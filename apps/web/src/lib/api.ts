export type Bbox = [number, number, number, number];

export const SIGN_CLASSES = [
  "direction_guide",
  "street_name",
  "city_entry",
  "informational",
] as const;
export type SignClass = (typeof SIGN_CLASSES)[number] | "unknown";

export type JobState = "queued" | "running" | "succeeded" | "partial" | "failed";

export interface JobSummary {
  id: string;
  name: string;
  kind: "bbox" | "street";
  status: JobState;
  reason: string | null;
  total: number;
  failed_count: number;
  tile_count: number;
  failed_tile_count: number;
  created_at: string;
  finished_at: string | null;
}

export interface StreetHit {
  osm_id: number;
  osm_type: string;
  display_name: string;
  name: string;
  name_fa: string;
  name_en: string;
  category: string;
  type: string;
  lat: number;
  lon: number;
}

export interface JobStatus {
  id: string;
  name: string;
  kind: "bbox" | "street";
  status: JobState;
  reason: string | null;
  bbox: [number, number, number, number];
  /** Street surveys carry the centreline they followed. */
  geometry: GeoJSON.Geometry | null;
  buffer_m: number;
  osm_id: number | null;
  created_at: string;
  finished_at: string | null;
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
  /** Provenance — which Mapillary image the crop came from. */
  image_id: string | null;
  /** Which model version produced sign_class. */
  model_version: string | null;
  /** ok | crop_failed | no_detection | classify_failed */
  reason: string | null;
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

export function createBboxJob(bbox: Bbox, name?: string) {
  return request<{ id: string; status: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ bbox, name }),
  });
}

/** The primary path: survey a street, not a rectangle. */
export function createStreetJob(street: StreetHit, bufferM: number, name?: string) {
  return request<{ id: string; status: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      osm_id: street.osm_id,
      street_name: street.name || street.name_fa || street.display_name,
      lat: street.lat,
      lon: street.lon,
      buffer_m: bufferM,
      name,
    }),
  });
}

export function listJobs(limit = 50, offset = 0) {
  return request<{ items: JobSummary[]; total: number }>(
    `/api/jobs?limit=${limit}&offset=${offset}`,
  );
}

export function deleteJob(id: string) {
  return fetch(`${API_BASE}/api/jobs/${id}`, { method: "DELETE" });
}

export function searchStreets(q: string, signal?: AbortSignal) {
  return request<{ items: StreetHit[] }>(
    `/api/streets/search?q=${encodeURIComponent(q)}`,
    { signal },
  );
}

/** GeoJSON the map renders directly and any GIS client can consume. */
export function featuresUrl(id: string) {
  return `${API_BASE}/api/jobs/${id}/features`;
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
