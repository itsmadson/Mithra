"use client";

import { useTranslations } from "next-intl";
import { SIGN_CLASSES, type JobStatus, type FeatureClass } from "../lib/api";
import { CLASS_COLOR, colorForClass } from "../lib/signClass";

const SIGN_ORDER: string[] = [...SIGN_CLASSES, "unknown"];

/**
 * The classes this run actually looked for.
 *
 * A sign survey shows all five sign classes even at zero, because a missing
 * row there would read as "not measured" rather than "measured, none found".
 * A water run must not show them at all: five empty sign rows above a lake
 * count is not a legend, it is noise from a different question.
 */
function classesFor(job: JobStatus): string[] {
  const found = Object.keys(job.counts ?? {});
  const isSignSurvey = found.every((c) => SIGN_ORDER.includes(c));
  return isSignSurvey ? SIGN_ORDER : found;
}

/**
 * Legend and filter are the same control. A separate legend would be a second
 * thing to read that does nothing; making the swatches toggle means the key to
 * the map is also how you interrogate it.
 */
export default function ClassFilter({
  job,
  active,
  onToggle,
  onOnly,
}: {
  job: JobStatus;
  active: Set<string>;
  onToggle: (cls: string) => void;
  onOnly: (cls: string) => void;
}) {
  const t = useTranslations();

  return (
    <ul data-testid="class-filter" className="space-y-0.5">
      {classesFor(job).map((cls) => {
        const count = job.counts[cls] ?? 0;
        const on = active.has(cls);
        const share = job.total > 0 ? (count / job.total) * 100 : 0;

        return (
          <li key={cls}>
            <button
              onClick={() => onToggle(cls)}
              onDoubleClick={() => onOnly(cls)}
              aria-pressed={on}
              title={t("filter.hint")}
              className="group relative w-full text-start rounded-[var(--radius-sm)] px-2.5 py-2 hover:bg-[var(--panel-2)] transition-colors duration-150"
            >
              {/* The bar is the count, drawn behind the row rather than beside
                  it — the proportions read instantly without a chart. */}
              <span
                className="absolute inset-y-0 start-0 rounded-[var(--radius-sm)] transition-[width] duration-500 ease-out"
                style={{
                  width: `${share}%`,
                  background: colorForClass(cls),
                  opacity: on ? 0.13 : 0.05,
                }}
                aria-hidden
              />
              <span className="relative flex items-center gap-2.5">
                <span
                  className="size-2.5 rounded-full shrink-0 transition-opacity duration-150"
                  style={{
                    background: colorForClass(cls),
                    opacity: on ? 1 : 0.3,
                    boxShadow: on ? `0 0 0 3px color-mix(in oklab, ${colorForClass(cls)} 20%, transparent)` : "none",
                  }}
                  aria-hidden
                />
                <span
                  className="text-[13px] flex-1 truncate transition-colors duration-150"
                  style={{ color: on ? "var(--fg)" : "var(--fg-faint)" }}
                >
                  {t.has(`classes.${cls}`) ? t(`classes.${cls}`) : cls}
                </span>
                <span
                  className="text-[13px] font-semibold tabular-nums transition-colors duration-150"
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
  );
}
