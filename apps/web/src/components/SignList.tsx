"use client";

import { useTranslations } from "next-intl";
import { API_BASE, type Feature } from "../lib/api";
import { colorForClass, mapillaryName } from "../lib/signClass";
import { IconFlag, IconImage } from "./icons";

export default function SignList({
  signs,
  selectedId,
  onSelect,
}: {
  signs: Feature[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations();

  if (signs.length === 0) {
    return (
      <div className="px-4 py-10 text-center">
        <IconImage size={22} className="mx-auto mb-2.5 text-[var(--fg-faint)]" />
        <p className="text-[13px] text-[var(--fg-muted)]">{t("list.empty")}</p>
        <p className="mt-1 text-xs text-[var(--fg-faint)]">{t("list.emptyHint")}</p>
      </div>
    );
  }

  return (
    <ul data-testid="sign-list">
      {signs.map((sign) => {
        const selected = sign.id === selectedId;
        const color = colorForClass(sign.class_name);
        return (
          <li key={sign.id}>
            <button
              onClick={() => onSelect(sign.id)}
              aria-current={selected}
              className="group flex w-full items-center gap-3 px-3 py-2.5 text-start transition-colors duration-150"
              style={{ background: selected ? "var(--panel-2)" : undefined }}
            >
              <span
                className="w-0.5 self-stretch rounded-full shrink-0 transition-opacity duration-150"
                style={{ background: color, opacity: selected ? 1 : 0 }}
                aria-hidden
              />
              {sign.crop_url ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={`${API_BASE}${sign.crop_url}`}
                  alt=""
                  loading="lazy"
                  className="size-10 shrink-0 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] object-cover"
                />
              ) : (
                <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius-sm)] border border-dashed border-[var(--line)] text-[var(--fg-faint)]">
                  <IconImage size={14} />
                </span>
              )}
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span
                    className="size-1.5 rounded-full shrink-0"
                    style={{ background: color }}
                    aria-hidden
                  />
                  <span className="truncate text-[13px] text-[var(--fg)]">
                    {t.has(`classes.${sign.class_name}`) ? t(`classes.${sign.class_name}`) : sign.class_name}
                  </span>
                  {sign.needs_review && (
                    <IconFlag size={12} className="shrink-0 text-[var(--warn)]" />
                  )}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--fg-faint)]">
                  <span className="tabular-nums">{Math.round(sign.confidence * 100)}%</span>
                  <span aria-hidden>·</span>
                  <span className="truncate capitalize">
                    {mapillaryName(sign.source_value) ?? t("list.unlabelled")}
                  </span>
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
