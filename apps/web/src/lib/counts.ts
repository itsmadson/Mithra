import type { JobStatus } from "./api";

/** A survey that will not change again without a new run. */
export function isTerminal(status: JobStatus["status"]) {
  return status === "succeeded" || status === "partial" || status === "failed";
}
