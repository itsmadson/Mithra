export type Bbox = [number, number, number, number];

export const SIGN_CLASSES = [
  "direction_guide",
  "street_name",
  "city_entry",
  "informational",
] as const;
export type FeatureClass = (typeof SIGN_CLASSES)[number] | "unknown";

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
  counts: Record<string, number>;
  total: number;
  failed_count: number;
}

export interface Feature {
  id: string;
  class_name: FeatureClass;
  confidence: number;
  lon: number;
  lat: number;
  crop_url: string | null;
  needs_review: boolean;
  source_value: string | null;
  /** Provenance — which Mapillary image the crop came from. */
  image_id: string | null;
  /** Which model version produced class_name. */
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
  return request<{ id: string; status: string }>("/api/runs", {
    method: "POST",
    body: JSON.stringify({ bbox, name }),
  });
}

/** The primary path: survey a street, not a rectangle. */
export function createStreetJob(street: StreetHit, bufferM: number, name?: string) {
  return request<{ id: string; status: string }>("/api/runs", {
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
    `/api/runs?limit=${limit}&offset=${offset}`,
  );
}

export function deleteJob(id: string) {
  return request<void>(`/api/runs/${id}`, { method: "DELETE" });
}

export function searchStreets(q: string, signal?: AbortSignal) {
  return request<{ items: StreetHit[] }>(
    `/api/streets/search?q=${encodeURIComponent(q)}`,
    { signal },
  );
}

export interface Stats {
  surveys: { total: number; by_status: Record<string, number>; running: number };
  features: {
    total: number;
    by_class: Partial<Record<FeatureClass, number>>;
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
  if (filters.signClass) params.set("class_name", filters.signClass);
  if (filters.needsReview !== undefined)
    params.set("needs_review", String(filters.needsReview));
  params.set("limit", String(filters.limit ?? 1000));
  return request<{ items: Feature[] }>(`/api/features?${params}`);
}

/** GeoJSON the map renders directly and any GIS client can consume. */
export function featuresUrl(id: string) {
  return `${API_BASE}/api/runs/${id}/features.geojson`;
}

export function getJob(id: string) {
  return request<JobStatus>(`/api/runs/${id}`);
}

export function listSigns(
  id: string,
  filters: { signClass?: string; needsReview?: boolean } = {},
) {
  const params = new URLSearchParams();
  if (filters.signClass) params.set("class_name", filters.signClass);
  if (filters.needsReview !== undefined)
    params.set("needs_review", String(filters.needsReview));
  const query = params.toString();
  return request<{ items: Feature[] }>(`/api/runs/${id}/features${query ? `?${query}` : ""}`);
}

export function getLabelQueue(limit = 50) {
  return request<{ items: Feature[] }>(`/api/labels/queue?limit=${limit}`);
}

export function postLabel(signId: string, signClass: string) {
  return request<{ status: string }>("/api/labels", {
    method: "POST",
    body: JSON.stringify({ sign_id: signId, class_name: signClass }),
  });
}

export function exportUrl(id: string, format: "csv" | "geojson") {
  return `${API_BASE}/api/runs/${id}/export.${format}`;
}

export interface Overview {
  org: { id: string | null };
  features: {
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
  coverage: { area_km2: number; mapped_km2: number; per_km2: number };
  sources: Record<string, number>;
  detectors: Record<string, number>;
  activity: { features_per_day: { date: string; count: number }[]; days: number };
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

export interface CatalogSource {
  key: string;
  label_en: string;
  label_fa: string;
  kind: string;
  gsd_m: number | null;
  viewpoint: string;
  imagery_kind: string;
  licence: string;
  bulk_use: string;
  needs_credentials: boolean;
  notes_en: string;
}

export interface CatalogTarget {
  key: string;
  label_en: string;
  label_fa: string;
  geometry: string;
  min_gsd_m: number;
  viewpoints: string[];
  coarser_alternative: string | null;
  notes_en: string;
}

export interface TargetAvailability {
  key: string;
  label_en: string;
  label_fa: string;
  available: boolean;
  reason: string;
  alternative: string | null;
  detectors: string[];
}

export function getCatalog() {
  return request<{
    sources: CatalogSource[];
    targets: CatalogTarget[];
    detectors: { key: string; label: string; targets: string[]; open_vocabulary: boolean; needs_gpu: boolean; notes: string }[];
  }>("/api/catalog");
}

export function getAvailability(source: string, gsdM?: number) {
  const query = gsdM ? `&gsd_m=${gsdM}` : "";
  return request<{
    source: string;
    gsd_m: number | null;
    viewpoint: string;
    bulk_use: string;
    targets: TargetAvailability[];
  }>(`/api/catalog/availability?source=${encodeURIComponent(source)}${query}`);
}

/** Start a detection run over an area with a chosen imagery source. */
export function createDetectionRun(body: {
  name?: string;
  bbox: Bbox;
  source_kind: string;
  source_config?: Record<string, unknown>;
  targets: string[];
  detector: string;
}) {
  return request<{ id: string; status: string }>("/api/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface DetectorFitness {
  key: string;
  label: string;
  targets: string[];
  implemented: boolean;
  runtime: string;
  vram_gb: number;
  open_vocabulary: boolean;
  benchmark: { metric: string; value: number; dataset: string; source: string } | null;
  runnable: boolean;
  reason: string;
  speed: string;
  notes: string;
}

export interface SystemCapability {
  machine: {
    tier: "gpu" | "small_gpu" | "strong_cpu" | "modest";
    cpu_count: number;
    ram_gb: number;
    has_gpu: boolean;
    gpu_name: string;
    vram_gb: number;
    disk_free_gb: number;
  };
  detectors: DetectorFitness[];
  recommended: Record<string, { detector: string | null; evidence: string; available: boolean }>;
}

export function getCapability() {
  return request<SystemCapability>("/api/system/capability");
}

export interface UploadedRaster {
  path: string;
  filename: string;
  bytes: number;
  bounds: [number, number, number, number];
  gsd_m: number | null;
}

/** Upload a raster; the response reports what its pixels can support. */
export async function uploadRaster(file: File): Promise<UploadedRaster> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE}/api/uploads`, {
    method: "POST",
    credentials: "include",
    body,
  });
  if (response.status === 401) throw new Unauthorized();
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `upload failed: ${response.status}`);
  }
  return response.json();
}

export interface DetectionPlan {
  target: string;
  known: boolean;
  label_en: string;
  label_fa: string;
  domain: string;
  geometry: string;
  min_gsd_m: number;
  viewpoints: string[];
  coarser_alternative: string | null;
  notes_en: string;
  sources: {
    key: string;
    label_en: string;
    label_fa: string;
    gsd_m: number | null;
    viewpoint: string;
    imagery_kind: string;
    licence: string;
    bulk_use: string;
    usable: boolean;
    reason: string;
  }[];
  models: {
    key: string;
    label: string;
    runtime: string;
    vram_gb: number;
    implemented: boolean;
    runnable_here: boolean;
    reason: string;
    speed: string;
    open_vocabulary: boolean;
    benchmark: {
      metric: string;
      value: number;
      dataset: string;
      source: string;
      measures_this_target: boolean;
    } | null;
    notes: string;
  }[];
  recommended: { detector: string | null; evidence: string };
}

export function getPlan(target: string) {
  return request<DetectionPlan>(`/api/catalog/plan/${encodeURIComponent(target)}`);
}

export interface CatalogDomain {
  key: string;
  targets: {
    key: string;
    label_en: string;
    label_fa: string;
    geometry: string;
    min_gsd_m: number;
    viewpoints: string[];
  }[];
}

export function getDomains() {
  return request<{ domains: CatalogDomain[] }>("/api/catalog/domains");
}
