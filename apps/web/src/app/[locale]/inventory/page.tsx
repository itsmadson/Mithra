"use client";

import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell, useTheme } from "../../../components/AppShell";
import { DataTable, type Column, type SortState } from "../../../components/DataTable";
import { InventoryFilters } from "../../../components/InventoryFilters";
import { BasemapPicker } from "../../../components/BasemapPicker";
import { useBasemap } from "../../../components/useBasemap";
import SignDetail from "../../../components/SignDetail";
import { useToast } from "../../../components/Toast";
import {
  IconAlert,
  IconClose,
  IconDatabase,
  IconDownload,
  IconSearch,
} from "../../../components/icons";
import {
  API_BASE,
  getFacets,
  listInventory,
  type Facets,
  type Feature,
  type InventoryQuery,
} from "../../../lib/api";
import { catalogueLabel, domainColor, formatArea, humanise } from "../../../lib/targets";

const InventoryMap = dynamic(() => import("../../../components/InventoryMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-[var(--panel-2)]" />,
});

const PAGE_SIZE = 100;

/**
 * The inventory: everything detected, across every run.
 *
 * This is the screen the product is for. It replaced a page that fetched two
 * thousand rows and filtered them in the browser — which worked until an
 * organisation had more than two thousand detections, at which point it started
 * quietly answering a different question than the one asked.
 *
 * Filter, sort and page all happen on the server, so the count in the corner is
 * the real count and "no results" means no results rather than none in the
 * first two thousand.
 */
export default function InventoryPage() {
  const t = useTranslations();
  const fa = useLocale() === "fa";
  const [theme] = useTheme();
  const toast = useToast();
  const { basemap, options: basemapOptions, selectedId: basemapId, select: selectBasemap } =
    useBasemap();

  const [query, setQuery] = useState<InventoryQuery>({ sort: "created_at", direction: "desc" });
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<Feature[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [density, setDensity] = useState<"compact" | "comfortable">("comfortable");
  const [showMap, setShowMap] = useState(true);
  const searchRef = useRef<HTMLInputElement>(null);

  // Typing must not fire a request per keystroke, and must not feel laggy
  // either: 250ms is under the threshold where a person notices waiting but
  // long enough that a typed word is one query rather than five.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery((q) => (q.q === (search || undefined) ? q : { ...q, q: search || undefined, offset: 0 }));
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([listInventory({ ...query, limit: PAGE_SIZE }), getFacets(query)])
      .then(([page, counts]) => {
        if (cancelled) return;
        setRows(page.items);
        setTotal(page.total);
        setFacets(counts);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  // "/" focuses search the way it does in every tool an operator already uses.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA";
      if (event.key === "/" && !typing) {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape" && !typing) setActiveId(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // The catalogue names most classes. The five original sign classes came
  // before it and are named in the message files instead, which is where they
  // have always been translated — falling through to the raw key would show a
  // Persian operator "street_name".
  const className = useCallback(
    (row: Feature) =>
      catalogueLabel(row, fa) ??
      (t.has(`classes.${row.class_name}`) ? t(`classes.${row.class_name}`) : humanise(row.class_name)),
    [fa, t],
  );

  const active = useMemo(() => rows.find((r) => r.id === activeId) ?? null, [rows, activeId]);
  const offset = query.offset ?? 0;

  const columns: Column<Feature>[] = useMemo(
    () => [
      {
        key: "class",
        header: t("inventory.columns.class"),
        sortKey: "class_name",
        render: (row) => (
          <span className="flex items-center gap-2">
            <span
              className="size-2.5 shrink-0 rounded-full"
              style={{ background: domainColor(row.domain) }}
              aria-hidden
            />
            <span className="truncate text-[var(--fg)]">{className(row)}</span>
            {row.needs_review && (
              <span
                className="shrink-0 rounded-full border border-[var(--warn)] px-1.5 py-px text-[10px] text-[var(--warn)]"
                title={t("inventory.needsReview")}
              >
                {t("inventory.unsureShort")}
              </span>
            )}
          </span>
        ),
      },
      {
        key: "confidence",
        header: t("inventory.columns.confidence"),
        sortKey: "confidence",
        numeric: true,
        width: "88px",
        render: (row) => (
          <span
            className="whitespace-nowrap"
            style={{
              // Low confidence is the number an operator is hunting for, so it
              // is the one that changes colour — not a badge on every row.
              color: row.confidence < 0.5 ? "var(--warn)" : "var(--fg-muted)",
            }}
          >
            <span dir="ltr">{Math.round(row.confidence * 100)}%</span>
          </span>
        ),
      },
      {
        key: "area",
        header: t("inventory.columns.area"),
        sortKey: "area_m2",
        numeric: true,
        width: "96px",
        render: (row) => (
          <span className="whitespace-nowrap text-[var(--fg-muted)]" dir="ltr">
            {formatArea(row.area_m2) ?? "—"}
          </span>
        ),
      },
      {
        key: "run",
        header: t("inventory.columns.run"),
        width: "22%",
        render: (row) => (
          <span className="block truncate text-[var(--fg-muted)]" title={row.run_name ?? ""}>
            {row.run_name || t("inventory.untitledRun")}
          </span>
        ),
      },
      {
        key: "model",
        header: t("inventory.columns.model"),
        width: "16%",
        render: (row) => (
          <span className="block truncate text-[var(--fg-faint)]" dir="ltr">
            {row.model_version ?? "—"}
          </span>
        ),
      },
      ...(showMap
        ? []
        : [
            {
              key: "where",
              header: t("inventory.columns.where"),
              numeric: true,
              width: "150px",
              render: (row: Feature) => (
                <span className="whitespace-nowrap text-[11px] text-[var(--fg-faint)]" dir="ltr">
                  {row.lat.toFixed(4)}, {row.lon.toFixed(4)}
                </span>
              ),
            },
          ]),
    ],
    [t, fa, showMap, className],
  );

  const exportUrl = useMemo(() => {
    const params = new URLSearchParams();
    for (const cls of query.classes ?? []) params.append("class_name", cls);
    if (query.needsReview !== undefined) params.set("needs_review", String(query.needsReview));
    if (query.runId) params.set("run_id", query.runId);
    if (query.q) params.set("q", query.q);
    if (query.minConfidence !== undefined) params.set("min_confidence", String(query.minConfidence));
    return `${API_BASE}/api/features/export.csv?${params}`;
  }, [query]);

  const shown = rows.length;
  const rangeLabel =
    total === null
      ? ""
      : total === 0
        ? t("inventory.noneFound")
        : t("inventory.range", {
            from: (offset + 1).toLocaleString(),
            to: (offset + shown).toLocaleString(),
            total: total.toLocaleString(),
          });

  return (
    <AppShell
      title={t("nav.inventory")}
      subtitle={rangeLabel}
      actions={
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setDensity((d) => (d === "compact" ? "comfortable" : "compact"))}
            className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1.5 text-[12px] text-[var(--fg-muted)] transition-colors hover:border-[var(--line-strong)] hover:text-[var(--fg)]"
          >
            {density === "compact" ? t("inventory.comfortable") : t("inventory.compact")}
          </button>
          <button
            onClick={() => setShowMap((v) => !v)}
            aria-pressed={showMap}
            className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1.5 text-[12px] transition-colors hover:border-[var(--line-strong)]"
            style={{ color: showMap ? "var(--accent)" : "var(--fg-muted)" }}
          >
            {t("inventory.map")}
          </button>
          <a
            href={exportUrl}
            className="flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--accent)] px-3 py-1.5 text-[12px] font-medium text-[var(--accent-ink)] transition-opacity hover:opacity-90"
          >
            <IconDownload size={13} />
            {t("inventory.export")}
          </a>
        </div>
      }
    >
      <div className="flex h-full min-h-0 overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)]">
        <InventoryFilters facets={facets} query={query} onChange={setQuery} loading={loading} />

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2">
            <div className="relative flex-1">
              <IconSearch
                size={13}
                className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-[var(--fg-faint)]"
              />
              <input
                ref={searchRef}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("inventory.searchPlaceholder")}
                className="w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] py-1.5 pe-8 ps-8 text-[12.5px] text-[var(--fg)] placeholder:text-[var(--fg-faint)] focus:border-[var(--accent)] focus:outline-none"
              />
              {search ? (
                <button
                  onClick={() => setSearch("")}
                  aria-label={t("inventory.clearSearch")}
                  className="absolute end-2 top-1/2 -translate-y-1/2 text-[var(--fg-faint)] hover:text-[var(--fg)]"
                >
                  <IconClose size={12} />
                </button>
              ) : (
                <kbd className="pointer-events-none absolute end-2 top-1/2 -translate-y-1/2 rounded border border-[var(--line)] px-1 text-[10px] text-[var(--fg-faint)]">
                  /
                </kbd>
              )}
            </div>
          </div>

          {selected.size > 0 && (
            <div className="flex items-center gap-3 border-b border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 text-[12px]">
              <span className="text-[var(--fg)]">
                {t("inventory.selected", { count: selected.size.toLocaleString() })}
              </span>
              <button
                onClick={() => {
                  const ids = [...selected];
                  navigator.clipboard
                    ?.writeText(ids.join("\n"))
                    .then(() => toast.show(t("inventory.copiedIds", { count: ids.length })))
                    .catch(() => toast.show(t("inventory.copyFailed"), "error"));
                }}
                className="text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)]"
              >
                {t("inventory.copyIds")}
              </button>
              <button
                onClick={() => setSelected(new Set())}
                className="ms-auto flex items-center gap-1 text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)]"
              >
                <IconClose size={11} />
                {t("inventory.clearSelection")}
              </button>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 border-b border-[var(--line)] bg-[color-mix(in_oklab,var(--danger)_12%,transparent)] px-3 py-2 text-[12px] text-[var(--danger)]">
              <IconAlert size={13} className="mt-px shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex min-h-0 flex-1">
            <div className="min-w-0 flex-1">
              <DataTable
                rows={rows}
                columns={columns}
                sort={{ key: query.sort ?? "created_at", direction: query.direction ?? "desc" }}
                onSort={(next: SortState) =>
                  setQuery((q) => ({
                    ...q,
                    sort: next.key as InventoryQuery["sort"],
                    direction: next.direction,
                    offset: 0,
                  }))
                }
                selected={selected}
                onSelect={setSelected}
                activeId={activeId}
                onActivate={(row) => setActiveId(row.id)}
                density={density}
                loading={loading}
                labels={{
                  selectAll: t("inventory.selectAll"),
                  selectRow: t("inventory.selectRow"),
                  sortedBy: t("inventory.sortedBy"),
                }}
                emptyState={<EmptyInventory hasFilters={Boolean(facets && facets.total === 0)} />}
              />
            </div>

            {showMap && (
              <div className="hidden w-[38%] min-w-[320px] border-s border-[var(--line)] lg:block">
                <div className="relative h-full">
                  <InventoryMap
                    features={rows}
                    theme={theme}
                    activeId={activeId}
                    onSelect={setActiveId}
                    basemap={basemap}
                  />
                  <BasemapPicker
                    options={basemapOptions}
                    selectedId={basemapId}
                    onSelect={selectBasemap}
                  />
                </div>
              </div>
            )}
          </div>

          <Pagination
            offset={offset}
            shown={shown}
            total={total}
            onChange={(next) => setQuery((q) => ({ ...q, offset: next }))}
            labels={{
              previous: t("inventory.previous"),
              next: t("inventory.next"),
              page: rangeLabel,
            }}
          />
        </div>

        {active && (
          <div className="hidden w-80 shrink-0 overflow-y-auto border-s border-[var(--line)] xl:block">
            <SignDetail sign={active} onClose={() => setActiveId(null)} />
          </div>
        )}
      </div>
    </AppShell>
  );
}

function Pagination({
  offset,
  shown,
  total,
  onChange,
  labels,
}: {
  offset: number;
  shown: number;
  total: number | null;
  onChange: (offset: number) => void;
  labels: { previous: string; next: string; page: string };
}) {
  const hasPrevious = offset > 0;
  const hasNext = total !== null && offset + shown < total;
  if (!hasPrevious && !hasNext) return null;
  return (
    <div className="flex items-center justify-between border-t border-[var(--line)] px-3 py-2 text-[12px]">
      <span className="tabular-nums text-[var(--fg-faint)]">{labels.page}</span>
      <div className="flex gap-1.5">
        <button
          disabled={!hasPrevious}
          onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}
          className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1 text-[var(--fg-muted)] transition-colors hover:border-[var(--line-strong)] hover:text-[var(--fg)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {labels.previous}
        </button>
        <button
          disabled={!hasNext}
          onClick={() => onChange(offset + PAGE_SIZE)}
          className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1 text-[var(--fg-muted)] transition-colors hover:border-[var(--line-strong)] hover:text-[var(--fg)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {labels.next}
        </button>
      </div>
    </div>
  );
}

/**
 * Nothing here — and which of the two reasons it is.
 *
 * An empty inventory and an over-tight filter look identical and need opposite
 * responses, so they are never shown the same message.
 */
function EmptyInventory({ hasFilters }: { hasFilters: boolean }) {
  const t = useTranslations();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <IconDatabase size={22} className="text-[var(--fg-faint)]" />
      <p className="text-[13px] text-[var(--fg)]">
        {hasFilters ? t("inventory.emptyAll") : t("inventory.emptyFiltered")}
      </p>
      <p className="max-w-sm text-[12px] leading-relaxed text-[var(--fg-muted)]">
        {hasFilters ? t("inventory.emptyAllHint") : t("inventory.emptyFilteredHint")}
      </p>
    </div>
  );
}
