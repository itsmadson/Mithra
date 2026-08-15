"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import {
  createDetectionRun,
  getCapability,
  uploadRaster,
  getAvailability,
  getCatalog,
  type Bbox,
  type CatalogSource,
  type SystemCapability,
  type UploadedRaster,
  type TargetAvailability,
} from "../lib/api";
import { IconAlert, IconLayers } from "./icons";

/**
 * Compose a detection run: an area, an imagery source, and what to find.
 *
 * The order matters. The imagery is chosen first, because it decides what can
 * be detected at all — and the targets that follow are the ones that source
 * can actually deliver. Everything else is shown too, greyed, with the reason,
 * so the answer to "why can't I pick trees?" is on screen rather than absent.
 */
export function DetectionComposer({
  bbox,
  onStarted,
}: {
  bbox: Bbox | null;
  onStarted: (runId: string) => void;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const fa = locale === "fa";

  const [sources, setSources] = useState<CatalogSource[]>([]);
  const [source, setSource] = useState<string>("sentinel2");
  const [targets, setTargets] = useState<TargetAvailability[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [bulkUse, setBulkUse] = useState<string>("allowed");
  const [capability, setCapability] = useState<SystemCapability | null>(null);
  const [uploaded, setUploaded] = useState<UploadedRaster | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // What this server can run decides which detector answers, and whether it
    // can answer at all — asked once, alongside the catalogue.
    getCapability().then(setCapability).catch(() => setCapability(null));
  }, []);

  useEffect(() => {
    getCatalog()
      .then(({ sources }) => setSources(sources.filter((s) => s.viewpoint === "overhead")))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  // Every change of imagery re-asks what is possible, because the answer is
  // different for every source and guessing it in the client would drift.
  useEffect(() => {
    if (!source) return;
    getAvailability(source, source === "upload" ? uploaded?.gsd_m ?? undefined : undefined)
      .then((body) => {
        setTargets(body.targets);
        setBulkUse(body.bulk_use);
        setChosen((prev) =>
          prev.filter((k) => body.targets.some((t) => t.key === k && t.available)),
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [source, uploaded]);

  const selected = sources.find((s) => s.key === source);

  async function start() {
    // An uploaded raster carries its own extent; everything else needs one
    // chosen on the map.
    if ((!bbox && !uploaded) || chosen.length === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      // The most accurate detector this machine can actually run, chosen by
      // published benchmark rather than by order in a list.
      const recommended = capability?.recommended?.[chosen[0]]?.detector;
      const detector =
        recommended ?? targets.find((t) => t.key === chosen[0])?.detectors[0] ?? "ndwi-water";
      // One of the two is present: the button is disabled otherwise.
      const area = (uploaded?.bounds ?? bbox) as Bbox;
      const run = await createDetectionRun({
        bbox: area,
        source_kind: source,
        source_config: uploaded
          ? { path: uploaded.path, gsd_m: uploaded.gsd_m }
          : undefined,
        targets: chosen,
        detector,
      });
      onStarted(run.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4">
      <div>
        <label className="text-xs text-[var(--fg-faint)]">{t("compose.imagery")}</label>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="mt-1 w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-2 text-[13px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none"
        >
          {sources.map((s) => (
            <option key={s.key} value={s.key}>
              {fa ? s.label_fa : s.label_en}
              {s.gsd_m ? ` — ${s.gsd_m} m/px` : ""}
            </option>
          ))}
        </select>
        {selected && (
          <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--fg-muted)]">
            {selected.notes_en}
          </p>
        )}
        {bulkUse === "check_your_licence" && (
          <p className="mt-1.5 flex items-start gap-1.5 text-[11px] text-[var(--warn)]">
            <IconAlert size={12} className="mt-px shrink-0" />
            {t("compose.licenceWarning")}
          </p>
        )}
      </div>

      {selected?.kind === "upload" && (
        <div>
          <label className="text-xs text-[var(--fg-faint)]">{t("compose.file")}</label>
          <input
            type="file"
            accept=".tif,.tiff,.jp2"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              setError(null);
              try {
                const result = await uploadRaster(file);
                setUploaded(result);
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
                setUploaded(null);
              }
            }}
            className="mt-1 w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-2 text-[12px] text-[var(--fg-muted)] file:me-2 file:rounded file:border-0 file:bg-[var(--panel)] file:px-2 file:py-1 file:text-[var(--fg)]"
          />
          {uploaded && (
            <p className="mt-1.5 text-[11px] text-[var(--fg-muted)]" dir="ltr">
              {uploaded.filename} · {uploaded.gsd_m ?? "?"} m/px
            </p>
          )}
          {!uploaded && (
            <p className="mt-1.5 text-[11px] text-[var(--fg-faint)]">
              {t("compose.uploadFirst")}
            </p>
          )}
        </div>
      )}

      <div>
        <label className="text-xs text-[var(--fg-faint)]">{t("compose.targets")}</label>
        <div className="mt-1.5 grid gap-1">
          {targets.map((target) => {
            const active = chosen.includes(target.key);
            return (
              <button
                key={target.key}
                disabled={!target.available}
                onClick={() =>
                  setChosen((prev) =>
                    prev.includes(target.key)
                      ? prev.filter((k) => k !== target.key)
                      : [...prev, target.key],
                  )
                }
                className="flex items-start gap-2 rounded-[var(--radius-sm)] border px-2.5 py-2 text-start transition-colors duration-150 disabled:cursor-not-allowed"
                style={{
                  borderColor: active ? "var(--accent)" : "var(--line)",
                  background: active ? "var(--panel-2)" : undefined,
                  opacity: target.available ? 1 : 0.55,
                }}
              >
                <span className="min-w-0 flex-1">
                  <span
                    className="block text-[13px]"
                    style={{ color: active ? "var(--accent)" : "var(--fg)" }}
                  >
                    {fa ? target.label_fa : target.label_en}
                  </span>
                  {/* The reason lives next to the thing it refuses. */}
                  {!target.available && (
                    <span className="block text-[11px] leading-relaxed text-[var(--fg-faint)]">
                      {target.reason}
                      {target.alternative && ` — ${t("compose.tryInstead")} ${target.alternative}`}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <p className="flex items-start gap-1.5 text-[11px] text-[var(--danger)]">
          <IconAlert size={12} className="mt-px shrink-0" />
          {error}
        </p>
      )}

      {chosen.length > 0 && capability && (
        <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-2">
          {chosen.map((key) => {
            const plan = capability.recommended?.[key];
            return (
              <p key={key} className="text-[11px] leading-relaxed">
                <span className="text-[var(--fg-muted)]">{key}</span>{" "}
                {plan?.available ? (
                  <span className="text-[var(--fg)]">
                    → {plan.detector}{" "}
                    <span className="text-[var(--fg-faint)]">({plan.evidence})</span>
                  </span>
                ) : (
                  <span className="text-[var(--warn)]">{plan?.evidence}</span>
                )}
              </p>
            );
          })}
        </div>
      )}

      <button
        onClick={start}
        disabled={(!bbox && !uploaded) || chosen.length === 0 || busy}
        className="flex items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-[var(--accent)] px-3 py-2.5 text-[13px] font-semibold text-[var(--accent-ink)] transition-[opacity,transform] duration-150 hover:opacity-90 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
      >
        <IconLayers size={14} />
        {busy ? t("compose.starting") : t("compose.start")}
      </button>
      {!bbox && (
        <p className="text-[11px] text-[var(--fg-faint)]">{t("compose.needArea")}</p>
      )}
    </div>
  );
}
