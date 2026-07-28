import { SIGN_CLASSES, type JobStatus, type SignClass } from "./api";

const DISPLAY_ORDER: SignClass[] = [...SIGN_CLASSES, "unknown"];

export function orderedCounts(counts: Partial<Record<SignClass, number>>) {
  return DISPLAY_ORDER.map((signClass) => ({ signClass, count: counts[signClass] ?? 0 }));
}

export function isTerminal(status: JobStatus["status"]) {
  return status === "succeeded" || status === "partial" || status === "failed";
}
