"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import NewSurvey from "../../../components/NewSurvey";
import SurveyList, { ClassKey } from "../../../components/SurveyList";
import { AppShell } from "../../../components/AppShell";
import { IconAlert } from "../../../components/icons";
import { listJobs, type JobSummary } from "../../../lib/api";

/**
 * The survey console: what has been surveyed, and a panel to survey something
 * new. This used to be the landing page; the dashboard took that place, because
 * "what do we have" is a different question from "run another survey", and only
 * the first is worth answering before anyone asks.
 */
export default function SurveysPage() {
  const t = useTranslations();

  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { items, total: count } = await listJobs();
      setJobs(items);
      setTotal(count);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Running surveys advance on the worker, so the list refreshes while any of
  // them is unfinished and stops once everything has settled.
  useEffect(() => {
    const pending = jobs.some((j) => j.status === "queued" || j.status === "running");
    if (!pending) return;
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [jobs, refresh]);

  return (
    <AppShell
      title={t("surveys.title")}
      subtitle={loaded ? t("surveys.count", { count: total }) : t("job.loading")}
    >
      <div className="flex min-h-0 flex-1 flex-col-reverse lg:flex-row">
        <main className="flex min-h-0 flex-1 flex-col rtl:lg:order-2">
          {error ? (
            <div className="grid flex-1 place-items-center p-8 text-center">
              <div>
                <IconAlert size={24} className="mx-auto mb-2.5 text-[var(--danger)]" />
                <p className="text-sm">{t("error.title")}</p>
                <p className="mt-1 text-xs text-[var(--fg-muted)]">{error}</p>
              </div>
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <SurveyList jobs={jobs} />
            </div>
          )}

          <footer className="border-t border-[var(--line)] px-4 py-2.5">
            <ClassKey />
          </footer>
        </main>

        <aside className="w-full shrink-0 border-b border-[var(--line)] bg-[var(--panel)] lg:w-[360px] lg:border-b-0 lg:border-s rtl:lg:order-1 rtl:lg:border-e rtl:lg:border-s-0">
          <NewSurvey onCreated={refresh} />
        </aside>
      </div>
    </AppShell>
  );
}
