"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import BboxMap from "../../components/BboxMap";
import { createJob, type Bbox } from "../../lib/api";

export default function HomePage() {
  const t = useTranslations();
  const router = useRouter();
  const [bbox, setBbox] = useState<Bbox | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!bbox) return;
    setBusy(true);
    setError(null);
    try {
      const job = await createJob(bbox);
      router.push(`jobs/${job.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-bold">{t("app.name")}</h1>
      <p className="mb-4 text-sm opacity-70">{t("app.tagline")}</p>

      <BboxMap value={bbox} onChange={setBbox} />

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={submit}
          disabled={!bbox || busy}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-40"
        >
          {t("map.submit")}
        </button>
        <button onClick={() => setBbox(null)} className="rounded border px-4 py-2">
          {t("map.clear")}
        </button>
        {!bbox && <span className="text-sm opacity-60">{t("map.drawBox")}</span>}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </main>
  );
}
