"use client";

import { useEffect } from "react";

/**
 * Recover a tab left open across a deployment.
 *
 * The client bundle is split into hashed chunks, and a navigation fetches the
 * ones the next route needs. After a deploy those files are gone: the router
 * asks for a chunk that no longer exists, the request fails, and the
 * navigation stops with the old page still on screen — indistinguishable from
 * loading forever. A reload fixes it, which is why it looks like the app is
 * "stuck until you refresh".
 *
 * An operator running a survey has the tab open for hours, so this is the
 * normal case rather than the edge one. Rather than asking them to know that,
 * a failed chunk load reloads the page once at the URL they were heading to.
 *
 * Once per session: if the reload itself fails to fix it, looping would spin
 * forever instead of showing the real error.
 */
const FLAG = "bina-reloaded-for-stale-build";

function isStaleChunk(reason: unknown): boolean {
  const message =
    reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason ?? "");
  return (
    message.includes("ChunkLoadError") ||
    message.includes("Loading chunk") ||
    message.includes("Loading CSS chunk") ||
    // Next's router surfaces a stale RSC payload as a failed dynamic import.
    (message.includes("Failed to fetch dynamically imported module") &&
      message.includes("/_next/"))
  );
}

export function StaleBuildRecovery() {
  useEffect(() => {
    function recover(reason: unknown) {
      if (!isStaleChunk(reason)) return;
      try {
        if (sessionStorage.getItem(FLAG)) return;
        sessionStorage.setItem(FLAG, "1");
      } catch {
        /* private mode: reload once anyway rather than staying stuck */
      }
      window.location.reload();
    }

    const onRejection = (event: PromiseRejectionEvent) => recover(event.reason);
    const onError = (event: ErrorEvent) => recover(event.error ?? event.message);

    window.addEventListener("unhandledrejection", onRejection);
    window.addEventListener("error", onError);

    // A successful load means this build is current; clear the guard so a
    // later deploy can recover too.
    try {
      sessionStorage.removeItem(FLAG);
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
