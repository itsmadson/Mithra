"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { IconLayers } from "./icons";
import type { BasemapChoice } from "../lib/basemap";

/**
 * Choose the backdrop, from the map itself.
 *
 * On the map rather than only in settings, because the reason to switch is
 * something on screen: a sign that cannot be placed against a street map is
 * often obvious against aerial imagery, and walking to another page to change
 * it loses the view you were reading.
 */
export function BasemapPicker({
  options,
  selectedId,
  onSelect,
}: {
  options: BasemapChoice[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations();
  const [open, setOpen] = useState(false);

  // One source is no choice.
  if (options.length < 2) return null;

  const selected = options.find((o) => o.id === selectedId);

  return (
    <div className="absolute bottom-3 end-3 z-10">
      {open && (
        <div className="mb-1.5 min-w-44 overflow-hidden rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-lg)]">
          {options.map((option) => (
            <button
              key={option.id}
              onClick={() => {
                onSelect(option.id);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-start text-[12px] transition-colors duration-150 hover:bg-[var(--panel-2)]"
              style={{ color: option.id === selectedId ? "var(--accent)" : "var(--fg-muted)" }}
            >
              <span
                className="size-1.5 shrink-0 rounded-full"
                style={{
                  background: option.id === selectedId ? "var(--accent)" : "transparent",
                }}
                aria-hidden
              />
              <span className="truncate">{option.name}</span>
            </button>
          ))}
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={t("basemap.choose")}
        className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel)] px-2.5 py-1.5 text-[12px] text-[var(--fg-muted)] shadow-[var(--shadow)] transition-colors duration-150 hover:text-[var(--fg)]"
      >
        <IconLayers size={14} />
        <span className="max-w-32 truncate">{selected?.name ?? t("basemap.choose")}</span>
      </button>
    </div>
  );
}
