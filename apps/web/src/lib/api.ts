export type Bbox = [number, number, number, number];

export const SIGN_CLASSES = [
  "direction_guide",
  "street_name",
  "city_entry",
  "informational",
] as const;
export type SignClass = (typeof SIGN_CLASSES)[number] | "unknown";

export interface JobStatus {
  id: string;
  status: "queued" | "running" | "succeeded" | "partial" | "failed";
  reason: string | null;
  tile_count: number;
  failed_tile_count: number;
  counts: Partial<Record<SignClass, number>>;
  total: number;
  failed_count: number;
}

export interface Sign {
  id: string;
  sign_class: SignClass;
  confidence: number;
  lon: number;
  lat: number;
  crop_url: string | null;
  needs_review: boolean;
  mapillary_value: string | null;
}

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function createJob(bbox: Bbox) {
  return request<{ id: string; status: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ bbox }),
  });
}

export function getJob(id: string) {
  return request<JobStatus>(`/api/jobs/${id}`);
}

export function listSigns(
  id: string,
  filters: { signClass?: string; needsReview?: boolean } = {},
) {
  const params = new URLSearchParams();
  if (filters.signClass) params.set("sign_class", filters.signClass);
  if (filters.needsReview !== undefined)
    params.set("needs_review", String(filters.needsReview));
  const query = params.toString();
  return request<{ items: Sign[] }>(`/api/jobs/${id}/signs${query ? `?${query}` : ""}`);
}

export function getLabelQueue(limit = 50) {
  return request<{ items: Sign[] }>(`/api/labels/queue?limit=${limit}`);
}

export function postLabel(signId: string, signClass: string) {
  return request<{ status: string }>("/api/labels", {
    method: "POST",
    body: JSON.stringify({ sign_id: signId, sign_class: signClass }),
  });
}

export function exportUrl(id: string, format: "csv" | "geojson") {
  return `${API_BASE}/api/jobs/${id}/export.${format}`;
}
