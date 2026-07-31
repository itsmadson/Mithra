"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { IconMoon, IconSun } from "./icons";

export type Theme = "dark" | "light";

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (localStorage.getItem("bina-theme") as Theme | null) ?? "dark";
    setThemeState(stored);
    document.documentElement.dataset.theme = stored;
  }, []);

  function setTheme(next: Theme) {
    setThemeState(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("bina-theme", next);
    } catch {
      /* private mode — the in-memory theme still applies */
    }
  }

  return [theme, setTheme];
}

/** Swaps the locale segment in place so the current job stays open. */
function useSwitchedPath(target: string) {
  const pathname = usePathname();
  const segments = pathname.split("/");
  if (segments[1] === "fa" || segments[1] === "en") segments[1] = target;
  return segments.join("/") || `/${target}`;
}

export function TopBar({
  title,
  subtitle,
  theme,
  setTheme,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  theme: Theme;
  setTheme: (t: Theme) => void;
  children?: React.ReactNode;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const other = locale === "fa" ? "en" : "fa";
  const switched = useSwitchedPath(other);

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--line)] bg-[var(--panel)] px-4">
      <Link
        href={`/${locale}`}
        className="flex items-center gap-2.5 shrink-0 group"
        aria-label={t("app.name")}
      >
        {/* The mark: an aperture ring around a pin dot — "bina" means seeing. */}
        <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
          <circle
            cx="12"
            cy="12"
            r="9"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="1.6"
            strokeDasharray="4 3.2"
            className="origin-center transition-transform duration-500 ease-out group-hover:rotate-45"
          />
          <circle cx="12" cy="12" r="3.4" fill="var(--accent)" />
        </svg>
        <span className="text-[15px] font-semibold tracking-tight">{t("app.name")}</span>
      </Link>

      <div className="mx-1 h-5 w-px bg-[var(--line)]" aria-hidden />

      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] text-[var(--fg)]">{title}</div>
        {subtitle && (
          <div className="truncate text-[11px] text-[var(--fg-faint)]">{subtitle}</div>
        )}
      </div>

      {children}

      <div className="flex items-center gap-1">
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={t("a11y.toggleTheme")}
          className="grid size-8 place-items-center rounded-[var(--radius-sm)] text-[var(--fg-muted)] hover:bg-[var(--panel-2)] hover:text-[var(--fg)] transition-colors duration-150"
        >
          {theme === "dark" ? <IconSun size={16} /> : <IconMoon size={16} />}
        </button>

        <Link
          href={switched}
          className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2.5 py-1 text-xs font-medium text-[var(--fg-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors duration-150"
        >
          {other === "fa" ? "فارسی" : "English"}
        </Link>
      </div>
    </header>
  );
}
