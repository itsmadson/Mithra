"use client";

import { useEffect, useRef } from "react";

/**
 * Keep a long-open tab working across a deployment.
 *
 * Two different failures follow from a rebuild landing under an open tab, and
 * they need different answers:
 *
 * 1. A chunk the router asks for no longer exists. That throws, so it can be
 *    caught, and the page reloads itself.
 *
 * 2. The server answers with a payload built by a *different* build. Nothing
 *    throws — the router simply never commits the navigation, and the tab sits
 *    on the old page looking like it is still loading. This is the one that
 *    cannot be caught, so it has to be predicted: the tab knows which build it
 *    was served, asks the server what is running now, and when they disagree
 *    stops using client-side navigation.
 *
 * Discovering the mismatch does not reload immediately. An operator may be
 * mid-review with an unsaved judgement on screen, and yanking the page out
 * from under them to fix a problem they have not hit yet is its own bug. The
 * next link they click becomes a full page load instead, which lands them
 * where they wanted to go, on the current build.
 */
const RELOADED = "bina-reloaded-for-stale-build";
const CHECK_INTERVAL = 60_000;

function isStaleChunk(reason: unknown): boolean {
  const message =
    reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason ?? "");
  return (
    message.includes("ChunkLoadError") ||
    message.includes("Loading chunk") ||
    message.includes("Loading CSS chunk") ||
    (message.includes("Failed to fetch dynamically imported module") &&
      message.includes("/_next/"))
  );
}

export function StaleBuildRecovery({ buildId }: { buildId: string }) {
  const stale = useRef(false);

  useEffect(() => {
    if (buildId === "development") return;

    let cancelled = false;

    async function check() {
      try {
        const response = await fetch("/api/build", { cache: "no-store" });
        if (!response.ok) return;
        const { id } = (await response.json()) as { id: string };
        if (!cancelled && id && id !== buildId) stale.current = true;
      } catch {
        /* offline or restarting: not evidence of a new build */
      }
    }

    // On focus as well as on a timer: a tab left in the background all night
    // should find out when it is looked at again, not up to a minute later.
    const onVisible = () => {
      if (document.visibilityState === "visible") check();
    };

    check();
    const timer = setInterval(check, CHECK_INTERVAL);
    document.addEventListener("visibilitychange", onVisible);

    // Capture phase, so this runs before the router claims the click.
    function onClick(event: MouseEvent) {
      if (!stale.current) return;
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const anchor = (event.target as Element | null)?.closest?.("a");
      const href = anchor?.getAttribute("href");
      if (!anchor || !href || anchor.target === "_blank") return;
      if (!href.startsWith("/")) return;

      event.preventDefault();
      // A full load rather than a router navigation: the client-side route
      // table belongs to a build that is no longer being served.
      window.location.assign(href);
    }

    document.addEventListener("click", onClick, true);

    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      document.removeEventListener("click", onClick, true);
    };
  }, [buildId]);

  useEffect(() => {
    function recover(reason: unknown) {
      if (!isStaleChunk(reason)) return;
      try {
        if (sessionStorage.getItem(RELOADED)) return;
        sessionStorage.setItem(RELOADED, "1");
      } catch {
        /* private mode: reload once anyway rather than staying stuck */
      }
      window.location.reload();
    }

    const onRejection = (event: PromiseRejectionEvent) => recover(event.reason);
    const onError = (event: ErrorEvent) => recover(event.error ?? event.message);

    window.addEventListener("unhandledrejection", onRejection);
    window.addEventListener("error", onError);
    try {
      sessionStorage.removeItem(RELOADED);
    } catch {
      /* nothing to clear */
    }

    return () => {
      window.removeEventListener("unhandledrejection", onRejection);
      window.removeEventListener("error", onError);
    };
  }, []);

  return null;
}
