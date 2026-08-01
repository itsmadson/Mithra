"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { listBasemaps, type Basemap } from "../lib/api";
import {
  BUILT_IN_ID,
  builtInBasemap,
  storeBasemapId,
  storedBasemapId,
  type BasemapChoice,
} from "../lib/basemap";

/**
 * Which backdrop the maps draw, resolved once and shared.
 *
 * Precedence: what this operator last chose, then the organisation's default,
 * then OpenStreetMap. A remembered choice wins over the default because an
 * administrator setting a house style should not override the person who
 * deliberately switched to aerial imagery to read a sign.
 */
export function useBasemap() {
  const t = useTranslations();
  const [options, setOptions] = useState<BasemapChoice[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const built = builtInBasemap(t("basemap.builtIn"));

    listBasemaps()
      .then(({ items }) => {
        if (cancelled) return;
        const all = [built, ...items.map(toChoice)];
        setOptions(all);

        const remembered = storedBasemapId();
        const fallback =
          items.find((b) => b.is_default)?.id ?? BUILT_IN_ID;
        setSelectedId(
          remembered && all.some((o) => o.id === remembered) ? remembered : fallback,
        );
      })
      .catch(() => {
        // The map still has to draw; the built-in source is always reachable.
        if (!cancelled) {
          setOptions([built]);
          setSelectedId(BUILT_IN_ID);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [t]);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    storeBasemapId(id);
  }, []);

  const basemap =
    options.find((o) => o.id === selectedId) ?? options[0] ?? null;

  return { basemap, options, selectedId, select };
}

function toChoice(b: Basemap): BasemapChoice {
  return {
    id: b.id,
    name: b.name,
    url_template: b.url_template,
    attribution: b.attribution,
    tint: b.tint,
  };
}
