"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Unauthorized,
  getStats,
  logout,
  me,
  type Account,
  type Stats,
} from "../lib/api";
import { API_BASE } from "../lib/api";
import {
  IconAlert,
  IconChart,
  IconFlag,
  IconLayers,
  IconMoon,
  IconPin,
  IconSettings,
  IconSun,
} from "./icons";

export type Theme = "dark" | "light";

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (localStorage.getItem("mithra-theme") as Theme | null) ?? "dark";
    setThemeState(stored);
    document.documentElement.dataset.theme = stored;
  }, []);

  function setTheme(next: Theme) {
    setThemeState(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("mithra-theme", next);
    } catch {
      /* private mode — the in-memory theme still applies */
    }
  }

  return [theme, setTheme];
}

type Section = {
  href: string;
  key: "dashboard" | "surveys" | "signs" | "review" | "settings";
  icon: typeof IconLayers;
  /** Which live number belongs beside this section, if any. */
  badge?: (s: Stats) => number;
};

const SECTIONS: Section[] = [
  { href: "", key: "dashboard", icon: IconChart },
  { href: "/surveys", key: "surveys", icon: IconLayers, badge: (s) => s.surveys.running },
  { href: "/signs", key: "signs", icon: IconPin, badge: (s) => s.signs.total },
  { href: "/label", key: "review", icon: IconFlag, badge: (s) => s.signs.needs_review },
  { href: "/settings", key: "settings", icon: IconSettings },
];

/**
 * The app shell.
 *
 * Navigation lives in a rail rather than in the page, because the sections are
 * different questions about the same inventory — what was surveyed, what was
 * found, what is unsure, how it is configured — and moving between them should
 * not feel like leaving the tool. Badges carry live counts so the rail also
 * reports state: a running survey and a growing review queue are both visible
 * without opening anything.
 */
export function AppShell({
  title,
  subtitle,
  actions,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [theme, setTheme] = useTheme();
  const [stats, setStats] = useState<Stats | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [offline, setOffline] = useState(false);

  // The shell is the guard: any page wrapped in it requires a session, and an
  // expired one sends the operator to sign in rather than showing empty panels
  // that look like a data problem.
  useEffect(() => {
    let cancelled = false;
    me()
      .then((user) => {
        if (!cancelled) setAccount(user);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof Unauthorized) {
          router.replace(`/${locale}/login`);
          return;
        }
        // Not an auth problem — the API could not be reached at all. Saying so
        // is the difference between "still loading" and "nothing is coming".
        setOffline(true);
      });
    return () => {
      cancelled = true;
    };
  }, [locale, router]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const next = await getStats();
        if (!cancelled) {
          setStats(next);
          setOffline(false);
        }
      } catch (e) {
        if (e instanceof Unauthorized) router.replace(`/${locale}/login`);
        else if (!cancelled) setOffline(true);
      }
    }
    load();
    const timer = setInterval(load, 8000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [locale, router]);

  const other = locale === "fa" ? "en" : "fa";
  const switchedPath = (() => {
    const segments = pathname.split("/");
    if (segments[1] === "fa" || segments[1] === "en") segments[1] = other;
    return segments.join("/") || `/${other}`;
  })();

  const base = `/${locale}`;

  return (
    <div className="flex h-dvh">
      <nav
        aria-label={t("nav.label")}
        className="flex w-[68px] shrink-0 flex-col items-center gap-1 border-e border-[var(--line)] bg-[var(--panel)] py-3 lg:w-[196px] lg:items-stretch lg:px-3"
      >
        <Link
          href={base}
          className="group mb-3 flex items-center gap-2.5 px-1 lg:px-1.5"
          aria-label={t("app.name")}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden className="shrink-0">
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
          <span className="hidden text-[15px] font-semibold tracking-tight lg:inline">
            {t("app.name")}
          </span>
        </Link>

        {SECTIONS.map(({ href, key, icon: Icon, badge }) => {
          const target = `${base}${href}`;
          const active =
            href === "" ? pathname === base || pathname === `${base}/` : pathname.startsWith(target);
          const count = stats && badge ? badge(stats) : 0;

          return (
            <Link
              key={key}
              href={target}
              aria-current={active ? "page" : undefined}
              title={t(`nav.${key}`)}
              className="flex items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 py-2 transition-colors duration-150"
              style={{
                background: active ? "var(--panel-2)" : undefined,
                color: active ? "var(--fg)" : "var(--fg-muted)",
              }}
            >
              <span className="relative shrink-0">
                <Icon size={17} />
                {/* On the collapsed rail the badge becomes a dot: the number has
                    nowhere to go, but "there is something here" still matters. */}
                {count > 0 && (
                  <span
                    className="absolute -end-1 -top-1 size-1.5 rounded-full lg:hidden"
                    style={{ background: "var(--accent)" }}
                    aria-hidden
                  />
                )}
              </span>
              <span className="hidden min-w-0 flex-1 truncate text-[13px] lg:inline">
                {t(`nav.${key}`)}
              </span>
              {count > 0 && (
                <span className="hidden shrink-0 rounded-full bg-[var(--panel-2)] px-1.5 text-[11px] text-[var(--fg-muted)] lg:inline">
                  {count.toLocaleString(locale)}
                </span>
              )}
            </Link>
          );
        })}

        <div className="flex-1" />

        {account && (
          <div className="mb-2 hidden min-w-0 px-1.5 lg:block">
            <div className="truncate text-[12px] text-[var(--fg)]">
              {account.name || account.email}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="truncate text-[10px] text-[var(--fg-faint)]">
                {t(`auth.role.${account.role}`)}
              </span>
              <button
                onClick={async () => {
                  await logout().catch(() => undefined);
                  router.replace(`/${locale}/login`);
                }}
                className="text-[10px] text-[var(--fg-faint)] underline-offset-2 hover:text-[var(--danger)] hover:underline transition-colors duration-150"
              >
                {t("auth.signOut")}
              </button>
            </div>
          </div>
        )}

        <div className="flex flex-col items-center gap-1 lg:flex-row lg:items-center lg:justify-between lg:px-1">
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={t("a11y.toggleTheme")}
            className="grid size-8 place-items-center rounded-[var(--radius-sm)] text-[var(--fg-muted)] hover:bg-[var(--panel-2)] hover:text-[var(--fg)] transition-colors duration-150"
          >
            {theme === "dark" ? <IconSun size={16} /> : <IconMoon size={16} />}
          </button>
          <Link
            href={switchedPath}
            className="rounded-[var(--radius-sm)] border border-[var(--line)] px-2 py-1 text-[11px] font-medium text-[var(--fg-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors duration-150"
          >
            {other === "fa" ? "فا" : "EN"}
          </Link>
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        {offline && (
          <div
            role="alert"
            className="flex items-center gap-2 border-b border-[var(--line)] bg-[var(--panel-2)] px-4 py-2 text-[12px]"
            style={{ color: "var(--danger)" }}
          >
            <IconAlert size={13} className="shrink-0" />
            {t("error.offline", { api: API_BASE })}
          </div>
        )}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--line)] bg-[var(--panel)] px-4">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] text-[var(--fg)]">{title}</div>
            {subtitle && (
              <div className="truncate text-[11px] text-[var(--fg-faint)]">{subtitle}</div>
            )}
          </div>
          {actions}
        </header>

        {children}
      </div>
    </div>
  );
}
