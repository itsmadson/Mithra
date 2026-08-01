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

/** Thrown when the session is missing or expired, so callers can redirect. */
export class Unauthorized extends Error {
  constructor() {
    super("authentication required");
    this.name = "Unauthorized";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    // The session lives in an httpOnly cookie, which is only sent on
    // cross-origin requests when credentials are included explicitly.
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (response.status === 401) throw new Unauthorized();
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export interface Account {
  id: string;
  email: string;
  name: string;
  role: "admin" | "operator";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export function setupState() {
  return request<{ needs_setup: boolean }>("/api/auth/setup");
}

export function login(email: string, password: string) {
  return request<Account>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function registerAccount(email: string, password: string, name = "") {
  return request<Account>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
}

export function logout() {
  return request<void>("/api/auth/logout", { method: "POST" });
}

export function me() {
  return request<Account>("/api/auth/me");
}

export function listAccounts() {
  return request<{ items: Account[] }>("/api/auth/users");
}

export function updateAccount(
  id: string,
  patch: { role?: string; is_active?: boolean },
) {
  return request<Account>(`/api/auth/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
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
  return request<void>(`/api/jobs/${id}`, { method: "DELETE" });
}

export function searchStreets(q: string, signal?: AbortSignal) {
  return request<{ items: StreetHit[] }>(
    `/api/streets/search?q=${encodeURIComponent(q)}`,
    { signal },
  );
}

export interface Stats {
  surveys: { total: number; by_status: Record<string, number>; running: number };
  signs: {
    total: number;
    by_class: Partial<Record<SignClass, number>>;
    needs_review: number;
    unclassified: number;
  };
  labels: { total: number };
  models: string[];
}

export function getStats() {
  return request<Stats>("/api/stats");
}

export function listAllSigns(
  filters: { signClass?: string; needsReview?: boolean; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (filters.signClass) params.set("sign_class", filters.signClass);
  if (filters.needsReview !== undefined)
    params.set("needs_review", String(filters.needsReview));
  params.set("limit", String(filters.limit ?? 1000));
  return request<{ items: Sign[] }>(`/api/signs?${params}`);
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

export interface Overview {
  org: { id: string | null };
  signs: {
    total: number;
    by_class: Record<string, number>;
    needs_review: number;
    failed: number;
    confident_share: number;
  };
  surveys: {
    total: number;
    by_status: Record<string, number>;
    running: number;
    failed: number;
  };
  labels: {
    total: number;
    per_day: { date: string; count: number }[];
    by_class: Record<string, number>;
    needed_per_class: number;
    short_by: Record<string, number>;
  };
  activity: { signs_per_day: { date: string; count: number }[]; days: number };
  confidence: {
    buckets: { from: number; to: number; count: number }[];
    threshold: number;
  };
  top_surveys: {
    id: string;
    name: string;
    total: number;
    needs_review: number;
    status: string;
  }[];
  recent: {
    id: string;
    name: string;
    status: string;
    reason: string | null;
    kind: string;
    created_at: string | null;
    total: number;
  }[];
}

/** Everything the dashboard shows, in one request, scoped to the caller's organisation. */
export function getOverview(days = 30) {
  return request<Overview>(`/api/overview?days=${days}`);
}

export interface Basemap {
  id: string;
  name: string;
  url_template: string;
  attribution: string;
  tint: boolean;
  is_default: boolean;
}

export function listBasemaps() {
  return request<{ items: Basemap[] }>("/api/basemaps");
}

export function createBasemap(body: {
  name: string;
  url_template: string;
  attribution?: string;
  tint?: boolean;
  is_default?: boolean;
}) {
  return request<Basemap>("/api/basemaps", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateBasemap(id: string, patch: { is_default?: boolean; tint?: boolean }) {
  return request<Basemap>(`/api/basemaps/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteBasemap(id: string) {
  return request<void>(`/api/basemaps/${id}`, { method: "DELETE" });
}
