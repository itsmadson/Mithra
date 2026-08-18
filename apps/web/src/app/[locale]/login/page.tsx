"use client";

import Image from "next/image";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IconAlert } from "../../../components/icons";
import { Unauthorized, login, registerAccount, setupState } from "../../../lib/api";

/**
 * Sign in, or create the first account.
 *
 * A fresh deployment has no accounts, so a login form would be a door nobody
 * can open. The screen asks the API which state it is in and becomes a setup
 * form when the instance is empty — that first account is the administrator.
 */
export default function LoginPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();

  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setupState()
      .then(({ needs_setup }) => setNeedsSetup(needs_setup))
      .catch(() => setNeedsSetup(false));
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (needsSetup) await registerAccount(email, password, name);
      else await login(email, password);
      router.replace(`/${locale}`);
    } catch (e) {
      // A 401 from the login endpoint means the credentials were wrong, not
      // that a session expired, so it gets its own wording rather than the
      // generic "sign in again" the rest of the app shows.
      if (e instanceof Unauthorized) setError(t("auth.badCredentials"));
      else setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center p-6">
      <div className="w-full max-w-sm">
        {/* Sign-in is the one screen with room for the full mark, and the
            first thing anyone sees. The rail shows the reduced one because it
            has twenty-six pixels; this has ninety. */}
        <div className="mb-7 flex flex-col items-center gap-3">
          <Image
            src="/brand/logo.png"
            alt=""
            width={90}
            height={90}
            priority
            className="brand-mark"
          />
          <span className="text-[19px] font-semibold tracking-tight">{t("app.name")}</span>
        </div>

        <form
          onSubmit={submit}
          className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-5 shadow-[var(--shadow-lg)]"
        >
          <h1 className="text-sm font-semibold">
            {needsSetup ? t("auth.setupTitle") : t("auth.signInTitle")}
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-[var(--fg-muted)]">
            {needsSetup ? t("auth.setupHelp") : t("auth.signInHelp")}
          </p>

          {needsSetup && (
            <label className="mt-4 block">
              <span className="text-xs text-[var(--fg-faint)]">{t("auth.name")}</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                className="mt-1 w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 text-[13px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
              />
            </label>
          )}

          <label className="mt-4 block">
            <span className="text-xs text-[var(--fg-faint)]">{t("auth.email")}</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              dir="ltr"
              className="mt-1 w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 text-[13px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
            />
          </label>

          <label className="mt-3 block">
            <span className="text-xs text-[var(--fg-faint)]">{t("auth.password")}</span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={needsSetup ? "new-password" : "current-password"}
              dir="ltr"
              className="mt-1 w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2 text-[13px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
            />
            {needsSetup && (
              <span className="mt-1 block text-[11px] text-[var(--fg-faint)]">
                {t("auth.passwordHint")}
              </span>
            )}
          </label>

          {error && (
            <p className="mt-3 flex items-start gap-1.5 text-[11px] text-[var(--danger)]">
              <IconAlert size={12} className="mt-px shrink-0" />
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || needsSetup === null}
            className="mt-4 w-full rounded-[var(--radius-sm)] bg-[var(--accent)] px-3 py-2.5 text-[13px] font-semibold text-[var(--accent-ink)] transition-[opacity,transform] duration-150 hover:opacity-90 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy
              ? t("auth.working")
              : needsSetup
                ? t("auth.createAccount")
                : t("auth.signIn")}
          </button>
        </form>
      </div>
    </main>
  );
}
