"use client";

// maplibre-gl v6 ships named exports only; there is no default export.
import { MapLibreMap, NavigationControl, type GeoJSONSource } from "maplibre-gl";
import { useEffect, useRef } from "react";
import type { Bbox } from "../lib/api";
import { MASHHAD_CENTER, bboxToPolygon, normalizeBbox } from "../lib/bbox";
import { OSM_ATTRIBUTION, basemapStyle } from "../lib/basemap";

export default function BboxMap({
  value,
  onChange,
  theme = "dark",
}: {
  value: Bbox | null;
  onChange: (bbox: Bbox | null) => void;
  theme?: "dark" | "light";
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const anchor = useRef<[number, number] | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!container.current || map.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      style: basemapStyle(theme, OSM_ATTRIBUTION),
      center: MASHHAD_CENTER,
      zoom: 13,
      attributionControl: { compact: true },
    });
    map.current = instance;
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");

    instance.on("load", () => {
      instance.addSource("bbox", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      instance.addLayer({
        id: "bbox-fill",
        type: "fill",
        source: "bbox",
        paint: { "fill-color": "#4da3ff", "fill-opacity": 0.12 },
      });
      instance.addLayer({
        id: "bbox-line",
        type: "line",
        source: "bbox",
        paint: { "line-color": "#4da3ff", "line-width": 1.6 },
      });
    });

    // Shift-drag draws the box; plain drag still pans the map, because picking
    // a survey area takes several pan-and-adjust rounds.
    instance.on("mousedown", (event) => {
      if (!event.originalEvent.shiftKey) return;
      instance.dragPan.disable();
      instance.boxZoom.disable();
      instance.getCanvas().style.cursor = "crosshair";
      anchor.current = [event.lngLat.lng, event.lngLat.lat];
    });
    instance.on("mousemove", (event) => {
      if (!anchor.current) return;
      onChangeRef.current(normalizeBbox(anchor.current, [event.lngLat.lng, event.lngLat.lat]));
    });
    instance.on("mouseup", () => {
      anchor.current = null;
      instance.dragPan.enable();
      instance.boxZoom.enable();
      instance.getCanvas().style.cursor = "";
    });

    return () => {
      instance.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const source = map.current?.getSource("bbox") as GeoJSONSource | undefined;
    if (!source) return;
    source.setData(
      value
        ? { type: "FeatureCollection", features: [bboxToPolygon(value)] }
        : { type: "FeatureCollection", features: [] },
    );
  }, [value]);

  // Inline positioning on purpose. Tailwind v4 emits its utilities inside a
  // cascade layer, and unlayered third-party CSS outranks any layered rule
  // whatever the import order, so MapLibre's own `.maplibregl-map { position:
  // relative }` beat `.absolute` here and collapsed this container to zero
  // height. An inline style sits in no layer and cannot lose that way.
  return <div ref={container} style={{ position: "absolute", inset: 0 }} />;
}
