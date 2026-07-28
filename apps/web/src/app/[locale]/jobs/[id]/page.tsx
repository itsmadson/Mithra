"use client";

import { useTranslations } from "next-intl";
import { use, useEffect, useState } from "react";
import CountsPanel from "../../../../components/CountsPanel";
import SignTable from "../../../../components/SignTable";
import { exportUrl, getJob, listSigns, type JobStatus, type Sign } from "../../../../lib/api";
import { isTerminal } from "../../../../lib/counts";

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations();
  const [job, setJob] = useState<JobStatus | null>(null);
  const [signs, setSigns] = useState<Sign[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const next = await getJob(id);
        if (cancelled) return;
        setJob(next);
        if (isTerminal(next.status)) {
          setSigns((await listSigns(id)).items);
          return;
        }
        setTimeout(poll, 2000);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <main className="p-6 text-red-600">{error}</main>;
  if (!job) return <main className="p-6">{t("job.queued")}</main>;

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-bold">{t("app.name")}</h1>
        <p className="text-sm opacity-70">
          {t("job.status")}: {t(`job.${job.status}`)}
        </p>
      </header>

      <CountsPanel job={job} />

      {isTerminal(job.status) && (
        <div className="flex gap-3">
          <a className="rounded border px-3 py-2 text-sm" href={exportUrl(id, "csv")}>
            {t("export.csv")}
          </a>
          <a className="rounded border px-3 py-2 text-sm" href={exportUrl(id, "geojson")}>
            {t("export.geojson")}
          </a>
        </div>
      )}

      <SignTable signs={signs} />
    </main>
  );
}
