"use client";

import { MapLibreMap, Marker, NavigationControl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { API_BASE, type Bbox, type Sign } from "../lib/api";
import { SIGNS_ATTRIBUTION, basemapStyle } from "../lib/basemap";
import { CLASS_HEX } from "../lib/signClass";

/**
 * Signs are drawn as DOM markers rather than as a GeoJSON circle layer.
 *
 * MapLibre parses GeoJSON sources in a Web Worker, and under this project's
 * bundler that worker never returns tiles: isSourceLoaded stayed false, no
 * error was raised, and every vector layer silently rendered nothing while the
 * raster basemap drew fine. Markers are plain elements on the main thread, so
 * they are immune to that whole class of failure — and at survey scale
 * (hundreds of signs inside one bbox) they cost nothing.
 *
 * The bbox outline is a projected overlay for the same reason, which leaves the
 * map with no vector layers at all.
 */

const MAX_MARKERS = 1200;

export default function SignMap({
  signs,
  bbox,
  selectedId,
  onSelect,
  theme,
}: {
  signs: Sign[];
  bbox: Bbox | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  theme: "dark" | "light";
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef(new Map<string, Marker>());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const [ready, setReady] = useState(false);
  const [box, setBox] = useState<{ left: number; top: number; w: number; h: number } | null>(
    null,
  );

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new MapLibreMap({
      container: container.current,
      style: basemapStyle(theme, SIGNS_ATTRIBUTION),
      center: [59.6062, 36.2972],
      zoom: 13.5,
      attributionControl: { compact: true },
    });
    map.current = instance;
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");

    // Clicking bare map clears the selection; markers stop propagation.
    instance.on("click", () => onSelectRef.current(null));
    instance.on("load", () => setReady(true));

    return () => {
      markers.current.forEach((m) => m.remove());
      markers.current.clear();
      instance.remove();
      map.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Markers are reconciled by id rather than rebuilt wholesale, so pins do not
  // flicker while a running job keeps adding to the list.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;

    const wanted = new Map(signs.slice(0, MAX_MARKERS).map((s) => [s.id, s]));

    markers.current.forEach((marker, id) => {
      if (!wanted.has(id)) {
        marker.remove();
        markers.current.delete(id);
      }
    });

    wanted.forEach((sign, id) => {
      const color = CLASS_HEX[sign.sign_class][theme];
      const existing = markers.current.get(id);

      if (existing) {
        const el = existing.getElement();
        el.dataset.selected = String(id === selectedId);
        el.style.setProperty("--pin", color);
        existing.setLngLat([sign.lon, sign.lat]);
        return;
      }

      const el = document.createElement("button");
      el.type = "button";
      el.className = "bina-pin";
      el.style.setProperty("--pin", color);
      el.dataset.selected = String(id === selectedId);
      el.dataset.review = String(sign.needs_review);
      el.setAttribute("aria-label", sign.sign_class);
      el.addEventListener("click", (event) => {
        event.stopPropagation();
        onSelectRef.current(id);
      });

      if (sign.crop_url) {
        const preview = document.createElement("span");
        preview.className = "bina-pin-preview";
        const img = document.createElement("img");
        img.src = `${API_BASE}${sign.crop_url}`;
        img.alt = "";
        img.loading = "lazy";
        preview.appendChild(img);
        el.appendChild(preview);
      }

      markers.current.set(
        id,
        new Marker({ element: el }).setLngLat([sign.lon, sign.lat]).addTo(instance),
      );
    });
  }, [signs, ready, theme, selectedId]);

  // Keep the bbox rectangle glued to the map.
  //
  // Measured on `render` rather than on `move`/`moveend`: the camera also
  // changes from fitBounds and from container resizes that emit no move event,
  // and a rectangle measured one frame too early stays wrong forever. The
  // equality guard stops this from setting state on every frame.
  const lastBox = useRef<string>("");

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !bbox) {
      setBox(null);
      lastBox.current = "";
      return;
    }
    const area = bbox;

    function project() {
      if (!instance) return;
      const a = instance.project([area[0], area[3]]);
      const b = instance.project([area[2], area[1]]);
      const next = {
        left: Math.min(a.x, b.x),
        top: Math.min(a.y, b.y),
        w: Math.abs(b.x - a.x),
        h: Math.abs(b.y - a.y),
      };
      const key = `${Math.round(next.left)},${Math.round(next.top)},${Math.round(next.w)},${Math.round(next.h)}`;
      if (key === lastBox.current) return;
      lastBox.current = key;
      setBox(next);
    }

    instance.fitBounds(
      [
        [area[0], area[1]],
        [area[2], area[3]],
      ],
      { padding: 72, duration: 0 },
    );
    instance.on("render", project);
    return () => {
      instance.off("render", project);
    };
  }, [bbox, ready]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !selectedId) return;
    const sign = signs.find((s) => s.id === selectedId);
    if (sign) instance.easeTo({ center: [sign.lon, sign.lat], duration: 420 });
  }, [selectedId, signs]);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {/* Inline positioning on purpose: Tailwind v4 emits utilities inside a
          cascade layer, and MapLibre's unlayered `.maplibregl-map { position:
          relative }` outranks any layered rule regardless of import order,
          which collapsed this container to zero height. */}
      <div ref={container} style={{ position: "absolute", inset: 0 }} />
      {box && (
        <div
          aria-hidden
          className="bina-bbox"
          style={{ left: box.left, top: box.top, width: box.w, height: box.h }}
        />
      )}
    </div>
  );
}
