"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  createStreetJob,
  searchStreets,
  type StreetHit,
} from "../lib/api";
import { IconAlert, IconSearch, IconTarget } from "./icons";

const BUFFERS = [15, 25, 40, 60];

/**
 * The survey composer.
 *
 * An operator surveys a معبر, so the input is a street name, resolved against
 * OpenStreetMap. The search is debounced and aborts in flight: Nominatim's
 * policy is one request per second, and a request per keystroke would both
 * violate it and race its own results into the list out of order.
 */
export default function NewSurvey({ onCreated }: { onCreated?: () => void }) {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<StreetHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [chosen, setChosen] = useState<StreetHit | null>(null);
  const [bufferM, setBufferM] = useState(25);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2 || chosen) {
      setHits([]);
      return;
    }
    const timer = setTimeout(async () => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setSearching(true);
      setError(null);
      try {
        const { items } = await searchStreets(q, controller.signal);
        setHits(items);
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        setSearching(false);
      }
    }, 450);
    return () => clearTimeout(timer);
  }, [query, chosen]);

  async function submit() {
    if (!chosen || busy) return;
    setBusy(true);
    setError(null);
    try {
      const job = await createStreetJob(chosen, bufferM);
      onCreated?.();
      router.push(`/${locale}/jobs/${job.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <section className="flex h-full flex-col">
      <header className="border-b border-[var(--line)] px-4 py-3">
        <h2 className="text-sm font-semibold">{t("compose.title")}</h2>
        <p className="mt-0.5 text-xs text-[var(--fg-muted)]">{t("compose.subtitle")}</p>
      </header>

      <div className="flex-1 overflow-y-auto p-4">
        <label className="block text-xs text-[var(--fg-faint)]" htmlFor="street">
          {t("compose.streetLabel")}
        </label>
        <div className="mt-1.5 flex items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-2 focus-within:border-[var(--accent)] transition-colors duration-150">
          <IconSearch size={14} className="shrink-0 text-[var(--fg-faint)]" />
          <input
            id="street"
            value={chosen ? chosen.name || chosen.display_name : query}
            onChange={(e) => {
              setChosen(null);
              setQuery(e.target.value);
            }}
            placeholder={t("compose.streetPlaceholder")}
            className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--fg)] placeholder:text-[var(--fg-faint)] focus:outline-none"
          />
          {searching && (
            <span className="size-3 shrink-0 rounded-full border-2 border-[var(--line-strong)] border-t-[var(--accent)] motion-safe:animate-spin" />
          )}
        </div>

        {hits.length > 0 && !chosen && (
          <ul className="mt-2 overflow-hidden rounded-[var(--radius-sm)] border border-[var(--line)]">
            {hits.map((hit) => (
              <li key={`${hit.osm_id}-${hit.lat}`}>
                <button
                  onClick={() => {
                    setChosen(hit);
                    setHits([]);
                  }}
                  className="w-full border-b border-[var(--line)] px-3 py-2 text-start last:border-0 hover:bg-[var(--panel-2)] transition-colors duration-150"
                >
                  <div className="truncate text-[13px] text-[var(--fg)]">
                    {hit.name || hit.name_fa || hit.display_name}
                  </div>
                  <div className="truncate text-[11px] text-[var(--fg-faint)]">
                    {hit.display_name}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}

        {query.trim().length >= 2 && !searching && hits.length === 0 && !chosen && (
          <p className="mt-2 text-xs text-[var(--fg-faint)]">{t("compose.noHits")}</p>
        )}

        {chosen && (
          <div className="mt-4">
            <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] p-3">
              <div className="flex items-start gap-2">
                <IconTarget size={14} className="mt-0.5 shrink-0 text-[var(--accent)]" />
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-[var(--fg)]">
                    {chosen.name || chosen.name_fa || chosen.display_name}
                  </div>
                  <div className="mt-0.5 text-[11px] text-[var(--fg-faint)]">
                    OSM way {chosen.osm_id} · {chosen.lat.toFixed(4)},{" "}
                    {chosen.lon.toFixed(4)}
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-4">
              <div className="flex items-baseline justify-between">
                <label className="text-xs text-[var(--fg-faint)]">
                  {t("compose.bufferLabel")}
                </label>
                <span className="text-xs text-[var(--fg-muted)]">{bufferM} m</span>
              </div>
              <div className="mt-1.5 flex gap-1.5">
                {BUFFERS.map((value) => (
                  <button
                    key={value}
                    onClick={() => setBufferM(value)}
                    aria-pressed={bufferM === value}
                    className="flex-1 rounded-[var(--radius-sm)] border px-2 py-1.5 text-xs transition-colors duration-150"
                    style={{
                      borderColor:
                        bufferM === value ? "var(--accent)" : "var(--line)",
                      color: bufferM === value ? "var(--accent)" : "var(--fg-muted)",
                    }}
                  >
                    {value}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-[var(--fg-faint)]">
                {t("compose.bufferHelp")}
              </p>
            </div>
          </div>
        )}

        {error && (
          <p className="mt-3 flex items-start gap-1.5 text-[11px] text-[var(--danger)]">
            <IconAlert size={12} className="mt-px shrink-0" />
            {error}
          </p>
        )}
      </div>

      <footer className="border-t border-[var(--line)] p-3">
        <button
          onClick={submit}
          disabled={!chosen || busy}
          className="w-full rounded-[var(--radius-sm)] bg-[var(--accent)] px-3 py-2.5 text-[13px] font-semibold text-[var(--accent-ink)] transition-[opacity,transform] duration-150 hover:opacity-90 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? t("compose.starting") : t("compose.start")}
        </button>
        <p className="mt-2 text-center text-[11px] text-[var(--fg-faint)]">
          {t("compose.bboxHint")}
        </p>
      </footer>
    </section>
  );
}
