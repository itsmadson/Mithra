"use client";

import maplibregl, { Map as MapLibreMap, Popup, type GeoJSONSource } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, type Bbox, type Sign, type SignClass } from "../lib/api";
import { SIGNS_ATTRIBUTION, basemapStyle } from "../lib/basemap";
import { CLASS_HEX } from "../lib/signClass";

/**
 * Signs render from a GeoJSON source through data-driven vector layers, which
 * is the standard way and the one that scales: styling is a paint expression
 * over feature properties, hit-testing is queryRenderedFeatures, and the same
 * FeatureCollection the map draws is what the API serves and exports.
 *
 * An earlier revision used DOM markers because MapLibre 6's GeoJSON worker
 * never returned tiles under this bundler — silently, with raster fine and
 * every vector layer empty. That was a workaround for a packaging bug, not a
 * design decision; pinning MapLibre to 5.x fixes the worker and the markers are
 * gone.
 */

const HALO = "signs-halo";
const DOT = "signs-dot";
const SELECTED = "signs-selected";

function colorExpression(theme: "dark" | "light") {
  const expression: unknown[] = ["match", ["get", "sign_class"]];
  (Object.keys(CLASS_HEX) as SignClass[]).forEach((cls) => {
    expression.push(cls, CLASS_HEX[cls][theme]);
  });
  expression.push(CLASS_HEX.unknown[theme]);
  return expression;
}

function toFeatureCollection(signs: Sign[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: signs.map((s) => ({
      type: "Feature",
      id: s.id,
      properties: {
        id: s.id,
        sign_class: s.sign_class,
        confidence: s.confidence,
        needs_review: s.needs_review ? 1 : 0,
        crop_url: s.crop_url ?? "",
        mapillary_value: s.mapillary_value ?? "",
      },
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
    })),
  };
}

function bboxFeature(bbox: Bbox): GeoJSON.FeatureCollection {
  const [w, s, e, n] = bbox;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [w, s],
              [e, s],
              [e, n],
              [w, n],
              [w, s],
            ],
          ],
        },
      },
    ],
  };
}

export default function SignMap({
  signs,
  bbox,
  geometry,
  selectedId,
  onSelect,
  theme,
}: {
  signs: Sign[];
  bbox: Bbox | null;
  /** Optional survey geometry (a street corridor) drawn instead of the bbox. */
  geometry?: GeoJSON.Geometry | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  theme: "dark" | "light";
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const popup = useRef<Popup | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const [ready, setReady] = useState(false);
  const data = useMemo(() => toFeatureCollection(signs), [signs]);
  const dataRef = useRef(data);
  dataRef.current = data;

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: basemapStyle(theme, SIGNS_ATTRIBUTION),
      center: [59.6062, 36.2972],
      zoom: 13.5,
      attributionControl: { compact: true },
    });
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: "metric" }), "bottom-left");

    instance.on("load", () => {
      instance.addSource("area", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      instance.addLayer({
        id: "area-fill",
        type: "fill",
        source: "area",
        paint: { "fill-color": "#4da3ff", "fill-opacity": 0.07 },
      });
      instance.addLayer({
        id: "area-line",
        type: "line",
        source: "area",
        paint: {
          "line-color": "#4da3ff",
          "line-width": 1.4,
          "line-dasharray": [3, 2],
          "line-opacity": 0.75,
        },
      });

      instance.addSource("signs", { type: "geojson", data: dataRef.current });

      instance.addLayer({
        id: HALO,
        type: "circle",
        source: "signs",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 8, 18, 22],
          "circle-color": colorExpression(theme) as never,
          "circle-opacity": 0.18,
          "circle-blur": 0.7,
        },
      });

      instance.addLayer({
        id: DOT,
        type: "circle",
        source: "signs",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 4, 18, 10],
          "circle-color": colorExpression(theme) as never,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": theme === "dark" ? "#0c1116" : "#ffffff",
          // Unreviewed low-confidence signs read as translucent, so an operator
          // can see which parts of a survey are still guesses.
          "circle-opacity": ["case", ["==", ["get", "needs_review"], 1], 0.45, 1],
        },
      });

      instance.addLayer({
        id: SELECTED,
        type: "circle",
        source: "signs",
        filter: ["==", ["get", "id"], ""],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 9, 18, 17],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-width": 2,
          "circle-stroke-color": theme === "dark" ? "#e7edf3" : "#14202b",
        },
      });

      instance.on("click", DOT, (event) => {
        const id = event.features?.[0]?.properties?.id as string | undefined;
        if (id) onSelectRef.current(id);
      });
      instance.on("click", (event) => {
        if (instance.queryRenderedFeatures(event.point, { layers: [DOT] }).length === 0) {
          onSelectRef.current(null);
        }
      });

      instance.on("mousemove", DOT, (event) => {
        instance.getCanvas().style.cursor = "pointer";
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties as Record<string, string>;
        const [lng, lat] = (feature.geometry as GeoJSON.Point).coordinates;
        const crop = props.crop_url
          ? `<img src="${API_BASE}${props.crop_url}" alt="" class="bina-pop-img" />`
          : "";
        popup.current ??= new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 14,
          className: "bina-pop",
        });
        popup.current
          .setLngLat([lng, lat])
          .setHTML(`<div class="bina-pop-card">${crop}</div>`)
          .addTo(instance);
      });
      instance.on("mouseleave", DOT, () => {
        instance.getCanvas().style.cursor = "";
        popup.current?.remove();
      });

      setReady(true);
    });

    // Vector layers leave nothing in the DOM to assert on, so the count of
    // actually-painted sign features is published on the container. It is the
    // only honest signal that rendering worked end to end: a source can hold
    // features while the layer paints none.
    instance.on("idle", () => {
      if (!container.current) return;
      container.current.dataset.signsRendered = String(
        instance.queryRenderedFeatures({ layers: [DOT] }).length,
      );
    });

    return () => {
      popup.current?.remove();
      popup.current = null;
      instance.remove();
      map.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!ready) return;
    (map.current?.getSource("signs") as GeoJSONSource | undefined)?.setData(data);
  }, [data, ready]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const source = instance.getSource("area") as GeoJSONSource | undefined;
    if (!source) return;

    if (geometry) {
      source.setData({
        type: "FeatureCollection",
        features: [{ type: "Feature", properties: {}, geometry }],
      });
    } else if (bbox) {
      source.setData(bboxFeature(bbox));
    } else {
      source.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    if (bbox) {
      instance.fitBounds(
        [
          [bbox[0], bbox[1]],
          [bbox[2], bbox[3]],
        ],
        { padding: 72, duration: 0 },
      );
    }
  }, [bbox, geometry, ready]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !instance.getLayer(SELECTED)) return;
    instance.setFilter(SELECTED, ["==", ["get", "id"], selectedId ?? ""]);
    if (!selectedId) return;
    const sign = signs.find((s) => s.id === selectedId);
    if (sign) instance.easeTo({ center: [sign.lon, sign.lat], duration: 420 });
  }, [selectedId, signs, ready]);

  // Inline positioning: Tailwind v4 emits utilities inside a cascade layer, and
  // MapLibre's unlayered `.maplibregl-map { position: relative }` outranks any
  // layered rule regardless of import order, collapsing this to zero height.
  return <div ref={container} style={{ position: "absolute", inset: 0 }} />;
}
