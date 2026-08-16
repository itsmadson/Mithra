"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import type { Facets, InventoryQuery } from "../lib/api";
import { catalogueLabel, domainColor, humanise } from "../lib/targets";
import { IconClose } from "./icons";

/**
 * The filter rail.
 *
 * Every option here is a count from the data rather than an entry from the
 * catalogue: seventy-one possible classes listed as checkboxes is a catalogue
 * of the software, while seven classes with counts is a description of what was
 * actually found. Options that would return nothing are not offered.
 */
export function InventoryFilters({
  facets,
  query,
  onChange,
  loading,
}: {
  facets: Facets | null;
  query: InventoryQuery;
  onChange: (next: InventoryQuery) => void;
  loading: boolean;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const [expanded, setExpanded] = useState(false);

  const classes = facets?.classes ?? [];
  const shown = expanded ? classes : classes.slice(0, 8);
  const chosen = new Set(query.classes ?? []);

  function toggleClass(key: string) {
    const next = new Set(chosen);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange({ ...query, classes: [...next], offset: 0 });
  }

  const activeCount =
    (query.classes?.length ?? 0) +
    (query.needsReview ? 1 : 0) +
    (query.runId ? 1 : 0) +
    (query.detector ? 1 : 0) +
    (query.minConfidence !== undefined ? 1 : 0);

  return (
    <aside className="flex w-56 shrink-0 flex-col gap-5 overflow-y-auto border-e border-[var(--line)] p-3.5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--fg-faint)]">
          {t("inventory.filters")}
        </h2>
        {activeCount > 0 && (
          <button
            onClick={() => onChange({ q: query.q, sort: query.sort, direction: query.direction })}
            className="flex items-center gap-1 text-[11px] text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)]"
          >
            <IconClose size={10} />
            {t("inventory.clear")}
          </button>
        )}
      </div>

      {/* Review state, first: it is the only filter that maps to a decision
          somebody has to make rather than to a property of the data. */}
      <div className="grid gap-1">
        <FilterRow
          label={t("inventory.everything")}
          count={facets?.total}
          active={query.needsReview === undefined}
          onClick={() => onChange({ ...query, needsReview: undefined, offset: 0 })}
          loading={loading}
        />
        <FilterRow
          label={t("inventory.needsReview")}
          count={facets?.needs_review}
          active={query.needsReview === true}
          onClick={() => onChange({ ...query, needsReview: true, offset: 0 })}
          loading={loading}
          tone="warn"
        />
      </div>

      <div>
        <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--fg-faint)]">
          {t("inventory.class")}
        </h3>
        <div className="grid gap-0.5">
          {shown.map((facet) => (
            <FilterRow
              key={facet.key}
              label={
                // Catalogue first, then the message file for the classes that
                // predate it, then the tidied key.
                catalogueLabel(facet, locale === "fa") ??
                (t.has(`classes.${facet.key}`) ? t(`classes.${facet.key}`) : humanise(facet.key))
              }
              count={facet.count}
              active={chosen.has(facet.key)}
              onClick={() => toggleClass(facet.key)}
              loading={loading}
              dot={domainColor(facet.domain)}
            />
          ))}
          {classes.length === 0 && !loading && (
            <p className="text-[11px] text-[var(--fg-faint)]">{t("inventory.noClasses")}</p>
          )}
        </div>
        {classes.length > 8 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="mt-1.5 text-[11px] text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)]"
          >
            {expanded
              ? t("inventory.showFewer")
              : t("inventory.showAll", { count: classes.length })}
          </button>
        )}
      </div>

      {(facets?.runs.length ?? 0) > 1 && (
        <div>
          <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--fg-faint)]">
            {t("inventory.run")}
          </h3>
          <div className="grid gap-0.5">
            {facets!.runs.slice(0, 6).map((facet) => (
              <FilterRow
                key={facet.key}
                label={facet.label || t("inventory.untitledRun")}
                count={facet.count}
                active={query.runId === facet.key}
                onClick={() =>
                  onChange({
                    ...query,
                    runId: query.runId === facet.key ? undefined : facet.key,
                    offset: 0,
                  })
                }
                loading={loading}
              />
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--fg-faint)]">
          {t("inventory.minConfidence")}
        </h3>
        <input
          type="range"
          min={0}
          max={95}
          step={5}
          value={(query.minConfidence ?? 0) * 100}
          onChange={(event) => {
            const value = Number(event.target.value) / 100;
            onChange({ ...query, minConfidence: value === 0 ? undefined : value, offset: 0 });
          }}
          className="w-full accent-[var(--accent)]"
          dir={locale === "fa" ? "rtl" : "ltr"}
        />
        <p className="text-[11px] tabular-nums text-[var(--fg-muted)]">
          {query.minConfidence === undefined
            ? t("inventory.anyConfidence")
            : `≥ ${Math.round((query.minConfidence ?? 0) * 100)}%`}
        </p>
      </div>
    </aside>
  );
}

function FilterRow({
  label,
  count,
  active,
  onClick,
  loading,
  dot,
  tone,
}: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
  loading: boolean;
  dot?: string;
  tone?: "warn";
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className="flex items-center justify-between gap-2 rounded-[var(--radius-sm)] px-2 py-1.5 text-start text-[12.5px] transition-colors duration-150 hover:bg-[var(--panel-2)] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[var(--accent)]"
      style={{
        background: active ? "var(--panel-2)" : undefined,
        color: active ? "var(--fg)" : "var(--fg-muted)",
      }}
    >
      <span className="flex min-w-0 items-center gap-1.5">
        {dot && (
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ background: dot }}
            aria-hidden
          />
        )}
        <span className="truncate">{label}</span>
      </span>
      <span
        className="shrink-0 tabular-nums text-[11px]"
        style={{
          color: tone === "warn" && (count ?? 0) > 0 ? "var(--warn)" : "var(--fg-faint)",
          // A count that is still loading fades rather than disappearing, so
          // the row does not change width as numbers arrive.
          opacity: loading ? 0.4 : 1,
        }}
      >
        {count?.toLocaleString() ?? "—"}
      </span>
    </button>
  );
}
