"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { TopBar, useTheme } from "../../../components/Shell";
import { IconFlag } from "../../../components/icons";
import {
  API_BASE,
  SIGN_CLASSES,
  getLabelQueue,
  postLabel,
  type Sign,
} from "../../../lib/api";
import { CLASS_COLOR, mapillaryImageUrl, mapillaryName } from "../../../lib/signClass";
import { advance, needsRefill } from "../../../lib/labelQueue";

export default function LabelPage() {
  const t = useTranslations();
  const [theme, setTheme] = useTheme();
  const [items, setItems] = useState<Sign[]>([]);
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);

  const refill = useCallback(async () => {
    const { items: next } = await getLabelQueue(50);
    setItems(next);
    setIndex(0);
  }, []);

  useEffect(() => {
    refill();
  }, [refill]);

  useEffect(() => {
    if (items.length > 0 && needsRefill(items, index)) refill();
  }, [items, index, refill]);

  const current = items[index];

  const choose = useCallback(
    async (signClass: string) => {
      if (!current || busy) return;
      setBusy(true);
      try {
        await postLabel(current.id, signClass);
        setIndex((i) => advance(items, i));
      } finally {
        setBusy(false);
      }
    },
    [current, busy, items],
  );

  // Number keys pick a class. Labeling hundreds of crops with a mouse is the
  // difference between an afternoon and a week.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const n = Number(event.key);
      if (n >= 1 && n <= SIGN_CLASSES.length) choose(SIGN_CLASSES[n - 1]);
      if (event.key === "0") choose("unknown");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choose]);

  const source = current ? mapillaryImageUrl(current.image_id) : null;

  return (
    <div className="flex h-dvh flex-col">
      <TopBar
        theme={theme}
        setTheme={setTheme}
        title={t("label.title")}
        subtitle={items.length > 0 ? t("label.hint") : undefined}
      />

      <main className="grid min-h-0 flex-1 place-items-center p-4">
        {!current ? (
          <div className="text-center">
            <IconFlag size={24} className="mx-auto mb-3 text-[var(--fg-faint)]" />
            <p className="text-sm text-[var(--fg)]">{t("label.empty")}</p>
            <p className="mt-1 text-xs text-[var(--fg-muted)]">{t("label.emptyHint")}</p>
          </div>
        ) : (
          <div className="w-full max-w-md">
            <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-4 shadow-[var(--shadow-lg)]">
              <div className="grid min-h-56 place-items-center rounded-[var(--radius-sm)] bg-[var(--panel-2)] p-3">
                {current.crop_url ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    src={`${API_BASE}${current.crop_url}`}
                    alt={t("detail.cropAlt")}
                    className="max-h-64 rounded-[var(--radius-sm)] object-contain"
                  />
                ) : (
                  <p className="text-xs text-[var(--fg-faint)]">{t("detail.noCrop")}</p>
                )}
              </div>

              <div className="mt-3 flex items-center justify-between text-[11px] text-[var(--fg-faint)]">
                <span className="capitalize">
                  {mapillaryName(current.mapillary_value) ?? t("list.unlabelled")}
                </span>
                <span className="tabular-nums">
                  {Math.round(current.confidence * 100)}%
                </span>
              </div>

              <p className="mt-4 text-center text-[13px] text-[var(--fg)]">
                {t("label.question")}
              </p>

              <div className="mt-3 grid grid-cols-2 gap-2">
                {SIGN_CLASSES.map((cls, i) => (
                  <button
                    key={cls}
                    onClick={() => choose(cls)}
                    disabled={busy}
                    className="group flex items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--line)] px-3 py-2.5 text-start text-[13px] text-[var(--fg)] transition-colors duration-150 hover:border-[var(--line-strong)] hover:bg-[var(--panel-2)] disabled:opacity-40"
                  >
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ background: CLASS_COLOR[cls] }}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1 truncate">{t(`classes.${cls}`)}</span>
                    <kbd className="shrink-0 rounded border border-[var(--line)] px-1 text-[10px] text-[var(--fg-faint)]">
                      {i + 1}
                    </kbd>
                  </button>
                ))}
                <button
                  onClick={() => choose("unknown")}
                  disabled={busy}
                  className="col-span-2 flex items-center gap-2 rounded-[var(--radius-sm)] border border-dashed border-[var(--line)] px-3 py-2 text-start text-[13px] text-[var(--fg-muted)] transition-colors duration-150 hover:border-[var(--line-strong)] disabled:opacity-40"
                >
                  <span className="min-w-0 flex-1">{t("classes.unknown")}</span>
                  <kbd className="shrink-0 rounded border border-[var(--line)] px-1 text-[10px] text-[var(--fg-faint)]">
                    0
                  </kbd>
                </button>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between px-1 text-[11px] text-[var(--fg-faint)]">
              <span>{t("label.progress", { current: index + 1, total: items.length })}</span>
              {source && (
                <a
                  href={source}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-[var(--accent)] transition-colors duration-150"
                >
                  {t("detail.openSource")}
                </a>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
