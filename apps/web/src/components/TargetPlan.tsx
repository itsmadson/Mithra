"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { getPlan, type DetectionPlan } from "../lib/api";
import { IconAlert, IconClose } from "./icons";

/**
 * How this object would actually be detected.
 *
 * The question behind picking a target is never "is it in the list". It is
 * "from what imagery, by which model, and how well" — and answering it before
 * the run is the difference between a tool and a slot machine.
 */
export function TargetPlan({ target, onClose }: { target: string; onClose: () => void }) {
  const t = useTranslations();
  const locale = useLocale();
  const fa = locale === "fa";
  const [plan, setPlan] = useState<DetectionPlan | null>(null);

  useEffect(() => {
    setPlan(null);
    getPlan(target).then(setPlan).catch(() => setPlan(null));
  }, [target]);

  if (!plan) return null;

  const usableSources = plan.sources.filter((s) => s.usable);

  return (
    <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel-2)] p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold">{fa ? plan.label_fa : plan.label_en}</h3>
          <p className="mt-0.5 text-[11px] text-[var(--fg-faint)]" dir="ltr">
            {t.has(`domains.${plan.domain}`) ? t(`domains.${plan.domain}`) : plan.domain} ·{" "}
            {plan.geometry} · ≤ {plan.min_gsd_m} m/px ·{" "}
            {plan.viewpoints.join(" + ")}
          </p>
        </div>
        <button onClick={onClose} aria-label={t("plan.close")} className="shrink-0 text-[var(--fg-faint)] hover:text-[var(--fg)]">
          <IconClose size={13} />
        </button>
      </div>

      {plan.notes_en && (
        <p className="mt-2 text-[11px] leading-relaxed text-[var(--fg-muted)]">{plan.notes_en}</p>
      )}

      {/* Which imagery can see this at all. */}
      <p className="mt-3 text-[10px] font-medium uppercase tracking-wide text-[var(--fg-faint)]">
        {t("plan.sources")}
      </p>
      <div className="mt-1 flex flex-wrap gap-1">
        {usableSources.length === 0 && (
          <span className="text-[11px] text-[var(--warn)]">{t("plan.noSource")}</span>
        )}
        {usableSources.map((source) => (
          <span
            key={source.key}
            className="rounded-full border border-[var(--line)] px-2 py-0.5 text-[10px] text-[var(--fg-muted)]"
            title={`${source.gsd_m ?? "?"} m/px · ${source.viewpoint} · ${source.licence}`}
          >
            {fa ? source.label_fa : source.label_en}
            {source.imagery_kind === "unknown" && (
              // A tile service the operator has not yet classified: it may be a
              // drawn map, in which case nothing here will be found.
              <span className="ms-1 text-[var(--warn)]" title={t("plan.declareKind")}>
                ?
              </span>
            )}
          </span>
        ))}
      </div>

      {/* Which model, and the number that justifies it. */}
      <p className="mt-3 text-[10px] font-medium uppercase tracking-wide text-[var(--fg-faint)]">
        {t("plan.models")}
      </p>
      <div className="mt-1 grid gap-1.5">
        {plan.models.map((model) => (
          <div key={model.key} className="text-[11px] leading-relaxed">
            <span className="flex items-baseline justify-between gap-2">
              <span style={{ color: model.runnable_here ? "var(--fg)" : "var(--fg-faint)" }}>
                {model.label}
                {model.key === plan.recommended.detector && (
                  <span className="ms-1.5 text-[10px] text-[var(--accent)]">
                    {t("plan.chosen")}
                  </span>
                )}
              </span>
              {model.benchmark && (
                <span className="shrink-0 tabular-nums text-[var(--fg-muted)]" dir="ltr">
                  {model.benchmark.metric} {(model.benchmark.value * 100).toFixed(0)}%
                </span>
              )}
            </span>
            {model.benchmark && (
              <span className="block text-[10px] text-[var(--fg-faint)]" dir="ltr">
                {model.benchmark.dataset}
                {/* A generalist's number was earned on another class; saying so
                    stops it reading as evidence for this one. */}
                {!model.benchmark.measures_this_target && ` — ${t("plan.otherTask")}`}
              </span>
            )}
            {!model.runnable_here && (
              <span className="block text-[10px] text-[var(--warn)]">{model.reason}</span>
            )}
          </div>
        ))}
      </div>

      {plan.recommended.detector === null && (
        <p className="mt-2 flex items-start gap-1.5 text-[11px] text-[var(--warn)]">
          <IconAlert size={12} className="mt-px shrink-0" />
          {plan.recommended.evidence}
        </p>
      )}
    </div>
  );
}
