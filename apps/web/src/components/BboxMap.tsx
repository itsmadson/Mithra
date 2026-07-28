"use client";

// maplibre-gl v6 ships named exports only; there is no default export.
import { MapLibreMap, type GeoJSONSource } from "maplibre-gl";
import { useEffect, useRef } from "react";
import type { Bbox } from "../lib/api";
import { MASHHAD_CENTER, bboxToPolygon, normalizeBbox } from "../lib/bbox";

const STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

export default function BboxMap({
  value,
  onChange,
}: {
  value: Bbox | null;
  onChange: (bbox: Bbox | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const anchor = useRef<[number, number] | null>(null);

  useEffect(() => {
    if (!container.current || map.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      style: STYLE,
      center: MASHHAD_CENTER,
      zoom: 13,
    });
    map.current = instance;

    instance.on("load", () => {
      instance.addSource("bbox", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      instance.addLayer({
        id: "bbox-fill",
        type: "fill",
        source: "bbox",
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.15 },
      });
      instance.addLayer({
        id: "bbox-line",
        type: "line",
        source: "bbox",
        paint: { "line-color": "#2563eb", "line-width": 2 },
      });
    });

    // Shift-drag draws the box; plain drag still pans the map.
    instance.on("mousedown", (event) => {
      if (!event.originalEvent.shiftKey) return;
      instance.dragPan.disable();
      instance.boxZoom.disable();
      anchor.current = [event.lngLat.lng, event.lngLat.lat];
    });
    instance.on("mousemove", (event) => {
      if (!anchor.current) return;
      onChange(normalizeBbox(anchor.current, [event.lngLat.lng, event.lngLat.lat]));
    });
    instance.on("mouseup", () => {
      anchor.current = null;
      instance.dragPan.enable();
      instance.boxZoom.enable();
    });

    return () => {
      instance.remove();
      map.current = null;
    };
  }, [onChange]);

  useEffect(() => {
    const source = map.current?.getSource("bbox") as GeoJSONSource | undefined;
    if (!source) return;
    source.setData(
      value
        ? { type: "FeatureCollection", features: [bboxToPolygon(value)] }
        : { type: "FeatureCollection", features: [] },
    );
  }, [value]);

  return <div ref={container} className="h-[70vh] w-full rounded-lg" />;
}
