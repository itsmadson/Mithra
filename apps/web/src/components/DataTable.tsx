"use client";

import { useEffect, useRef } from "react";
import { IconSortAsc, IconSortDesc, IconSortNone } from "./icons";

/**
 * The table an inventory is actually read in.
 *
 * Operators work down a list of hundreds of rows comparing values in a column,
 * which is the one thing a stack of cards cannot do: a column is only scannable
 * if every value starts at the same x. Everything here serves that — fixed
 * alignment, tabular figures, a row height tight enough to hold twenty rows on
 * screen, and a header that says which way it is sorted rather than making you
 * infer it from the data.
 *
 * Selection and sorting are controlled by the caller, because both belong to
 * the query that produced the rows: sorting a page of a hundred rows in the
 * browser reorders a hundred rows and calls it the top of the list.
 */

export type Column<T> = {
  key: string;
  header: string;
  /** Server-side sort key. Omit for a column that cannot be sorted. */
  sortKey?: string;
  /** Right-aligned for measurements, so digits line up on the decimal. */
  numeric?: boolean;
  width?: string;
  render: (row: T) => React.ReactNode;
};

export type SortState = { key: string; direction: "asc" | "desc" };

export function DataTable<T extends { id: string }>({
  rows,
  columns,
  sort,
  onSort,
  selected,
  onSelect,
  activeId,
  onActivate,
  density = "comfortable",
  emptyState,
  loading = false,
  labels,
}: {
  rows: T[];
  columns: Column<T>[];
  sort?: SortState;
  onSort?: (sort: SortState) => void;
  selected?: Set<string>;
  onSelect?: (next: Set<string>) => void;
  activeId?: string | null;
  onActivate?: (row: T) => void;
  density?: "compact" | "comfortable";
  emptyState?: React.ReactNode;
  loading?: boolean;
  labels: { selectAll: string; selectRow: string; sortedBy: string };
}) {
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  const rowPadding = density === "compact" ? "py-[5px]" : "py-2";

  // Keep the active row in view when it is changed from outside the table —
  // from the map, or from arrow keys — so selection never scrolls off screen
  // silently.
  useEffect(() => {
    if (!activeId || !bodyRef.current) return;
    const el = bodyRef.current.querySelector<HTMLElement>(`[data-row-id="${activeId}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  const allSelected = selected && rows.length > 0 && rows.every((r) => selected.has(r.id));
  const someSelected = selected && rows.some((r) => selected.has(r.id));

  function toggleAll() {
    if (!onSelect || !selected) return;
    const next = new Set(selected);
    if (allSelected) rows.forEach((r) => next.delete(r.id));
    else rows.forEach((r) => next.add(r.id));
    onSelect(next);
  }

  function toggleRow(id: string) {
    if (!onSelect || !selected) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelect(next);
  }

  function headerClick(column: Column<T>) {
    if (!column.sortKey || !onSort) return;
    const isCurrent = sort?.key === column.sortKey;
    onSort({
      key: column.sortKey,
      // A new column starts descending: the first question about a measurement
      // is almost always "what is the biggest".
      direction: isCurrent && sort?.direction === "desc" ? "asc" : "desc",
    });
  }

  return (
    <div className="relative h-full overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead className="sticky top-0 z-10">
          <tr className="bg-[var(--panel)]">
            {selected && (
              <th scope="col" className="w-9 border-b border-[var(--line)] px-2.5">
                <input
                  type="checkbox"
                  aria-label={labels.selectAll}
                  checked={Boolean(allSelected)}
                  ref={(el) => {
                    // Indeterminate is a property, not an attribute: a partial
                    // selection that renders as unchecked invites you to click
                    // once and silently deselect everything.
                    if (el) el.indeterminate = Boolean(someSelected && !allSelected);
                  }}
                  onChange={toggleAll}
                  className="size-3.5 accent-[var(--accent)]"
                />
              </th>
            )}
            {columns.map((column) => {
              const active = sort?.key === column.sortKey;
              const Icon = !active ? IconSortNone : sort?.direction === "desc" ? IconSortDesc : IconSortAsc;
              return (
                <th
                  key={column.key}
                  scope="col"
                  style={{ width: column.width }}
                  aria-sort={
                    active ? (sort?.direction === "desc" ? "descending" : "ascending") : undefined
                  }
                  className={`border-b border-[var(--line)] px-2.5 py-2 text-[10.5px] font-medium uppercase tracking-[0.06em] text-[var(--fg-faint)] ${
                    column.numeric ? "text-end" : "text-start"
                  }`}
                >
                  {column.sortKey ? (
                    <button
                      onClick={() => headerClick(column)}
                      className={`inline-flex items-center gap-1 transition-colors duration-150 hover:text-[var(--fg)] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[var(--accent)] ${
                        column.numeric ? "flex-row-reverse" : ""
                      } ${active ? "text-[var(--fg)]" : ""}`}
                      title={active ? `${labels.sortedBy} ${column.header}` : column.header}
                    >
                      {column.header}
                      <Icon size={10} className={active ? "opacity-100" : "opacity-40"} />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>

        <tbody ref={bodyRef}>
          {rows.map((row) => {
            const isActive = row.id === activeId;
            const isSelected = selected?.has(row.id);
            return (
              <tr
                key={row.id}
                data-row-id={row.id}
                tabIndex={0}
                onClick={() => onActivate?.(row)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onActivate?.(row);
                  }
                  // Arrow keys walk the list without leaving the keyboard, which
                  // is how a review session of four hundred rows is survivable.
                  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                    event.preventDefault();
                    const sibling =
                      event.key === "ArrowDown"
                        ? event.currentTarget.nextElementSibling
                        : event.currentTarget.previousElementSibling;
                    (sibling as HTMLElement | null)?.focus();
                  }
                }}
                className="cursor-pointer border-b border-[var(--line)]/60 transition-colors duration-100 hover:bg-[var(--panel-2)] focus:outline-none focus-visible:bg-[var(--panel-2)] focus-visible:outline focus-visible:-outline-offset-1 focus-visible:outline-[var(--accent)]"
                style={{
                  background: isActive
                    ? "color-mix(in oklab, var(--accent) 12%, transparent)"
                    : isSelected
                      ? "var(--panel-2)"
                      : undefined,
                }}
              >
                {selected && (
                  <td className="px-2.5" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={labels.selectRow}
                      checked={Boolean(isSelected)}
                      onChange={() => toggleRow(row.id)}
                      className="size-3.5 accent-[var(--accent)]"
                    />
                  </td>
                )}
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`px-2.5 ${rowPadding} ${
                      column.numeric ? "text-end tabular-nums" : "text-start"
                    }`}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>

      {loading && rows.length === 0 && <TableSkeleton columns={columns.length + 1} />}
      {!loading && rows.length === 0 && emptyState}
    </div>
  );
}

/**
 * Rows that are the shape of the answer, not a spinner.
 *
 * A spinner says "something is happening somewhere"; this says "a table is
 * coming, this wide, with this many rows", so the layout does not jump when the
 * data lands.
 */
export function TableSkeleton({ columns, rows = 12 }: { columns: number; rows?: number }) {
  return (
    <div className="px-2.5 py-1" aria-hidden>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div
          key={rowIndex}
          className="flex items-center gap-3 border-b border-[var(--line)]/40 py-2.5"
          style={{ opacity: Math.max(0.12, 1 - rowIndex / rows) }}
        >
          {Array.from({ length: columns }).map((__, cellIndex) => (
            <div
              key={cellIndex}
              className="h-2.5 rounded-full bg-[var(--line)]"
              style={{ width: cellIndex === 0 ? "14px" : `${9 - (cellIndex % 4)}%` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
