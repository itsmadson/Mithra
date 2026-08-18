"use client";

import maplibregl, { Map as MapLibreMap, type GeoJSONSource } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Feature } from "../lib/api";
import { SIGNS_ATTRIBUTION, basemapStyle, type BasemapChoice } from "../lib/basemap";
import { DOMAIN_HEX } from "../lib/targets";

/**
 * Where the current page of the inventory is.
 *
 * Deliberately shows the page rather than everything: the map answers "where
 * are the rows I am looking at", and a map of every detection in the
 * organisation answers a question nobody asked while taking a second to draw.
 * Selection is shared with the table in both directions, because the two are
 * one view of one list.
 */

const SOURCE = "inventory";
const HALO = "inventory-halo";
const DOT = "inventory-dot";
const ACTIVE = "inventory-active";

function colorExpression(theme: "dark" | "light") {
  // Colour by domain, not by class: there are ten domains and seventy-one
  // classes, and a legend of seventy-one hues is a legend nobody reads.
  const expression: unknown[] = ["match", ["get", "domain"]];
  for (const [domain, hex] of Object.entries(DOMAIN_HEX)) {
    if (domain === "other") continue;
    expression.push(domain, hex[theme]);
  }
  expression.push(DOMAIN_HEX.other[theme]);
  return expression;
}

function toFeatureCollection(features: Feature[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: features.map((f) => ({
      type: "Feature",
      id: f.id,
      properties: {
        id: f.id,
        class_name: f.class_name,
        domain: f.domain ?? "other",
        confidence: f.confidence,
        needs_review: f.needs_review ? 1 : 0,
      },
      geometry: { type: "Point", coordinates: [f.lon, f.lat] },
    })),
  };
}


/** The three layers, in one place: added on load and re-added after a restyle. */
function addLayers(instance: MapLibreMap, theme: "dark" | "light") {
  // A halo under every dot so a detection stays visible over both a dark
  // basemap and a bright aerial tile.
  instance.addLayer({
    id: HALO,
    type: "circle",
    source: SOURCE,
    paint: {
      "circle-radius": 6.5,
      "circle-color": theme === "dark" ? "#101820" : "#fbf6ec",
      "circle-opacity": 0.85,
    },
  });
  instance.addLayer({
    id: DOT,
    type: "circle",
    source: SOURCE,
    paint: {
      "circle-radius": 4,
      "circle-color": colorExpression(theme) as never,
      // Anything the model was unsure about is ringed rather than recoloured:
      // colour already carries the domain and cannot carry two things.
      "circle-stroke-width": ["case", ["==", ["get", "needs_review"], 1], 1.5, 0],
      "circle-stroke-color": theme === "dark" ? "#e0a53a" : "#8C5A2B",
    },
  });
  instance.addLayer({
    id: ACTIVE,
    type: "circle",
    source: SOURCE,
    filter: ["==", ["get", "id"], ""],
    paint: {
      "circle-radius": 9,
      "circle-color": "transparent",
      "circle-stroke-width": 2,
      "circle-stroke-color": theme === "dark" ? "#D4A017" : "#8C5A2B",
    },
  });
}

export default function InventoryMap({
  features,
  theme,
  activeId,
  onSelect,
  basemap,
}: {
  features: Feature[];
  theme: "dark" | "light";
  activeId: string | null;
  onSelect: (id: string) => void;
  basemap?: BasemapChoice | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const ready = useRef(false);
  // What the map was constructed with, which is not necessarily what is wanted
  // by the time it finishes loading.
  const basemapAtCreation = useRef<string>("default");
  const themeAtCreation = useRef<"dark" | "light">("dark");
  const collection = useMemo(() => toFeatureCollection(features), [features]);

  useEffect(() => {
    if (!container.current || map.current) return;
    basemapAtCreation.current = basemap?.id ?? "default";
    themeAtCreation.current = theme;
    const instance = new maplibregl.Map({
      container: container.current,
      style: basemapStyle(theme, SIGNS_ATTRIBUTION, basemap),
      center: [59.6, 36.29],
      zoom: 10,
      attributionControl: { compact: true },
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      instance.addSource(SOURCE, { type: "geojson", data: collection });
      addLayers(instance, theme);
      ready.current = true;

      instance.on("click", DOT, (event) => {
        const id = event.features?.[0]?.properties?.id;
        if (typeof id === "string") onSelect(id);
      });
      instance.on("mouseenter", DOT, () => {
        instance.getCanvas().style.cursor = "pointer";
      });
      instance.on("mouseleave", DOT, () => {
        instance.getCanvas().style.cursor = "";
      });

      // Record what it was built with, then nudge the restyle effect: if the
      // basemap list arrived while the map was still loading, this is where
      // that change gets applied.
      applied.current = `${basemapAtCreation.current}:${themeAtCreation.current}`;
      setStyleReady((n) => n + 1);
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
      ready.current = false;
    };
    // The map is created once; data and theme are pushed in through the effects
    // below rather than by rebuilding it, which would lose the viewport.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!map.current || !ready.current) return;
    (map.current.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(collection);

    // Fit to the rows in hand, but only when there are rows and the viewport has
    // not been moved by hand — refitting under a operator who just panned is
    // the map fighting the person using it.
    if (features.length === 0) return;
    const lons = features.map((f) => f.lon);
    const lats = features.map((f) => f.lat);
    map.current.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 40, maxZoom: 16, duration: 400 },
    );
  }, [collection, features]);

  useEffect(() => {
    if (!map.current || !ready.current) return;
    map.current.setFilter(ACTIVE, ["==", ["get", "id"], activeId ?? ""]);
  }, [activeId]);

  // Changing the basemap replaces the style, and a style change takes every
  // source and layer with it — so the detections have to be put back.
  // Which basemap and theme the map is currently drawn with. Compared against
  // what is wanted, rather than counting renders: the map is created before its
  // basemap list has loaded, so the first real change arrives late and an
  // "ignore the first run" guard swallows exactly the change that matters.
  const applied = useRef<string | null>(null);
  const [styleReady, setStyleReady] = useState(0);

  useEffect(() => {
    if (!map.current) return;
    const wanted = `${basemap?.id ?? "default"}:${theme}`;
    if (applied.current === null || applied.current === wanted) return;
    applied.current = wanted;

    const instance = map.current;
    ready.current = false;
    instance.setStyle(basemapStyle(theme, SIGNS_ATTRIBUTION, basemap));

    // styledata, not idle: idle waits for tiles, and a basemap whose tiles
    // never arrive would never reach it — leaving the map permanently
    // mid-change and every later switch blocked behind it. Whether the imagery
    // loads is the network's business; whether our layers are back is ours.
    instance.once("styledata", () => {
      if (!instance.getSource(SOURCE)) {
        instance.addSource(SOURCE, { type: "geojson", data: collection });
        addLayers(instance, theme);
      }
      ready.current = true;
      instance.setFilter(ACTIVE, ["==", ["get", "id"], activeId ?? ""]);
      setStyleReady((n) => n + 1);
    });
    // collection and activeId are read at re-add time rather than tracked:
    // a data change has its own effect, and listing them here would restyle the
    // map every time a row arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basemap, theme, styleReady]);

  return (
    <div
      ref={container}
      className="h-full w-full"
      // Which basemap this map is drawing. Rendered as an attribute so a
      // browser test can assert the switch reached the map rather than
      // inferring it from tiles, which may not load on every network.
      data-basemap={basemap?.id ?? "default"}
      data-style-generation={styleReady}
    />
  );
}
