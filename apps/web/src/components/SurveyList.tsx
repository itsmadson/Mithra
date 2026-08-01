"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { SIGN_CLASSES, type JobSummary } from "../lib/api";
import { CLASS_COLOR } from "../lib/signClass";
import { IconAlert, IconLayers, IconPin } from "./icons";

const STATUS_COLOR: Record<JobSummary["status"], string> = {
  queued: "var(--fg-faint)",
  running: "var(--accent)",
  succeeded: "var(--ok)",
  partial: "var(--warn)",
  failed: "var(--danger)",
};

function relativeTime(iso: string, locale: string) {
  const then = new Date(iso).getTime();
  const seconds = Math.round((then - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 30],
    ["month", 12],
  ];
  let value = seconds;
  for (const [unit, size] of steps) {
    if (Math.abs(value) < size) return rtf.format(Math.round(value), unit);
    value /= size;
  }
  return rtf.format(Math.round(value), "year");
}

export default function SurveyList({ jobs }: { jobs: JobSummary[] }) {
  const t = useTranslations();
  const locale = useLocale();

  if (jobs.length === 0) {
    return (
      <div className="grid flex-1 place-items-center p-10 text-center">
        <div className="max-w-xs">
          <IconLayers size={26} className="mx-auto mb-3 text-[var(--fg-faint)]" />
          <p className="text-sm text-[var(--fg)]">{t("surveys.emptyTitle")}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-[var(--fg-muted)]">
            {t("surveys.emptyBody")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <ul data-testid="survey-list" className="divide-y divide-[var(--line)]">
      {jobs.map((job) => {
        const running = job.status === "queued" || job.status === "running";
        return (
          <li key={job.id}>
            <Link
              href={`/${locale}/jobs/${job.id}`}
              className="flex items-center gap-4 px-4 py-3 hover:bg-[var(--panel-2)] transition-colors duration-150"
            >
              <span
                className="size-2 shrink-0 rounded-full"
                style={{ background: STATUS_COLOR[job.status] }}
                aria-hidden
              />

              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate text-[14px] text-[var(--fg)]">
                    {job.name || t("surveys.untitled")}
                  </span>
                  {job.kind === "street" && (
                    <IconPin size={12} className="shrink-0 text-[var(--fg-faint)]" />
                  )}
                </span>
                <span className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--fg-faint)]">
                  <span style={{ color: STATUS_COLOR[job.status] }}>
                    {t(`job.${job.status}`)}
                  </span>
                  <span aria-hidden>·</span>
                  <span>{relativeTime(job.created_at, locale)}</span>
                  {running && job.tile_count > 0 && (
                    <>
                      <span aria-hidden>·</span>
                      <span>
                        {t("job.tilesDone", {
                          done: job.tile_count - job.failed_tile_count,
                          total: job.tile_count,
                        })}
                      </span>
                    </>
                  )}
                </span>
              </span>

              {job.failed_count > 0 && (
                <span
                  className="flex shrink-0 items-center gap-1 text-[11px] text-[var(--fg-faint)]"
                  title={t("job.failedNote", { count: job.failed_count })}
                >
                  <IconAlert size={11} />
                  {job.failed_count}
                </span>
              )}

              <span className="shrink-0 text-end">
                <span className="block text-[15px] font-semibold text-[var(--fg)]">
                  {job.total.toLocaleString(locale)}
                </span>
                <span className="block text-[10px] text-[var(--fg-faint)]">
                  {t("surveys.signs")}
                </span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** A compact key so the list's status dots are not unexplained colour. */
export function ClassKey() {
  const t = useTranslations();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      {[...SIGN_CLASSES, "unknown" as const].map((cls) => (
        <span key={cls} className="flex items-center gap-1.5 text-[11px] text-[var(--fg-faint)]">
          <span
            className="size-2 rounded-full"
            style={{ background: CLASS_COLOR[cls] }}
            aria-hidden
          />
          {t(`classes.${cls}`)}
        </span>
      ))}
    </div>
  );
}
