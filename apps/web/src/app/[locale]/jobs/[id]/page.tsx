"use client";

import { useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { use, useEffect, useMemo, useState } from "react";
import ClassFilter from "../../../../components/ClassFilter";
import JobProgress from "../../../../components/JobProgress";
import SignDetail from "../../../../components/SignDetail";
import SignList from "../../../../components/SignList";
import { BasemapPicker } from "../../../../components/BasemapPicker";
import { useBasemap } from "../../../../components/useBasemap";
import { AppShell, useTheme } from "../../../../components/AppShell";
import { IconAlert, IconDownload, IconSearch } from "../../../../components/icons";
import {
  SIGN_CLASSES,
  exportUrl,
  featuresUrl,
  getJob,
  listSigns,
  type Bbox,
  type JobStatus,
  type Feature,
  type FeatureClass,
} from "../../../../lib/api";
import { isTerminal } from "../../../../lib/counts";
import { mapillaryName } from "../../../../lib/signClass";

// MapLibre touches window on import, so it must not run during SSR.
const SignMap = dynamic(() => import("../../../../components/SignMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-[var(--panel-2)]" />,
});

const ALL: string[] = [...SIGN_CLASSES, "unknown"];

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations();
  const [theme, setTheme] = useTheme();
  const {
    basemap,
    options: basemapOptions,
    selectedId: basemapId,
    select: selectBasemap,
  } = useBasemap();

  const [job, setJob] = useState<JobStatus | null>(null);
  const [signs, setSigns] = useState<Feature[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [active, setActive] = useState<Set<string>>(new Set(ALL));
  const [query, setQuery] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const next = await getJob(id);
        if (cancelled) return;
        setJob(next);
        // Seed the filter from what this run actually found. Starting from the
        // sign classes meant a water run filtered every one of its own
        // detections out and showed "nothing matches" over a full map.
        setActive((prev) => {
          const classes = Object.keys(next.counts ?? {});
          const overlaps = classes.some((c) => prev.has(c));
          return overlaps || classes.length === 0 ? prev : new Set([...prev, ...classes]);
        });

        // Load signs as they appear, not only at the end: a long run should
        // fill the map while it works rather than showing an empty rectangle.
        if (next.total > 0) {
          const { items } = await listSigns(id);
          if (!cancelled) setSigns(items);
        }
        if (isTerminal(next.status)) return;
        setTimeout(poll, 2500);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return signs.filter((s) => {
      if (!active.has(s.class_name)) return false;
      if (reviewOnly && !s.needs_review) return false;
      if (!q) return true;
      const name = mapillaryName(s.source_value) ?? "";
      return (
        name.toLowerCase().includes(q) ||
        (s.source_value ?? "").toLowerCase().includes(q) ||
        (s.image_id ?? "").includes(q)
      );
    });
  }, [signs, active, query, reviewOnly]);

  const selected = useMemo(
    () => signs.find((s) => s.id === selectedId) ?? null,
    [signs, selectedId],
  );

  // Memoised by value, not by object identity. Rebuilding this array on every
  // render made the map's bbox effect re-run continuously: it refit the camera
  // and re-measured the rectangle from the pre-fit camera each time, so the
  // survey outline was drawn at the wrong scale and never corrected itself.
  const bboxKey = job ? job.bbox.join(",") : "";
  const bbox: Bbox | null = useMemo(
    () => (bboxKey ? (bboxKey.split(",").map(Number) as Bbox) : null),
    [bboxKey],
  );

  function toggle(cls: string) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(cls)) next.delete(cls);
      else next.add(cls);
      return next;
    });
  }

  if (error) {
    return (
      <main className="grid min-h-dvh place-items-center p-6">
        <div className="max-w-sm text-center">
          <IconAlert size={26} className="mx-auto mb-3 text-[var(--danger)]" />
          <p className="text-sm text-[var(--fg)]">{t("error.title")}</p>
          <p className="mt-1.5 text-xs text-[var(--fg-muted)]">{error}</p>
        </div>
      </main>
    );
  }

  return (
    <AppShell
        title={job ? job.name || t("job.titleWithCount", { count: job.total }) : t("job.loading")}
        subtitle={
          job
            ? `${t("job.titleWithCount", { count: job.total })} · ${t(`job.${job.status}`)} · ${t("job.tilesDone", {
                done: job.tile_count - job.failed_tile_count,
                total: job.tile_count,
              })}`
            : undefined
        }
        actions={
        <>
        {job && isTerminal(job.status) && (
          <div className="hidden sm:flex items-center gap-1.5">
            <a
              href={exportUrl(id, "csv")}
              className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1.5 text-xs font-medium text-[var(--fg-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors duration-150"
            >
              <IconDownload size={13} />
              CSV
            </a>
            <a
              href={exportUrl(id, "geojson")}
              className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1.5 text-xs font-medium text-[var(--fg-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors duration-150"
            >
              <IconDownload size={13} />
              GeoJSON
            </a>
          </div>
        )}
      </>
        }
      >

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="flex w-full shrink-0 flex-col border-b border-[var(--line)] bg-[var(--panel)] lg:w-[340px] lg:border-b-0 lg:border-e">
          {job && !isTerminal(job.status) && (
            <div className="p-3">
              <JobProgress job={job} />
            </div>
          )}

          {job && (
            <div className="border-b border-[var(--line)] p-3">
              <ClassFilter
                job={job}
                active={active}
                onToggle={toggle}
                onOnly={(cls) => setActive(new Set([cls]))}
              />
              {job.failed_count > 0 && (
                <p className="mt-2.5 flex items-start gap-1.5 px-2.5 text-[11px] text-[var(--fg-faint)]">
                  <IconAlert size={12} className="mt-px shrink-0" />
                  {t("job.failedNote", { count: job.failed_count })}
                </p>
              )}
              {job.reason === "no_imagery" && (
                <p className="mt-2.5 rounded-[var(--radius-sm)] bg-[var(--panel-2)] px-2.5 py-2 text-[11px] text-[var(--fg-muted)]">
                  {t("job.noImagery")}
                </p>
              )}
            </div>
          )}

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
            <SignList signs={filtered} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
        </div>

        <div className="relative min-h-[320px] flex-1">
          <SignMap
            basemap={basemap}
            outlinesUrl={featuresUrl(id)}
            key={theme}
            signs={filtered}
            bbox={bbox}
            geometry={job?.geometry ?? null}
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
