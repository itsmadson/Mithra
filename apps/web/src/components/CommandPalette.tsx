"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { IconArrowRight, IconSearch } from "./icons";

/**
 * Everything the console can do, one keystroke away.
 *
 * An operator who runs a hundred surveys a week stops reading navigation and
 * starts reaching for the shortest path. ⌘K is that path, and it is the
 * difference between a tool somebody uses all day and a site somebody visits:
 * the whole application becomes typeable, including the places nested two
 * screens deep.
 *
 * Matching is subsequence-based, so "inv" finds Inventory and "nr" finds Needs
 * review — nobody types a full label into a command bar.
 */

export type Command = {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void;
};

/** "nr" matches "Needs review": every letter present, in order. */
function matches(query: string, text: string): boolean {
  if (!query) return true;
  const haystack = text.toLowerCase();
  let index = 0;
  for (const char of query.toLowerCase()) {
    index = haystack.indexOf(char, index);
    if (index === -1) return false;
    index += 1;
  }
  return true;
}

export function CommandPalette({
  extraCommands = [],
  onToggleTheme,
}: {
  extraCommands?: Command[];
  onToggleTheme: () => void;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const go = useCallback(
    (path: string) => () => router.push(`/${locale}${path}`),
    [router, locale],
  );

  const commands: Command[] = useMemo(
    () => [
      { id: "dashboard", label: t("nav.dashboard"), group: t("command.go"), run: go("") },
      { id: "detect", label: t("nav.detect"), group: t("command.go"), run: go("/detect") },
      { id: "surveys", label: t("nav.surveys"), group: t("command.go"), run: go("/surveys") },
      { id: "inventory", label: t("nav.inventory"), group: t("command.go"), run: go("/inventory") },
      { id: "review", label: t("nav.review"), group: t("command.go"), run: go("/label") },
      { id: "settings", label: t("nav.settings"), group: t("command.go"), run: go("/settings") },
      ...extraCommands,
      {
        id: "theme",
        label: t("command.toggleTheme"),
        group: t("command.act"),
        run: onToggleTheme,
      },
      {
        id: "language",
        label: t("command.switchLanguage"),
        hint: locale === "fa" ? "English" : "فارسی",
        group: t("command.act"),
        run: () => {
          // Replace only the locale segment, so the operator stays on the page
          // they were reading rather than being sent to the dashboard.
          const rest = window.location.pathname.split("/").slice(2).join("/");
          router.push(`/${locale === "fa" ? "en" : "fa"}${rest ? `/${rest}` : ""}`);
        },
      },
    ],
    [t, go, extraCommands, onToggleTheme, locale, router],
  );

  const filtered = useMemo(
    () => commands.filter((command) => matches(query, `${command.label} ${command.group}`)),
    [commands, query],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((v) => !v);
        setQuery("");
        setCursor(0);
      }
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${cursor}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!open) return null;

  function runAt(index: number) {
    const command = filtered[index];
    if (!command) return;
    setOpen(false);
    command.run();
  }

  let lastGroup = "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[12vh] backdrop-blur-[2px]"
      onClick={() => setOpen(false)}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("command.title")}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--panel)] shadow-[var(--shadow-lg)]"
      >
        <div className="flex items-center gap-2 border-b border-[var(--line)] px-3">
          <IconSearch size={14} className="shrink-0 text-[var(--fg-faint)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setCursor((c) => Math.min(c + 1, filtered.length - 1));
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              }
              if (event.key === "Enter") {
                event.preventDefault();
                runAt(cursor);
              }
            }}
            placeholder={t("command.placeholder")}
            className="w-full bg-transparent py-3 text-[13.5px] text-[var(--fg)] placeholder:text-[var(--fg-faint)] focus:outline-none"
          />
          <kbd className="shrink-0 rounded border border-[var(--line)] px-1.5 py-0.5 text-[10px] text-[var(--fg-faint)]">
            esc
          </kbd>
        </div>

        <div ref={listRef} className="max-h-80 overflow-y-auto py-1.5">
          {filtered.length === 0 && (
            <p className="px-3.5 py-6 text-center text-[12.5px] text-[var(--fg-muted)]">
              {t("command.noMatch", { query })}
            </p>
          )}
          {filtered.map((command, index) => {
            const newGroup = command.group !== lastGroup;
            lastGroup = command.group;
            return (
              <div key={command.id}>
                {newGroup && (
                  <p className="px-3.5 pb-1 pt-2.5 text-[10px] font-medium uppercase tracking-[0.06em] text-[var(--fg-faint)]">
                    {command.group}
                  </p>
                )}
                <button
                  data-index={index}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => runAt(index)}
                  className="flex w-full items-center gap-2.5 px-3.5 py-2 text-start text-[13px] transition-colors duration-100"
                  style={{
                    background: index === cursor ? "var(--panel-2)" : undefined,
                    color: index === cursor ? "var(--fg)" : "var(--fg-muted)",
                  }}
                >
                  <span className="flex-1 truncate">{command.label}</span>
                  {command.hint && (
                    <span className="shrink-0 text-[11px] text-[var(--fg-faint)]">
                      {command.hint}
                    </span>
                  )}
                  <IconArrowRight
                    size={12}
                    className={`shrink-0 transition-opacity ${index === cursor ? "opacity-100" : "opacity-0"}`}
                  />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
