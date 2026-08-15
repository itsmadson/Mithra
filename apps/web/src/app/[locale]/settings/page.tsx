"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { AppShell } from "../../../components/AppShell";
import { ServerCapability } from "../../../components/ServerCapability";
import { IconAlert } from "../../../components/icons";
import {
  API_BASE,
  getStats,
  listAccounts,
  me,
  registerAccount,
  updateAccount,
  createBasemap,
  deleteBasemap,
  listBasemaps,
  updateBasemap,
  type Account,
  type Basemap,
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
  // Numbers follow the page's language: the rail already renders Persian
  // digits, and one panel disagreeing reads as a different system.
  const locale = useLocale();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [accountError, setAccountError] = useState<string | null>(null);
  const [basemaps, setBasemaps] = useState<Basemap[]>([]);
  const [mapName, setMapName] = useState("");
  const [mapUrl, setMapUrl] = useState("");
  const [mapTint, setMapTint] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const refreshBasemaps = () =>
    listBasemaps()
      .then(({ items }) => setBasemaps(items))
      .catch(() => undefined);

  useEffect(() => {
    refreshBasemaps();
  }, []);

  async function addBasemap(event: React.FormEvent) {
    event.preventDefault();
    setMapError(null);
    try {
      await createBasemap({ name: mapName, url_template: mapUrl, tint: mapTint });
      setMapName("");
      setMapUrl("");
      setMapTint(false);
      await refreshBasemaps();
    } catch (e) {
      setMapError(e instanceof Error ? e.message : String(e));
    }
  }

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
              {stats?.features.total.toLocaleString(locale) ?? "—"}
            </Row>
            <Row label={t("settings.totalSurveys")}>
              {stats?.surveys.total.toLocaleString(locale) ?? "—"}
            </Row>
            <Row label={t("settings.needsReview")}>
              {stats?.features.needs_review.toLocaleString(locale) ?? "—"}
            </Row>
            <Row label={t("settings.unclassified")}>
              {stats?.features.unclassified.toLocaleString(locale) ?? "—"}
            </Row>
            <Row label={t("settings.labels")}>
              {stats?.labels.total.toLocaleString(locale) ?? "—"}
            </Row>
          </Card>

          <Card title={t("settings.byClass")}>
            {stats && (
              <div className="mt-2 space-y-2">
                {Object.entries(stats.features.by_class).map(([cls, count]) => {
                  const share = stats.features.total > 0 ? (count / stats.features.total) * 100 : 0;
                  return (
                    <div key={cls}>
                      <div className="flex items-baseline justify-between text-[12px]">
                        <span className="text-[var(--fg-muted)]">
                          {t(`classes.${cls}`)}
                        </span>
                        <span className="text-[var(--fg)]">
                          {count.toLocaleString(locale)} · {share.toLocaleString(locale, { maximumFractionDigits: 0 })}%
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

          <ServerCapability />

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

          <Card title={t("basemap.title")}>
            <p className="mb-3 text-xs leading-relaxed text-[var(--fg-muted)]">
              {t("basemap.help")}
            </p>

            {basemaps.map((row) => (
              <div
                key={row.id}
                className="flex items-center justify-between gap-3 border-b border-[var(--line)] py-2.5 last:border-0"
              >
                <span className="min-w-0">
                  <span className="block truncate text-[13px] text-[var(--fg)]">
                    {row.name}
                    {row.is_default && (
                      <span className="ms-2 text-[10px] text-[var(--accent)]">
                        {t("basemap.default")}
                      </span>
                    )}
                  </span>
                  <code className="block truncate text-[11px] text-[var(--fg-faint)]" dir="ltr">
                    {row.url_template}
                  </code>
                </span>
                {account?.role === "admin" && (
                  <span className="flex shrink-0 items-center gap-2">
                    {!row.is_default && (
                      <button
                        onClick={() =>
                          updateBasemap(row.id, { is_default: true }).then(refreshBasemaps)
                        }
                        className="rounded-full border border-[var(--line)] px-2 py-0.5 text-[11px] text-[var(--fg-muted)] transition-colors duration-150 hover:border-[var(--accent)] hover:text-[var(--accent)]"
                      >
                        {t("basemap.makeDefault")}
                      </button>
                    )}
                    <button
                      onClick={() => deleteBasemap(row.id).then(refreshBasemaps)}
                      className="text-[11px] text-[var(--fg-faint)] transition-colors duration-150 hover:text-[var(--danger)]"
                    >
                      {t("basemap.remove")}
                    </button>
                  </span>
                )}
              </div>
            ))}

            {account?.role === "admin" ? (
              <form onSubmit={addBasemap} className="mt-3 grid gap-2">
                <div className="flex flex-wrap gap-2">
                  <input
                    required
                    value={mapName}
                    onChange={(e) => setMapName(e.target.value)}
                    placeholder={t("basemap.name")}
                    className="min-w-32 flex-1 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-1.5 text-[12px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
                  />
                  <input
                    required
                    dir="ltr"
                    value={mapUrl}
                    onChange={(e) => setMapUrl(e.target.value)}
                    placeholder="https://tiles.example.com/{z}/{x}/{y}.png"
                    className="min-w-64 flex-[2] rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
                  />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <label className="flex items-center gap-2 text-[11px] text-[var(--fg-muted)]">
                    <input
                      type="checkbox"
                      checked={mapTint}
                      onChange={(e) => setMapTint(e.target.checked)}
                      className="accent-[var(--accent)]"
                    />
                    {t("basemap.tint")}
                  </label>
                  <button
                    type="submit"
                    className="rounded-[var(--radius-sm)] border border-[var(--line)] px-3 py-1.5 text-[12px] text-[var(--fg-muted)] transition-colors duration-150 hover:border-[var(--accent)] hover:text-[var(--accent)]"
                  >
                    {t("basemap.add")}
                  </button>
                </div>
                {mapError && (
                  <p className="flex items-start gap-1.5 text-[11px] text-[var(--danger)]">
                    <IconAlert size={12} className="mt-px shrink-0" />
                    {mapError}
                  </p>
                )}
              </form>
            ) : (
              <p className="mt-2 text-[11px] text-[var(--fg-faint)]">
                {t("basemap.adminOnly")}
              </p>
            )}
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
                        ? new Date(row.last_login_at).toLocaleString(locale)
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
