"use client";

import { useTranslations } from "next-intl";
import { API_BASE, type Feature } from "../lib/api";
import { IconClose, IconExternal, IconFlag } from "./icons";
import {
  CLASS_COLOR,
  mapillaryCategory,
  mapillaryImageUrl,
  mapillaryName,
} from "../lib/signClass";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 border-b border-[var(--line)] last:border-0">
      <span className="text-xs text-[var(--fg-faint)] shrink-0">{label}</span>
      <span className="text-[13px] text-[var(--fg)] text-end break-words">{children}</span>
    </div>
  );
}

export default function SignDetail({
  sign,
  onClose,
}: {
  sign: Feature;
  onClose: () => void;
}) {
  const t = useTranslations();
  const color = CLASS_COLOR[sign.class_name];
  const sourceUrl = mapillaryImageUrl(sign.image_id);
  const category = mapillaryCategory(sign.source_value);
  const name = mapillaryName(sign.source_value);
  const pct = Math.round(sign.confidence * 100);

  return (
    <aside className="flex h-full flex-col bg-[var(--panel)]">
      <header className="flex items-center gap-3 px-4 py-3 border-b border-[var(--line)]">
        <span
          className="size-2.5 rounded-full shrink-0"
          style={{ background: color }}
          aria-hidden
        />
        <h2 className="text-sm font-semibold flex-1 truncate">
          {t(`classes.${sign.class_name}`)}
        </h2>
        <button
          onClick={onClose}
          aria-label={t("a11y.close")}
          className="text-[var(--fg-faint)] hover:text-[var(--fg)] transition-colors duration-150"
        >
          <IconClose size={18} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="p-4">
          {sign.crop_url ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={`${API_BASE}${sign.crop_url}`}
              alt={t("detail.cropAlt")}
              className="w-full rounded-[var(--radius)] border border-[var(--line-strong)] bg-[var(--panel-2)] object-contain max-h-64"
            />
          ) : (
            <div className="rounded-[var(--radius)] border border-dashed border-[var(--line-strong)] p-6 text-center text-xs text-[var(--fg-faint)]">
              {t("detail.noCrop")}
            </div>
          )}
        </div>

        <div className="px-4 pb-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs text-[var(--fg-faint)]">{t("detail.confidence")}</span>
            <span className="text-xs font-semibold" style={{ color }}>
              {pct}%
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-[var(--panel-2)] overflow-hidden">
            <div
              className="h-full rounded-full transition-[width] duration-300 ease-out"
              style={{ width: `${pct}%`, background: color }}
            />
          </div>
          {sign.needs_review && (
            <p className="mt-2.5 flex items-start gap-2 text-xs text-[var(--warn)]">
              <IconFlag size={14} className="mt-px shrink-0" />
              {t("detail.needsReview")}
            </p>
          )}
        </div>

        <section className="px-4 pb-4">
          <h3 className="text-[11px] uppercase tracking-wider text-[var(--fg-faint)] mb-1">
            {t("detail.evidence")}
          </h3>
          <p className="text-xs text-[var(--fg-muted)] leading-relaxed mb-3">
            {t("detail.evidenceHelp")}
          </p>

          <Row label={t("detail.mapillaryLabel")}>
            {name ? <span className="capitalize">{name}</span> : "—"}
          </Row>
          <Row label={t("detail.mapillaryCategory")}>
            {category
              ? t.has(`mapillaryCategory.${category}`)
                ? t(`mapillaryCategory.${category}`)
                : category
              : "—"}
          </Row>
          <Row label={t("detail.model")}>
            <code className="text-[11px] text-[var(--fg-muted)]">
              {sign.model_version || "—"}
            </code>
          </Row>
          <Row label={t("detail.status")}>
            {sign.reason
              ? t.has(`signReason.${sign.reason}`)
                ? t(`signReason.${sign.reason}`)
                : sign.reason
              : "—"}
          </Row>
          <Row label={t("detail.coords")}>
            <code className="text-[11px]">
              {sign.lat.toFixed(5)}, {sign.lon.toFixed(5)}
            </code>
          </Row>
          <Row label={t("detail.sourceImage")}>
            {sign.image_id ? (
              <code className="text-[11px]">{sign.image_id}</code>
            ) : (
              "—"
            )}
          </Row>
        </section>
      </div>

      {sourceUrl && (
        <footer className="p-3 border-t border-[var(--line)]">
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center justify-center gap-2 w-full rounded-[var(--radius-sm)] border border-[var(--line-strong)] bg-[var(--panel-2)] px-3 py-2 text-xs font-medium text-[var(--fg)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors duration-150"
          >
            <IconExternal size={14} />
            {t("detail.openSource")}
          </a>
        </footer>
      )}
    </aside>
  );
}
