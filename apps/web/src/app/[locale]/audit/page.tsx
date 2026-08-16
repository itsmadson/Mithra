"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../../../components/AppShell";
import { DataTable, type Column } from "../../../components/DataTable";
import { IconAlert, IconClock, IconSearch } from "../../../components/icons";
import {
  getAuditActions,
  listAudit,
  type AuditActions,
  type AuditEvent,
} from "../../../lib/api";

const PAGE_SIZE = 100;

/**
 * Who did what, and when.
 *
 * The log exists for four or five questions that only ever get asked after
 * something has gone wrong — who started the run behind this number, who
 * overrode the model here, who disabled that account — so the screen is built
 * for looking one thing up rather than for browsing. Filter by person, filter
 * by action, read the detail.
 *
 * There is no way to edit or delete anything from here, and there is no route
 * behind it that could.
 */
export default function AuditPage() {
  const t = useTranslations();
  const locale = useLocale();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [facets, setFacets] = useState<AuditActions | null>(null);
  const [action, setAction] = useState<string>("");
  const [actor, setActor] = useState<string>("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search), 250);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listAudit({ action: action || undefined, actor: actor || undefined, q: query || undefined, limit: PAGE_SIZE, offset })
      .then((body) => {
        if (cancelled) return;
        setEvents(body.items);
        setTotal(body.total);
        setError(null);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [action, actor, query, offset]);

  useEffect(() => {
    getAuditActions().then(setFacets).catch(() => setFacets(null));
  }, []);

  // "auth.login" is one key, not two levels — next-intl reads a dot as
  // nesting, so the stored key uses an underscore and the action is mapped
  // here rather than showing a raw verb to a person.
  const actionLabel = useMemo(
    () => (action: string) => {
      const key = `audit.actions.${action.replace(/\./g, "_")}`;
      return t.has(key) ? t(key) : action;
    },
    [t],
  );

  const columns: Column<AuditEvent>[] = useMemo(
    () => [
      {
        key: "when",
        header: t("audit.when"),
        width: "168px",
        render: (row) => (
          <span className="whitespace-nowrap text-[var(--fg-muted)]" dir="ltr">
            {new Date(row.created_at).toLocaleString(locale === "fa" ? "fa-IR" : "en-GB")}
          </span>
        ),
      },
      {
        key: "actor",
        header: t("audit.actor"),
        width: "20%",
        render: (row) => (
          <span className="block truncate text-[var(--fg)]" dir="ltr">
            {row.actor_email}
          </span>
        ),
      },
      {
        key: "action",
        header: t("audit.action"),
        width: "22%",
        render: (row) => (
          <span className="flex items-center gap-2">
            <span
              className="size-1.5 shrink-0 rounded-full"
              style={{ background: toneFor(row.action) }}
              aria-hidden
            />
            <span className="truncate">
              {actionLabel(row.action)}
            </span>
          </span>
        ),
      },
      {
        key: "detail",
        header: t("audit.detail"),
        render: (row) => <Detail event={row} expanded={expanded === row.id} />,
      },
      {
        key: "ip",
        header: t("audit.from"),
        numeric: true,
        width: "132px",
        render: (row) => (
          <span className="whitespace-nowrap text-[11px] text-[var(--fg-faint)]" dir="ltr">
            {row.ip ?? "—"}
          </span>
        ),
      },
    ],
    [t, locale, expanded, actionLabel],
  );

  return (
    <AppShell
      title={t("audit.title")}
      subtitle={total === null ? t("audit.subtitle") : t("audit.count", { count: total.toLocaleString() })}
    >
      <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)]">
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] px-3 py-2">
          <div className="relative min-w-56 flex-1">
            <IconSearch
              size={13}
              className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-[var(--fg-faint)]"
            />
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
              placeholder={t("audit.searchPlaceholder")}
              className="w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] py-1.5 pe-3 ps-8 text-[12.5px] text-[var(--fg)] placeholder:text-[var(--fg-faint)] focus:border-[var(--accent)] focus:outline-none"
            />
          </div>

          <select
            value={action}
            onChange={(event) => {
              setAction(event.target.value);
              setOffset(0);
            }}
            className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2 py-1.5 text-[12.5px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
          >
            <option value="">{t("audit.allActions")}</option>
            {facets?.actions.map((item) => (
              <option key={item.key} value={item.key}>
                {actionLabel(item.key)} · {item.count}
              </option>
            ))}
          </select>

          <select
            value={actor}
            onChange={(event) => {
              setActor(event.target.value);
              setOffset(0);
            }}
            className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2 py-1.5 text-[12.5px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
            dir="ltr"
          >
            <option value="">{t("audit.allActors")}</option>
            {facets?.actors.map((item) => (
              <option key={item.key} value={item.key}>
                {item.key} · {item.count}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div className="flex items-start gap-2 border-b border-[var(--line)] bg-[color-mix(in_oklab,var(--danger)_12%,transparent)] px-3 py-2 text-[12px] text-[var(--danger)]">
            <IconAlert size={13} className="mt-px shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="min-h-0 flex-1">
          <DataTable
            rows={events}
            columns={columns}
            density="compact"
            loading={loading}
            activeId={expanded}
            onActivate={(row) => setExpanded((current) => (current === row.id ? null : row.id))}
            labels={{
              selectAll: "",
              selectRow: "",
              sortedBy: t("audit.newestFirst"),
            }}
            emptyState={
              <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-16 text-center">
                <IconClock size={22} className="text-[var(--fg-faint)]" />
                <p className="text-[13px]">{t("audit.empty")}</p>
                <p className="max-w-sm text-[12px] leading-relaxed text-[var(--fg-muted)]">
                  {t("audit.emptyHint")}
                </p>
              </div>
            }
          />
        </div>

        {(offset > 0 || (total !== null && offset + events.length < total)) && (
          <div className="flex items-center justify-between border-t border-[var(--line)] px-3 py-2 text-[12px]">
            <span className="tabular-nums text-[var(--fg-faint)]">
              {t("inventory.range", {
                from: (offset + 1).toLocaleString(),
                to: (offset + events.length).toLocaleString(),
                total: (total ?? 0).toLocaleString(),
              })}
            </span>
            <div className="flex gap-1.5">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1 text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)] disabled:opacity-40"
              >
                {t("inventory.previous")}
              </button>
              <button
                disabled={total === null || offset + events.length >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1 text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)] disabled:opacity-40"
              >
                {t("inventory.next")}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

/**
 * Colour by consequence, not by category.
 *
 * A failed sign-in and a deleted survey are the two rows somebody scanning this
 * log is looking for; everything else is context. Three tones, and the action
 * is always written out beside the dot.
 */
function toneFor(action: string): string {
  if (action.endsWith("_failed")) return "var(--warn)";
  if (action.endsWith(".deleted")) return "var(--danger)";
  if (action.startsWith("auth.")) return "var(--fg-faint)";
  return "var(--ai)";
}

/** The change itself, summarised in a line and expandable to the raw record. */
function Detail({ event, expanded }: { event: AuditEvent; expanded: boolean }) {
  const detail = event.detail;
  if (!detail) return <span className="text-[var(--fg-faint)]">—</span>;

  if (expanded) {
    return (
      <pre
        className="max-w-full overflow-x-auto whitespace-pre-wrap break-all text-[11px] leading-relaxed text-[var(--fg-muted)]"
        dir="ltr"
      >
        {JSON.stringify(detail, null, 1)}
      </pre>
    );
  }

  // A label override reads as a sentence, because that is what it is.
  if (typeof detail.from === "string" && typeof detail.to === "string") {
    return (
      <span className="flex items-center gap-1.5 truncate text-[var(--fg-muted)]">
        <span className="line-through opacity-70">{detail.from}</span>
        <span aria-hidden>→</span>
        <span className="text-[var(--fg)]">{detail.to}</span>
      </span>
    );
  }

  const summary = Object.entries(detail)
    .filter(([, value]) => value !== null && typeof value !== "object")
    .map(([key, value]) => `${key}: ${value}`)
    .join(" · ");

  return (
    <span className="block truncate text-[var(--fg-muted)]" title={summary}>
      {summary || JSON.stringify(detail).slice(0, 80)}
    </span>
  );
}
