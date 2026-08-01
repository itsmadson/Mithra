"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { Histogram, StackedShare, StatTile, TimeSeries } from "../../components/charts";
import { IconAlert } from "../../components/icons";
import { getOverview, type Overview, type SignClass } from "../../lib/api";
import { CLASS_COLOR, CLASS_ORDER } from "../../lib/signClass";

const RANGES = [7, 30, 90] as const;

function Panel({
  title,
  hint,
  children,
  className = "",
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-4 ${className}`}
    >
      <h2 className="text-[13px] font-semibold">{title}</h2>
      {hint && <p className="mt-0.5 text-[11px] text-[var(--fg-muted)]">{hint}</p>}
      <div className="mt-3.5">{children}</div>
    </section>
  );
}

const STATUS_TONE: Record<string, string> = {
  succeeded: "var(--c-city)",
  partial: "var(--warn)",
  failed: "var(--danger)",
  running: "var(--accent)",
  queued: "var(--fg-faint)",
};

/**
 * The dashboard.
 *
 * It answers, in order: how big is the inventory, how much of it is trustworthy,
 * what is waiting for a person, and is the tool being used. Everything else is
 * one click away. The panels are deliberately not a grid of equal tiles — the
 * numbers that drive a decision are larger than the ones that provide context.
 */
export default function DashboardPage() {
  const t = useTranslations();
  const locale = useLocale();
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const next = await getOverview(days);
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    load();
    // Surveys finish while the dashboard is open; a figure that silently goes
    // stale is worse than one that visibly moves.
    const timer = setInterval(load, 15_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [days]);

  const n = (v: number) => v.toLocaleString(locale);
  const base = `/${locale}`;

  return (
    <AppShell
      title={t("nav.dashboard")}
      subtitle={t("dashboard.subtitle")}
      actions={
        <div
          className="flex rounded-[var(--radius-sm)] border border-[var(--line)] p-0.5"
          role="group"
          aria-label={t("dashboard.range")}
        >
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setDays(r)}
              aria-pressed={days === r}
              className="rounded-[calc(var(--radius-sm)-2px)] px-2.5 py-1 text-[12px] transition-colors duration-150"
              style={{
                background: days === r ? "var(--panel-2)" : undefined,
                color: days === r ? "var(--fg)" : "var(--fg-muted)",
              }}
            >
              {t("dashboard.days", { count: n(r) })}
            </button>
          ))}
        </div>
      }
    >
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mx-auto grid max-w-[1180px] gap-4">
          {error && (
            <p className="flex items-start gap-2 text-xs text-[var(--danger)]">
              <IconAlert size={13} className="mt-px shrink-0" />
              {error}
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              label={t("dashboard.totalSigns")}
              value={data ? n(data.signs.total) : "—"}
              hint={t("dashboard.acrossSurveys", { count: n(data?.surveys.total ?? 0) })}
              spark={data?.activity.signs_per_day.map((p) => p.count)}
            />
            <StatTile
              label={t("dashboard.confident")}
              value={data ? `${data.signs.confident_share.toLocaleString(locale)}%` : "—"}
              hint={t("dashboard.confidentHint")}
              tone={
                data && data.signs.confident_share < 60
                  ? "warn"
                  : data
                    ? "good"
                    : "neutral"
              }
            />
            <StatTile
              label={t("dashboard.queue")}
              value={data ? n(data.signs.needs_review) : "—"}
              hint={t("dashboard.queueHint")}
              tone={data && data.signs.needs_review > 0 ? "warn" : "neutral"}
            />
            <StatTile
              label={t("dashboard.running")}
              value={data ? n(data.surveys.running) : "—"}
              hint={
                data?.surveys.failed
                  ? t("dashboard.failedSurveys", { count: n(data.surveys.failed) })
                  : t("dashboard.noneRunning")
              }
              tone={data && data.surveys.failed > 0 ? "danger" : "neutral"}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Panel title={t("dashboard.activity")} hint={t("dashboard.activityHint")}>
              {data && (
                <TimeSeries
                  points={data.activity.signs_per_day}
                  label={t("dashboard.activity")}
                />
              )}
            </Panel>

            <Panel title={t("dashboard.byClass")} hint={t("dashboard.byClassHint")}>
              {data && (
                <StackedShare
                  parts={CLASS_ORDER.filter(
                    (cls) => (data.signs.by_class[cls] ?? 0) > 0,
                  ).map((cls) => ({
                    key: cls,
                    label: t(`classes.${cls}`),
                    value: data.signs.by_class[cls] ?? 0,
                    color: CLASS_COLOR[cls as SignClass],
                  }))}
                />
              )}
            </Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
            <Panel title={t("dashboard.confidence")} hint={t("dashboard.confidenceHint")}>
              {data && (
                <Histogram
                  buckets={data.confidence.buckets}
                  threshold={data.confidence.threshold}
                  label={t("dashboard.confidence")}
                  belowLabel={t("dashboard.belowThreshold")}
                />
              )}
            </Panel>

            <Panel title={t("dashboard.topSurveys")} hint={t("dashboard.topSurveysHint")}>
              {data?.top_surveys.length ? (
                <div className="grid gap-2">
                  {data.top_surveys.slice(0, 6).map((s) => {
                    const share =
                      data.top_surveys[0].total > 0
                        ? (s.total / data.top_surveys[0].total) * 100
                        : 0;
                    return (
                      <Link
                        key={s.id}
                        href={`${base}/jobs/${s.id}`}
                        className="group block"
                      >
                        <div className="flex items-baseline justify-between gap-3 text-[12px]">
                          <span className="truncate text-[var(--fg-muted)] group-hover:text-[var(--fg)] transition-colors duration-150">
                            {s.name || t("dashboard.untitled")}
                          </span>
                          <span className="shrink-0 tabular-nums text-[var(--fg)]">
                            {n(s.total)}
                            {s.needs_review > 0 && (
                              <span className="ms-1.5 text-[var(--warn)]">
                                {t("dashboard.reviewCount", { count: n(s.needs_review) })}
                              </span>
                            )}
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 rounded-full bg-[var(--panel-2)]">
                          <div
                            className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-300"
                            style={{ width: `${share}%` }}
                          />
                        </div>
                      </Link>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[12px] text-[var(--fg-muted)]">{t("dashboard.empty")}</p>
              )}
            </Panel>
          </div>

          <Panel title={t("dashboard.recent")} hint={t("dashboard.recentHint")}>
            {data?.recent.length ? (
              <div className="grid gap-px overflow-hidden rounded-[var(--radius-sm)] bg-[var(--line)]">
                {data.recent.map((r) => (
                  <Link
                    key={r.id}
                    href={`${base}/jobs/${r.id}`}
                    className="flex items-center justify-between gap-3 bg-[var(--panel)] px-3 py-2.5 transition-colors duration-150 hover:bg-[var(--panel-2)]"
                  >
                    <span className="flex min-w-0 items-center gap-2.5">
                      <span
                        className="size-2 shrink-0 rounded-full"
                        style={{ background: STATUS_TONE[r.status] ?? "var(--fg-faint)" }}
                        aria-hidden
                      />
                      <span className="truncate text-[13px] text-[var(--fg)]">
                        {r.name || t("dashboard.untitled")}
                      </span>
                      <span className="shrink-0 text-[11px] text-[var(--fg-faint)]">
                        {t(`job.${r.status}`)}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-3 text-[11px]">
                      <span className="tabular-nums text-[var(--fg-muted)]">
                        {t("dashboard.signCount", { count: n(r.total) })}
                      </span>
                      {r.created_at && (
                        <span className="hidden text-[var(--fg-faint)] sm:inline">
                          {new Date(r.created_at).toLocaleDateString(locale)}
                        </span>
                      )}
                    </span>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-[var(--fg-muted)]">{t("dashboard.empty")}</p>
            )}
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
