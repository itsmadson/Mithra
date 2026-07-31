"use client";

import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { TopBar, useTheme } from "../../components/Shell";
import { IconAlert, IconTarget } from "../../components/icons";
import { createJob, type Bbox } from "../../lib/api";

const BboxMap = dynamic(() => import("../../components/BboxMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-[var(--panel-2)]" />,
});

const MAX_SIDE_DEGREES = 0.5;

/** Rough ground area, good enough to warn before a job is submitted. */
function areaKm2([w, s, e, n]: Bbox) {
  const latKm = (n - s) * 111.32;
  const lonKm = (e - w) * 111.32 * Math.cos(((n + s) / 2) * (Math.PI / 180));
  return Math.abs(latKm * lonKm);
}

export default function HomePage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [theme, setTheme] = useTheme();

  const [bbox, setBbox] = useState<Bbox | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tooLarge = useMemo(
    () =>
      bbox
        ? bbox[2] - bbox[0] > MAX_SIDE_DEGREES || bbox[3] - bbox[1] > MAX_SIDE_DEGREES
        : false,
    [bbox],
  );

  async function submit() {
    if (!bbox || tooLarge) return;
    setBusy(true);
    setError(null);
    try {
      const job = await createJob(bbox);
      router.push(`/${locale}/jobs/${job.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="flex h-dvh flex-col">
      <TopBar
        theme={theme}
        setTheme={setTheme}
        title={t("home.heading")}
        subtitle={t("app.tagline")}
      />

      <div className="relative min-h-0 flex-1">
        <BboxMap value={bbox} onChange={setBbox} theme={theme} key={theme} />

        {/* The control card floats over the map rather than sitting beside it:
            selecting an area is a map gesture, and the readout belongs next to
            the thing being measured. */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 p-3 sm:inset-auto sm:bottom-4 sm:start-4 sm:w-[320px] sm:p-0">
          <div className="pointer-events-auto rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-3.5 shadow-[var(--shadow-lg)]">
            {!bbox ? (
              <div className="flex items-start gap-2.5">
                <IconTarget size={16} className="mt-0.5 shrink-0 text-[var(--accent)]" />
                <p className="text-[13px] leading-relaxed text-[var(--fg-muted)]">
                  {t("home.help")}
                </p>
              </div>
            ) : (
              <>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-xs text-[var(--fg-faint)]">
                    {t("home.selected")}
                  </span>
                  <span className="text-xs text-[var(--fg-muted)] tabular-nums">
                    {areaKm2(bbox).toFixed(2)} {t("home.km2")}
                  </span>
                </div>
                <code className="mt-1.5 block text-[11px] leading-relaxed text-[var(--fg-faint)]">
                  {bbox.map((v) => v.toFixed(4)).join(", ")}
                </code>

                {tooLarge && (
                  <p className="mt-2.5 flex items-start gap-1.5 text-[11px] text-[var(--warn)]">
                    <IconAlert size={12} className="mt-px shrink-0" />
                    {t("home.tooLarge")}
                  </p>
                )}

                <div className="mt-3 flex gap-2">
                  <button
                    onClick={submit}
                    disabled={busy || tooLarge}
                    className="flex-1 rounded-[var(--radius-sm)] bg-[var(--accent)] px-3 py-2 text-[13px] font-semibold text-[var(--accent-ink)] transition-[opacity,transform] duration-150 hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {busy ? t("home.submitting") : t("home.submit")}
                  </button>
                  <button
                    onClick={() => setBbox(null)}
                    className="rounded-[var(--radius-sm)] border border-[var(--line)] px-3 py-2 text-[13px] text-[var(--fg-muted)] transition-colors duration-150 hover:border-[var(--line-strong)] hover:text-[var(--fg)]"
                  >
                    {t("home.clear")}
                  </button>
                </div>
              </>
            )}

            {error && (
              <p className="mt-2.5 flex items-start gap-1.5 text-[11px] text-[var(--danger)]">
                <IconAlert size={12} className="mt-px shrink-0" />
                {error}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
