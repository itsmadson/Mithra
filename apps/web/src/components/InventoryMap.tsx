"use client";

import maplibregl, { Map as MapLibreMap, type GeoJSONSource } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
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
  const collection = useMemo(() => toFeatureCollection(features), [features]);

  useEffect(() => {
    if (!container.current || map.current) return;
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
  const firstStyle = useRef(true);
  useEffect(() => {
    if (!map.current || !ready.current) return;
    if (firstStyle.current) {
      firstStyle.current = false;
      return;
    }
    const instance = map.current;
    ready.current = false;
    instance.setStyle(basemapStyle(theme, SIGNS_ATTRIBUTION, basemap));
    instance.once("styledata", () => {
      if (instance.getSource(SOURCE)) return;
      instance.addSource(SOURCE, { type: "geojson", data: collection });
      addLayers(instance, theme);
      ready.current = true;
      instance.setFilter(ACTIVE, ["==", ["get", "id"], activeId ?? ""]);
    });
    // collection and activeId are read at re-add time, not tracked: a data
    // change already has its own effect, and listing them here would re-style
    // the map every time a row arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basemap, theme]);

  return <div ref={container} className="h-full w-full" />;
}
