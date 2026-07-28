"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { API_BASE, SIGN_CLASSES, getLabelQueue, postLabel, type Sign } from "../../../lib/api";
import { advance, needsRefill } from "../../../lib/labelQueue";

export default function LabelPage() {
  const t = useTranslations();
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

  async function choose(signClass: string) {
    if (!current || busy) return;
    setBusy(true);
    try {
      await postLabel(current.id, signClass);
      setIndex((i) => advance(items, i));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold">{t("label.title")}</h1>

      {!current ? (
        <p className="mt-6 opacity-70">{t("label.empty")}</p>
      ) : (
        <>
          <div className="mt-6 flex justify-center">
            {current.crop_url && (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={`${API_BASE}${current.crop_url}`}
                alt=""
                className="max-h-80 rounded-lg border object-contain"
              />
            )}
          </div>
          <p className="mt-4 text-center">{t("label.question")}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {SIGN_CLASSES.map((signClass) => (
              <button
                key={signClass}
                onClick={() => choose(signClass)}
                disabled={busy}
                className="rounded border p-3 disabled:opacity-40"
              >
                {t(`classes.${signClass}`)}
              </button>
            ))}
            <button
              onClick={() => choose("unknown")}
              disabled={busy}
              className="col-span-2 rounded border p-3 opacity-70 disabled:opacity-40"
            >
              {t("classes.unknown")}
            </button>
          </div>
          <p className="mt-4 text-center text-xs opacity-50">
            {index + 1} / {items.length}
          </p>
        </>
      )}
    </main>
  );
}
