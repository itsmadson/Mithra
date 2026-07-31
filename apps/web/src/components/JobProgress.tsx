"use client";

import { useTranslations } from "next-intl";
import type { JobStatus } from "../lib/api";

/**
 * Shown while a job is queued or running. Tiles are the honest unit of
 * progress: the worker completes them one at a time and commits as it goes,
 * so "3 of 12 tiles" is a fact rather than an estimate. Signs found so far
 * climbs alongside it, which is what tells the operator the run is alive.
 */
export default function JobProgress({ job }: { job: JobStatus }) {
  const t = useTranslations();
  const done = job.tile_count > 0 ? job.tile_count - job.failed_tile_count : 0;
  const pct = job.tile_count > 0 ? Math.round((done / job.tile_count) * 100) : 0;
  const indeterminate = job.tile_count === 0;

  return (
    <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-4">
      <div className="flex items-center gap-2.5 mb-3">
        <span className="relative flex size-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] opacity-60 motion-safe:animate-ping" />
          <span className="relative inline-flex size-2 rounded-full bg-[var(--accent)]" />
        </span>
        <span className="text-sm font-medium">{t(`job.${job.status}`)}</span>
        <span className="ms-auto text-xs text-[var(--fg-faint)]">
          {indeterminate ? t("job.preparing") : `${done}/${job.tile_count} ${t("job.tiles")}`}
        </span>
      </div>

      <div
        className="h-1.5 rounded-full bg-[var(--panel-2)] overflow-hidden"
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t("job.progressLabel")}
      >
        {indeterminate ? (
          <div className="h-full w-1/3 rounded-full bg-[var(--accent)] motion-safe:animate-pulse" />
        ) : (
          <div
            className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>

      <p className="mt-3 text-xs text-[var(--fg-muted)]">
        {t("job.foundSoFar", { count: job.total })}
      </p>
    </div>
  );
}
