"use client";

import { useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { BasemapPicker } from "../../../components/BasemapPicker";
import { useBasemap } from "../../../components/useBasemap";
import { AppShell, useTheme } from "../../../components/AppShell";
import SignDetail from "../../../components/SignDetail";
import SignList from "../../../components/SignList";
import { IconAlert, IconSearch } from "../../../components/icons";
import {
  SIGN_CLASSES,
  listAllSigns,
  type Sign,
  type SignClass,
} from "../../../lib/api";
import { CLASS_COLOR, mapillaryName } from "../../../lib/signClass";

const SignMap = dynamic(() => import("../../../components/SignMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-[var(--panel-2)]" />,
});

const ALL: SignClass[] = [...SIGN_CLASSES, "unknown"];

/**
 * Every sign found so far, across all surveys.
 *
 * The per-survey view answers "what is on this street". This one is the
 * inventory: the thing a municipality actually asked for, and the view that
 * makes the classifier's weaknesses visible at a glance rather than one street
 * at a time.
 */
export default function SignsPage() {
  const t = useTranslations();
  const [theme] = useTheme();
  const {
    basemap,
    options: basemapOptions,
    selectedId: basemapId,
    select: selectBasemap,
  } = useBasemap();

  const [signs, setSigns] = useState<Sign[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [active, setActive] = useState<Set<SignClass>>(new Set(ALL));
  const [query, setQuery] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);

  useEffect(() => {
    listAllSigns({ limit: 2000 })
      .then(({ items }) => setSigns(items))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoaded(true));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return signs.filter((s) => {
      if (!active.has(s.sign_class)) return false;
      if (reviewOnly && !s.needs_review) return false;
      if (!q) return true;
      return (
        (mapillaryName(s.mapillary_value) ?? "").toLowerCase().includes(q) ||
        (s.mapillary_value ?? "").toLowerCase().includes(q) ||
        (s.image_id ?? "").includes(q)
      );
    });
  }, [signs, active, query, reviewOnly]);

  const counts = useMemo(() => {
    const out = new Map<SignClass, number>();
    for (const sign of signs) out.set(sign.sign_class, (out.get(sign.sign_class) ?? 0) + 1);
    return out;
  }, [signs]);

  const selected = useMemo(
    () => signs.find((s) => s.id === selectedId) ?? null,
    [signs, selectedId],
  );

  function toggle(cls: SignClass) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(cls)) next.delete(cls);
      else next.add(cls);
      return next;
    });
  }

  return (
    <AppShell
      title={t("nav.signs")}
      subtitle={
        loaded
          ? t("signs.subtitle", { shown: filtered.length, total: signs.length })
          : t("job.loading")
      }
    >
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="flex w-full shrink-0 flex-col border-b border-[var(--line)] bg-[var(--panel)] lg:w-[340px] lg:border-b-0 lg:border-e">
          <div className="border-b border-[var(--line)] p-3">
            <ul className="space-y-0.5">
              {ALL.map((cls) => {
                const count = counts.get(cls) ?? 0;
                const on = active.has(cls);
                const share = signs.length > 0 ? (count / signs.length) * 100 : 0;
                return (
                  <li key={cls}>
                    <button
                      onClick={() => toggle(cls)}
                      onDoubleClick={() => setActive(new Set([cls]))}
                      aria-pressed={on}
                      className="group relative w-full rounded-[var(--radius-sm)] px-2.5 py-2 text-start hover:bg-[var(--panel-2)] transition-colors duration-150"
                    >
                      <span
                        className="absolute inset-y-0 start-0 rounded-[var(--radius-sm)] transition-[width] duration-500 ease-out"
                        style={{
                          width: `${share}%`,
                          background: CLASS_COLOR[cls],
                          opacity: on ? 0.13 : 0.05,
                        }}
                        aria-hidden
                      />
                      <span className="relative flex items-center gap-2.5">
                        <span
                          className="size-2.5 shrink-0 rounded-full"
                          style={{ background: CLASS_COLOR[cls], opacity: on ? 1 : 0.3 }}
                          aria-hidden
                        />
                        <span
                          className="flex-1 truncate text-[13px]"
                          style={{ color: on ? "var(--fg)" : "var(--fg-faint)" }}
                        >
                          {t(`classes.${cls}`)}
                        </span>
                        <span
                          className="text-[13px] font-semibold"
                          style={{ color: on ? "var(--fg)" : "var(--fg-faint)" }}
                        >
                          {count}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2">
            <IconSearch size={14} className="shrink-0 text-[var(--fg-faint)]" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("list.searchPlaceholder")}
              className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--fg)] placeholder:text-[var(--fg-faint)] focus:outline-none"
            />
            <button
              onClick={() => setReviewOnly((v) => !v)}
              aria-pressed={reviewOnly}
              className="shrink-0 rounded-full border px-2 py-0.5 text-[11px] transition-colors duration-150"
              style={{
                borderColor: reviewOnly ? "var(--warn)" : "var(--line)",
                color: reviewOnly ? "var(--warn)" : "var(--fg-faint)",
              }}
            >
              {t("list.reviewOnly")}
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto max-lg:max-h-64">
            {error ? (
              <p className="flex items-start gap-2 p-4 text-xs text-[var(--danger)]">
                <IconAlert size={13} className="mt-px shrink-0" />
                {error}
              </p>
            ) : (
              <SignList signs={filtered} selectedId={selectedId} onSelect={setSelectedId} />
            )}
          </div>
        </div>

        <div className="relative min-h-[320px] flex-1">
          <SignMap
            basemap={basemap}
            key={theme}
            signs={filtered}
            bbox={null}
            selectedId={selectedId}
            onSelect={setSelectedId}
            theme={theme}
          />
          <BasemapPicker
            options={basemapOptions}
            selectedId={basemapId}
            onSelect={selectBasemap}
          />
        </div>

        {selected && (
          <div className="w-full shrink-0 border-t border-[var(--line)] lg:w-[320px] lg:border-s lg:border-t-0">
            <SignDetail sign={selected} onClose={() => setSelectedId(null)} />
          </div>
        )}
      </div>
    </AppShell>
  );
}
