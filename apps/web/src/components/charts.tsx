"use client";

import { useLocale } from "next-intl";
import { useState } from "react";

/**
 * Chart primitives, in plain SVG.
 *
 * No charting library: these are four shapes, and a dependency that ships a
 * canvas renderer and its own theme system to draw them would cost more than
 * it saves — including in bundle size on a dashboard operators open all day.
 *
 * Every mark is thin, every grid line is recessive, and every chart carries a
 * hover layer, because a chart on screen that cannot be interrogated is a
 * picture of data rather than a view of it.
 */

function useFormat() {
  const locale = useLocale();
  return (n: number) => n.toLocaleString(locale);
}

/**
 * A percentage in the page's own convention — Persian gets ٪, not %.
 *
 * Built through Intl rather than concatenated, because a bare "%" glued to a
 * Persian numeral is both the wrong sign and a bidirectional hazard.
 */
function usePercent() {
  const locale = useLocale();
  return (fraction: number, digits = 0) =>
    new Intl.NumberFormat(locale, {
      style: "percent",
      maximumFractionDigits: digits,
    }).format(fraction);
}

/**
 * A single number that answers one question.
 *
 * Not every figure deserves a chart. A total, a share, a backlog: these are
 * read, not compared, and a number set large is the honest form for them.
 */
export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
  spark,
}: {
  label: string;
  value: string;
  hint?: string;
  /** Status is reserved for state, never reused to make a tile look lively. */
  tone?: "neutral" | "good" | "warn" | "danger";
  spark?: number[];
}) {
  const color =
    tone === "good"
      ? "var(--c-city)"
      : tone === "warn"
        ? "var(--warn)"
        : tone === "danger"
          ? "var(--danger)"
          : "var(--fg)";

  return (
    <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-4">
      <div className="text-[11px] font-medium uppercase tracking-wide text-[var(--fg-faint)]">
        {label}
      </div>
      <div
        className="mt-1.5 text-[26px] font-semibold leading-none tabular-nums tracking-tight"
        style={{ color }}
      >
        {value}
      </div>
      {hint && <div className="mt-1.5 text-[11px] text-[var(--fg-muted)]">{hint}</div>}
      {spark && spark.length > 1 && <Sparkline values={spark} />}
    </div>
  );
}

/** Shape only — no axis, no labels. It says "rising" or "quiet", nothing more. */
function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  const w = 100;
  const h = 22;
  const step = w / (values.length - 1);
  const points = values.map((v, i) => `${i * step},${h - (v / max) * h}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="mt-2.5 h-6 w-full"
      aria-hidden
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

export type Point = { date: string; count: number };

/**
 * One series over time, as an area with a 2px line.
 *
 * A crosshair rather than per-point dots: thirty points would be thirty
 * targets competing with the line they describe.
 */
export function TimeSeries({
  points,
  label,
  height = 160,
}: {
  points: Point[];
  label: string;
  height?: number;
}) {
  const format = useFormat();
  const locale = useLocale();
  const [hover, setHover] = useState<number | null>(null);

  if (points.length === 0) return null;

  const max = Math.max(...points.map((p) => p.count), 1);
  const w = 600;
  const h = height;
  const padTop = 12;
  const padBottom = 22;
  const plot = h - padTop - padBottom;
  const step = points.length > 1 ? w / (points.length - 1) : w;

  const xy = (p: Point, i: number) => [i * step, padTop + plot - (p.count / max) * plot];
  const line = points.map((p, i) => xy(p, i).join(",")).join(" ");
  const area = `${line} ${w},${padTop + plot} 0,${padTop + plot}`;

  const active = hover === null ? null : points[hover];

  return (
    <div className="relative">
      {/* The ceiling, level with the top gridline, so a height reads as a
          quantity rather than a shape. */}
      {/* Backed by the surface: a peak reaching the ceiling passes under this
          label, and an unbacked number on top of the line is unreadable. */}
      <span className="absolute start-0 top-0 rounded-[3px] bg-[var(--panel)] px-1 text-[10px] tabular-nums text-[var(--fg-faint)]">
        {format(max)}
      </span>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height }}
        role="img"
        aria-label={label}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const ratio = (e.clientX - box.left) / box.width;
          setHover(Math.min(points.length - 1, Math.max(0, Math.round(ratio * (points.length - 1)))));
        }}
      >
        {/* Recessive baseline and midline: enough to read height against. */}
        {[0, 0.5, 1].map((f) => (
          <line
            key={f}
            x1="0"
            x2={w}
            y1={padTop + plot * f}
            y2={padTop + plot * f}
            stroke="var(--line)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        <polygon points={area} fill="var(--accent)" opacity="0.12" />
        <polyline
          points={line}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {hover !== null && (
          <>
            <line
              x1={hover * step}
              x2={hover * step}
              y1={padTop}
              y2={padTop + plot}
              stroke="var(--fg-faint)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
            <circle
              cx={xy(points[hover], hover)[0]}
              cy={xy(points[hover], hover)[1]}
              r="4"
              fill="var(--accent)"
              stroke="var(--panel)"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
          </>
        )}
      </svg>

      <div className="mt-1 flex items-baseline justify-between text-[10px] text-[var(--fg-faint)]">
        <span>{new Date(points[0].date).toLocaleDateString(locale)}</span>
        <span>{new Date(points[points.length - 1].date).toLocaleDateString(locale)}</span>
      </div>

      {active && (
        <div className="pointer-events-none absolute start-2 top-2 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2 py-1 text-[11px] shadow-[var(--shadow-lg)]">
          <span className="text-[var(--fg-muted)]">
            {new Date(active.date).toLocaleDateString(locale)}
          </span>{" "}
          <span className="font-semibold tabular-nums text-[var(--fg)]">
            {format(active.count)}
          </span>
        </div>
      )}
    </div>
  );
}

export type Bucket = { from: number; to: number; count: number };

/**
 * The confidence histogram.
 *
 * The review threshold is drawn as a line across it, because the shape only
 * means something next to the cut: everything left of it is work waiting for a
 * person.
 */
export function Histogram({
  buckets,
  threshold,
  label,
  belowLabel,
}: {
  buckets: Bucket[];
  threshold: number;
  label: string;
  belowLabel: string;
}) {
  const locale = useLocale();
  const format = useFormat();
  const decimal = (v: number) =>
    v.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...buckets.map((b) => b.count), 1);

  return (
    <div>
      <span className="mb-1 block text-[10px] tabular-nums text-[var(--fg-faint)]">
        {format(max)}
      </span>
      <div className="relative flex h-[150px] items-end gap-[2px]" role="img" aria-label={label}>
        {buckets.map((b, i) => {
          const below = b.to <= threshold;
          return (
            <div
              key={i}
              className="relative flex-1"
              style={{ height: "100%" }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              <div className="absolute inset-x-0 bottom-0 flex flex-col justify-end" style={{ height: "100%" }}>
                <div
                  className="rounded-t-[4px] transition-[opacity] duration-150"
                  style={{
                    height: `${(b.count / max) * 100}%`,
                    minHeight: b.count > 0 ? 2 : 0,
                    // Turquoise is the palette's mark for what the model
                    // produced; gold means a person still has to act. Both
                    // being gold made the threshold invisible.
                    background: below ? "var(--warn)" : "var(--ai)",
                    opacity: hover === null || hover === i ? 1 : 0.45,
                  }}
                />
              </div>
            </div>
          );
        })}

        {hover !== null && (
          <div className="pointer-events-none absolute start-0 top-0 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2 py-1 text-[11px] shadow-[var(--shadow-lg)]">
            <span className="text-[var(--fg-muted)] tabular-nums">
              {decimal(buckets[hover].from)}–{decimal(buckets[hover].to)}
            </span>{" "}
            <span className="font-semibold tabular-nums text-[var(--fg)]">
              {format(buckets[hover].count)}
            </span>
          </div>
        )}
      </div>

      <div className="mt-1.5 flex items-center justify-between text-[10px] text-[var(--fg-faint)]">
        <span className="tabular-nums">{decimal(0)}</span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2 rounded-[2px]" style={{ background: "var(--warn)" }} />
          {belowLabel}
        </span>
        <span className="tabular-nums">{decimal(1)}</span>
      </div>
    </div>
  );
}

/**
 * Parts of one whole, as a single stacked bar with a real legend.
 *
 * Not a pie: five slices of similar size cannot be ranked by eye, and the
 * question here is "how much of the inventory is each class", which a length
 * answers and an angle does not.
 */
export function StackedShare({
  parts,
}: {
  parts: { key: string; label: string; value: number; color: string }[];
}) {
  const format = useFormat();
  const percent = usePercent();
  const [hover, setHover] = useState<string | null>(null);
  const total = parts.reduce((sum, p) => sum + p.value, 0) || 1;

  return (
    <div>
      {/* 2px surface gaps between segments: adjacent fills otherwise read as one. */}
      <div className="flex h-3 gap-[2px] overflow-hidden rounded-full">
        {parts.map((p) => (
          <div
            key={p.key}
            className="h-full transition-opacity duration-150 first:rounded-s-full last:rounded-e-full"
            style={{
              width: `${(p.value / total) * 100}%`,
              background: p.color,
              opacity: hover === null || hover === p.key ? 1 : 0.4,
            }}
            onMouseEnter={() => setHover(p.key)}
            onMouseLeave={() => setHover(null)}
            title={`${p.label}: ${format(p.value)}`}
          />
        ))}
      </div>

      <div className="mt-3 grid gap-1.5">
        {parts.map((p) => (
          <div
            key={p.key}
            className="flex items-baseline justify-between gap-3 text-[12px] transition-opacity duration-150"
            style={{ opacity: hover === null || hover === p.key ? 1 : 0.5 }}
            onMouseEnter={() => setHover(p.key)}
            onMouseLeave={() => setHover(null)}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="size-2 shrink-0 rounded-[2px]"
                style={{ background: p.color }}
                aria-hidden
              />
              <span className="truncate text-[var(--fg-muted)]">{p.label}</span>
            </span>
            <span className="flex shrink-0 items-baseline gap-1.5 tabular-nums text-[var(--fg)]">
              <bdi>{format(p.value)}</bdi>
              <span aria-hidden className="text-[var(--fg-faint)]">
                ·
              </span>
              <bdi className="text-[var(--fg-faint)]">{percent(p.value / total)}</bdi>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
