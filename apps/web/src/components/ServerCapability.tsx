"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { getCapability, type SystemCapability } from "../lib/api";
import { IconAlert, IconChart } from "./icons";

/**
 * What this server can do — stated before anyone starts a run.
 *
 * The same build behaves differently on a laptop and on a GPU host, and the
 * difference is not speed: a detector that needs 8 GB of VRAM does not run
 * slowly without one, it does not run. An operator who is not told discovers
 * that an hour in.
 */
export function ServerCapability() {
  const t = useTranslations();
  const locale = useLocale();
  const [cap, setCap] = useState<SystemCapability | null>(null);

  useEffect(() => {
    getCapability().then(setCap).catch(() => setCap(null));
  }, []);

  if (!cap) return null;

  const { machine } = cap;
  const runnable = cap.detectors.filter((d) => d.runnable);
  const blocked = cap.detectors.filter((d) => !d.runnable && d.implemented);
  const tone =
    machine.tier === "gpu"
      ? "var(--c-city)"
      : machine.tier === "modest"
        ? "var(--warn)"
        : "var(--ai)";

  return (
    <section className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-[13px] font-semibold">{t("capability.title")}</h2>
        <span className="text-[11px] font-medium" style={{ color: tone }}>
          {t(`capability.tier.${machine.tier}`)}
        </span>
      </div>

      <p className="mt-1 text-[11px] leading-relaxed text-[var(--fg-muted)]" dir="ltr">
        {machine.cpu_count} CPU · {machine.ram_gb} GB RAM
        {machine.has_gpu ? ` · ${machine.gpu_name} ${machine.vram_gb} GB` : ` · ${t("capability.noGpu")}`}
      </p>

      <div className="mt-3 grid gap-1.5">
        {cap.detectors
          .filter((d) => d.implemented)
          .map((detector) => (
            <div
              key={detector.key}
              className="flex items-start justify-between gap-3 border-b border-[var(--line)] pb-1.5 text-[12px] last:border-0"
            >
              <span className="min-w-0">
                <span className="block truncate" style={{ color: detector.runnable ? "var(--fg)" : "var(--fg-faint)" }}>
                  {detector.label}
                </span>
                {/* The evidence for the claim, next to the claim. */}
                {detector.benchmark && (
                  <span className="block text-[10px] text-[var(--fg-faint)]" dir="ltr">
                    {detector.benchmark.metric} {(detector.benchmark.value * 100).toFixed(0)}% ·{" "}
                    {detector.benchmark.dataset}
                  </span>
                )}
                {!detector.runnable && (
                  <span className="block text-[10px] leading-relaxed text-[var(--warn)]">
                    {detector.reason}
                  </span>
                )}
              </span>
              <span
                className="shrink-0 rounded-full border px-1.5 text-[10px]"
                style={{
                  borderColor: detector.runnable ? "var(--line)" : "var(--warn)",
                  color: detector.runnable ? "var(--fg-muted)" : "var(--warn)",
                }}
              >
                {detector.runnable
                  ? detector.speed === "slow"
                    ? t("capability.slow")
                    : t("capability.ready")
                  : t("capability.needsBetter")}
              </span>
            </div>
          ))}
      </div>

      {blocked.length > 0 && (
        <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--fg-muted)]">
          <IconAlert size={12} className="mt-px shrink-0 text-[var(--warn)]" />
          {t("capability.moveToGpu", { count: blocked.length.toLocaleString(locale) })}
        </p>
      )}
      {blocked.length === 0 && runnable.length > 0 && (
        <p className="mt-3 flex items-start gap-1.5 text-[11px] text-[var(--fg-muted)]">
          <IconChart size={12} className="mt-px shrink-0" />
          {t("capability.allReady")}
        </p>
      )}
    </section>
  );
}
