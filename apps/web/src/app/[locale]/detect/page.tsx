"use client";

import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppShell, useTheme } from "../../../components/AppShell";
import { DetectionComposer } from "../../../components/DetectionComposer";
import { BasemapPicker } from "../../../components/BasemapPicker";
import { useBasemap } from "../../../components/useBasemap";
import { IconSearch } from "../../../components/icons";
import { searchStreets, type Bbox } from "../../../lib/api";

const SignMap = dynamic(() => import("../../../components/SignMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-[var(--panel-2)]" />,
});

/** Half-width, in degrees, of the square built around a searched place. */
const SPANS = [
  { km: 1, deg: 0.0045 },
  { km: 3, deg: 0.0135 },
  { km: 10, deg: 0.045 },
];

/**
 * Detect objects in an area.
 *
 * Two inputs, in the order that makes the third one answerable: where, and on
 * what imagery. Only then what to look for — because the imagery decides which
 * targets are possible, and offering the rest without saying why would be a
 * lie the map cannot correct.
 */
export default function DetectPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [theme] = useTheme();
  const {
    basemap,
    options: basemapOptions,
    selectedId: basemapId,
    select: selectBasemap,
  } = useBasemap();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ name: string; lat: number; lon: number }[]>([]);
  const [bbox, setBbox] = useState<Bbox | null>(null);
  const [span, setSpan] = useState(SPANS[1]);
  const [place, setPlace] = useState<string>("");

  async function search(value: string) {
    setQuery(value);
    if (value.trim().length < 2) {
      setResults([]);
      return;
    }
    try {
      const { items } = await searchStreets(value);
      setResults(items.slice(0, 6));
    } catch {
      setResults([]);
    }
  }

  function choose(item: { name: string; lat: number; lon: number }) {
    setPlace(item.name);
    setResults([]);
    setQuery(item.name);
    setBbox([
      item.lon - span.deg,
      item.lat - span.deg,
      item.lon + span.deg,
      item.lat + span.deg,
    ]);
  }

  function resize(next: (typeof SPANS)[number]) {
    setSpan(next);
    if (!bbox) return;
    const lon = (bbox[0] + bbox[2]) / 2;
    const lat = (bbox[1] + bbox[3]) / 2;
    setBbox([lon - next.deg, lat - next.deg, lon + next.deg, lat + next.deg]);
  }

  return (
    <AppShell title={t("nav.detect")} subtitle={t("detect.subtitle")}>
      <div className="flex min-h-0 flex-1">
        <aside className="w-[340px] shrink-0 overflow-y-auto border-e border-[var(--line)] bg-[var(--panel)] p-4">
          <label className="text-xs text-[var(--fg-faint)]">{t("detect.where")}</label>
          <div className="relative mt-1">
            <IconSearch
              size={14}
              className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-[var(--fg-faint)]"
            />
            <input
              value={query}
              onChange={(e) => search(e.target.value)}
              placeholder={t("detect.searchPlace")}
              className="w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 ps-8 text-[13px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
            />
          </div>

          {results.length > 0 && (
            <div className="mt-1 overflow-hidden rounded-[var(--radius-sm)] border border-[var(--line)]">
              {results.map((item) => (
                <button
                  key={`${item.lat},${item.lon}`}
                  onClick={() => choose(item)}
                  className="block w-full truncate px-3 py-2 text-start text-[12px] text-[var(--fg-muted)] transition-colors duration-150 hover:bg-[var(--panel-2)] hover:text-[var(--fg)]"
                >
                  {item.name}
                </button>
              ))}
            </div>
          )}

          {bbox && (
            <div className="mt-3">
              <div className="flex gap-1">
                {SPANS.map((option) => (
                  <button
                    key={option.km}
                    onClick={() => resize(option)}
                    className="flex-1 rounded-[var(--radius-sm)] border px-2 py-1 text-[11px] transition-colors duration-150"
                    style={{
                      borderColor: span.km === option.km ? "var(--accent)" : "var(--line)",
                      color: span.km === option.km ? "var(--accent)" : "var(--fg-muted)",
                    }}
                  >
                    {t("detect.km", { count: option.km.toLocaleString(locale) })}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-[11px] text-[var(--fg-faint)]" dir="ltr">
                {bbox.map((v) => v.toFixed(4)).join(", ")}
              </p>
            </div>
          )}

          <div className="mt-5 border-t border-[var(--line)] pt-4">
            <DetectionComposer
              bbox={bbox}
              onStarted={(id) => router.push(`/${locale}/jobs/${id}`)}
            />
          </div>
        </aside>

        <div className="relative min-w-0 flex-1">
          <SignMap
            basemap={basemap}
            signs={[]}
            bbox={bbox}
            selectedId={null}
            onSelect={() => undefined}
            theme={theme}
          />
          <BasemapPicker
            options={basemapOptions}
            selectedId={basemapId}
            onSelect={selectBasemap}
          />
          {place && (
            <div className="pointer-events-none absolute start-3 top-3 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel)] px-2.5 py-1.5 text-[12px] text-[var(--fg-muted)] shadow-[var(--shadow)]">
              {place}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
