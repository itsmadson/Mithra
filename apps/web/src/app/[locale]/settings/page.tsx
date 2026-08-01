"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { AppShell } from "../../../components/AppShell";
import { IconAlert } from "../../../components/icons";
import {
  API_BASE,
  getStats,
  listAccounts,
  me,
  registerAccount,
  updateAccount,
  type Account,
  type Stats,
} from "../../../lib/api";
import { CLASS_COLOR } from "../../../lib/signClass";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-[var(--line)] py-2.5 last:border-0">
      <span className="text-[13px] text-[var(--fg-muted)]">{label}</span>
      <span className="text-end text-[13px] text-[var(--fg)]">{children}</span>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-4">
      <h2 className="mb-1 text-[13px] font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/**
 * What the system is currently doing and what it is made of.
 *
 * Read-only on purpose. Everything here is set by environment or by the
 * pipeline, and a settings page that pretends to own values it does not
 * control is worse than one that states where they come from.
 */
export default function SettingsPage() {
  const t = useTranslations();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [accountError, setAccountError] = useState<string | null>(null);

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    me().then(setAccount).catch(() => undefined);
  }, []);

  // Account management is administrator-only, so the list is fetched only for
  // administrators; a 403 here would be noise for everyone else.
  useEffect(() => {
    if (account?.role !== "admin") return;
    listAccounts()
      .then(({ items }) => setAccounts(items))
      .catch(() => setAccounts(null));
  }, [account]);

  async function createAccount(event: React.FormEvent) {
    event.preventDefault();
    setAccountError(null);
    try {
      await registerAccount(newEmail, newPassword);
      setNewEmail("");
      setNewPassword("");
      const { items } = await listAccounts();
      setAccounts(items);
    } catch (e) {
      setAccountError(e instanceof Error ? e.message : String(e));
    }
  }

  async function toggleAccount(target: Account) {
    try {
      await updateAccount(target.id, { is_active: !target.is_active });
      const { items } = await listAccounts();
      setAccounts(items);
    } catch (e) {
      setAccountError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <AppShell title={t("nav.settings")} subtitle={t("settings.subtitle")}>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mx-auto grid max-w-3xl gap-4">
          {error && (
            <p className="flex items-start gap-2 text-xs text-[var(--danger)]">
              <IconAlert size={13} className="mt-px shrink-0" />
              {error}
            </p>
          )}

          <Card title={t("settings.inventory")}>
            <Row label={t("settings.totalSigns")}>
              {stats?.signs.total.toLocaleString() ?? "—"}
            </Row>
            <Row label={t("settings.totalSurveys")}>
              {stats?.surveys.total.toLocaleString() ?? "—"}
            </Row>
            <Row label={t("settings.needsReview")}>
              {stats?.signs.needs_review.toLocaleString() ?? "—"}
            </Row>
            <Row label={t("settings.unclassified")}>
              {stats?.signs.unclassified.toLocaleString() ?? "—"}
            </Row>
            <Row label={t("settings.labels")}>
              {stats?.labels.total.toLocaleString() ?? "—"}
            </Row>
          </Card>

          <Card title={t("settings.byClass")}>
            {stats && (
              <div className="mt-2 space-y-2">
                {Object.entries(stats.signs.by_class).map(([cls, count]) => {
                  const share = stats.signs.total > 0 ? (count / stats.signs.total) * 100 : 0;
                  return (
                    <div key={cls}>
                      <div className="flex items-baseline justify-between text-[12px]">
                        <span className="text-[var(--fg-muted)]">
                          {t(`classes.${cls}`)}
                        </span>
                        <span className="text-[var(--fg)]">
                          {count} · {share.toFixed(0)}%
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-[var(--panel-2)]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${share}%`,
                            background: CLASS_COLOR[cls as keyof typeof CLASS_COLOR],
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          <Card title={t("settings.models")}>
            <p className="mb-2 text-xs leading-relaxed text-[var(--fg-muted)]">
              {t("settings.modelsHelp")}
            </p>
            {stats?.models.length ? (
              stats.models.map((version) => (
                <Row key={version} label={t("settings.modelVersion")}>
                  <code className="text-[11px]">{version}</code>
                </Row>
              ))
            ) : (
              <Row label={t("settings.modelVersion")}>—</Row>
            )}
          </Card>

          <Card title={t("settings.data")}>
            <p className="mb-2 text-xs leading-relaxed text-[var(--fg-muted)]">
              {t("settings.dataHelp")}
            </p>
            <Row label="API">
              <code className="text-[11px]">{API_BASE}</code>
            </Row>
            <Row label={t("settings.imagery")}>Mapillary</Row>
            <Row label={t("settings.basemap")}>OpenStreetMap</Row>
            <Row label={t("settings.geocoder")}>Nominatim · Overpass</Row>
          </Card>

          {account?.role === "admin" && (
            <Card title={t("auth.accounts")}>
              <p className="mb-3 text-xs leading-relaxed text-[var(--fg-muted)]">
                {t("auth.accountsHelp")}
              </p>

              {accounts?.map((row) => (
                <div
                  key={row.id}
                  className="flex items-center justify-between gap-3 border-b border-[var(--line)] py-2.5 last:border-0"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] text-[var(--fg)]">
                      {row.name || row.email}
                    </span>
                    <span className="block truncate text-[11px] text-[var(--fg-faint)]">
                      {t(`auth.role.${row.role}`)} ·{" "}
                      {row.last_login_at
                        ? new Date(row.last_login_at).toLocaleString()
                        : t("auth.never")}
                    </span>
                  </span>
                  <button
                    onClick={() => toggleAccount(row)}
                    disabled={row.id === account.id}
                    className="shrink-0 rounded-full border px-2 py-0.5 text-[11px] transition-colors duration-150 disabled:opacity-40"
                    style={{
                      borderColor: row.is_active ? "var(--line)" : "var(--warn)",
                      color: row.is_active ? "var(--fg-muted)" : "var(--warn)",
                    }}
                  >
                    {row.is_active ? t("auth.active") : t("auth.disabled")}
                  </button>
                </div>
              ))}

              <form onSubmit={createAccount} className="mt-3 flex flex-wrap gap-2">
                <input
                  type="email"
                  required
                  dir="ltr"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder={t("auth.email")}
                  className="min-w-0 flex-1 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-1.5 text-[12px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
                />
                <input
                  type="password"
                  required
                  dir="ltr"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={t("auth.password")}
                  className="min-w-0 flex-1 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-1.5 text-[12px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
                />
                <button
                  type="submit"
                  className="rounded-[var(--radius-sm)] border border-[var(--line)] px-3 py-1.5 text-[12px] text-[var(--fg-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors duration-150"
                >
                  {t("auth.createAccount")}
                </button>
              </form>

              {accountError && (
                <p className="mt-2 flex items-start gap-1.5 text-[11px] text-[var(--danger)]">
                  <IconAlert size={12} className="mt-px shrink-0" />
                  {accountError}
                </p>
              )}
            </Card>
          )}

          <Card title={t("settings.limits")}>
            <p className="text-xs leading-relaxed text-[var(--fg-muted)]">
              {t("settings.limitsBody")}
            </p>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
