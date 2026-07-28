"use client";

import { useTranslations } from "next-intl";
import type { JobStatus } from "../lib/api";
import { orderedCounts } from "../lib/counts";

export default function CountsPanel({ job }: { job: JobStatus }) {
  const t = useTranslations();
  return (
    <section>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {orderedCounts(job.counts).map(({ signClass, count }) => (
          <div key={signClass} className="rounded-lg border p-3">
            <div className="text-2xl font-bold">{count.toLocaleString()}</div>
            <div className="text-xs opacity-70">{t(`classes.${signClass}`)}</div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-sm opacity-70">
        {t("job.total")}: {job.total.toLocaleString()} · {t("job.failedCount")}:{" "}
        {job.failed_count.toLocaleString()} · {t("job.tiles")}:{" "}
        {job.tile_count - job.failed_tile_count}/{job.tile_count}
      </p>
      {job.reason === "no_imagery" && (
        <p className="mt-2 rounded bg-amber-50 p-3 text-sm">{t("job.noImagery")}</p>
      )}
    </section>
  );
}
