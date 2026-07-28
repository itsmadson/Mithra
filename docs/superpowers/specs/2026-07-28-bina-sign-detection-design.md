# Bina — Street Sign Detection & Counting (v1 Design)

Date: 2026-07-28
Status: Approved
Scope: v1 MVP — traffic/informational sign counting and classification in Mashhad

## Problem

Given a bounding box drawn on a map of Mashhad, count the physical road signs inside it
and classify each one into a Persian-relevant sign taxonomy. Results must be exportable
for downstream survey/GIS use.

The application is named **bina** (Persian: بینا) and ships bilingual: Persian (RTL) and English.

## Key constraints discovered during research

1. **Sentinel-2 imagery is 10 m/pixel.** Road signs are physically invisible at that
   resolution. Satellite imagery cannot contribute to sign detection at all. It is
   excluded from v1 entirely. (It remains viable for tree counting in a later version,
   but only with sub-metre imagery — Maxar/Bing/Google tiles, not Sentinel.)
2. **Google Street View does not cover Iran.** Street-level imagery must come from
   Mapillary (crowdsourced), an Iranian panorama provider, or own capture.
3. **Mapillary is Meta-owned** and may be IP-blocked from Iran. The worker must support
   an outbound HTTP proxy.
4. **Mapillary bbox queries must be smaller than 0.01 degrees square** (constraint
   formalized 2026-01-16). Any user-drawn bbox must be tiled before querying.
5. **Mapillary's own sign taxonomy is weak on Persian guide signs.** Its 1500 classes are
   dominated by regulatory and warning signs; `information--*` classes are generic and do
   not distinguish the Iranian direction/street-name/city-entry/service categories we need.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Imagery source | Mapillary API | Free, global, already geo-referenced, no field work. Coverage in Mashhad must be verified before build starts. |
| Detection | Mapillary's precomputed detections | Removes the need to train a detector. Detection is the solved half of the problem. |
| Classification | Own classifier over cropped detections | The Iranian sign taxonomy is the part Mapillary gets wrong. This is where our modelling effort goes. |
| Backend | Python FastAPI + Postgres/PostGIS | ML is native in Python; PostGIS handles bbox and spatial queries directly. |
| Frontend | Next.js | Fixed requirement. |
| Labeling | In-app labeling UI | Keeps the improvement loop inside the product; no external tooling round-trips. |
| v1 scope | Signs only | Trees require a different imagery pipeline, different model, and different licensing. Separate project. |

## Sign taxonomy (v1 classes)

| Class key | Persian | English |
|---|---|---|
| `direction_guide` | تابلو مسیرنما | Direction / guide sign |
| `street_name` | تابلو نام معبر | Street name sign |
| `city_entry` | تابلو ورودی شهر | City / place entry sign |
| `informational` | تابلو اطلاعاتی | Informational / service sign |

Anything the classifier cannot place in these four is stored as `unknown` and surfaced in
the labeling queue. `unknown` is counted separately and never silently dropped.

## Architecture

```
apps/web         Next.js 15 App Router · next-intl (fa/en, RTL) · MapLibre GL
services/api     FastAPI · Postgres+PostGIS · job/sign/label/export routes
services/worker  RQ worker · mapillary client · tiler · cropper · inference
packages/ml      classifier train + predict · model registry
```

Postgres is the only shared state between web, API, and worker. The worker never
communicates with the web tier directly; job status is read from the database.

### Module responsibilities

- **`tiler`** — splits a user bbox into Mapillary-legal tiles (< 0.01° per side).
  Pure function, no I/O. Independently testable.
- **`mapillary client`** — HTTP access to Mapillary graph API. Handles auth, proxy,
  retry, and rate-limit backoff. Knows nothing about signs or jobs.
- **`cropper`** — decodes a Mapillary detection geometry into a pixel polygon, fetches
  the source image, returns a cropped sign image. No model dependency.
- **`packages/ml`** — `predict(crop) -> (class, confidence, model_version)` and a
  training entry point. No knowledge of HTTP, jobs, or the database.
- **`services/api`** — request validation, job lifecycle, querying results, export.
  No inference, no external image fetching.

## Data flow — one detection job

1. User draws a bbox on the map. `POST /jobs {bbox, classes}` creates a job row with
   status `queued`.
2. Worker picks up the job and splits the bbox into tiles smaller than 0.01° square.
3. For each tile, query `GET graph.mapillary.com/map_features` filtered to the traffic
   sign layer. **Each returned map feature represents one physical real-world sign**,
   already deduplicated across all the images that observed it and already geolocated.
   This is the counting primitive — no custom clustering is required.
4. For each map feature, select the best source image and fetch that image's detection
   record to obtain the pixel geometry. Crop the sign.
5. Run the crop through the classifier to obtain a class and confidence.
6. Insert a `signs` row: PostGIS point geometry, class, confidence,
   `mapillary_feature_id`, source `image_id`, crop path, and the model version used.
7. The web app polls job status and renders per-class counts, map pins, a result table,
   and CSV/GeoJSON export.

`mapillary_feature_id` is unique per job, which makes double-counting structurally
impossible rather than a matter of tuning.

## Classifier and labeling loop

**Cold start.** Before any labels exist, classification is CLIP zero-shot using bilingual
prompts (for example "a Persian street name plate" and "تابلو نام معبر"). This produces
usable-but-imperfect output on day one and, more importantly, an ordering over crops.

**Labeling.** Every classified crop enters the labeling queue, sorted lowest-confidence
first. The operator confirms or corrects the class in the app. Corrections are stored as
ground-truth labels against the crop, not against the sign row.

**Retraining.** Once roughly 200 labels per class exist, a small ViT classification head
is fine-tuned on the labeled crops and registered as a new model version.

**Versioning.** Model versions are database rows. Every sign records the version that
classified it. Reclassifying a job under a new model creates new sign classifications
rather than overwriting the old ones, so accuracy changes between versions are auditable.

## Error handling

| Case | Behavior |
|---|---|
| Mapillary 429 or 5xx | Tile-level retry with exponential backoff. If a tile still fails, the job completes with status `partial` and the failed tiles are listed on the job. |
| Mapillary auth failure (401/403) | Job fails fast with an explicit credential error. No retry. |
| Outbound network blocked from Iran | Worker honours an `HTTPS_PROXY` environment variable. Proxy config is worker-only; the API and web tiers never call Mapillary. |
| No imagery coverage in bbox | Job **succeeds** with zero results and reason `no_imagery`. Absence of coverage is a valid answer, not an error. |
| Image fetch fails for one feature | That feature is stored with class `unknown` and reason `crop_failed`. The job continues. |
| Classifier confidence below threshold | Sign is still counted, flagged `needs_review`, and placed at the top of the labeling queue. |

Counts are never silently reduced by failures. Every count returned to the user is
accompanied by the number of features that failed to classify.

## Testing

- **Unit** — tiler bbox splitting (including boxes exactly on the 0.01° boundary and
  boxes crossing it), detection geometry decoding, the dedup invariant (one sign row per
  `mapillary_feature_id`).
- **Integration** — API job lifecycle against a real Postgres/PostGIS instance.
- **External API** — recorded Mapillary responses via VCR fixtures. CI makes no live
  network calls.
- **Model** — smoke test that the registered model loads and returns a valid class and
  confidence for a fixture crop. No accuracy assertions in CI.
- **End-to-end** — Playwright: draw a bbox, submit a job, see counts render.

## Internationalization

`next-intl` with `fa` as the default locale and `en` available. Full RTL layout for
Persian, including map controls and the results table. Sign class names, job statuses,
and error reasons are all translated. Numbers render with locale-appropriate digits.

## Out of scope for v1

- Tree detection and counting
- Satellite or aerial imagery of any kind
- Own dashcam or panorama capture
- Multi-user auth, roles, or tenancy
- Change detection over time

## Open blockers before implementation

1. **Mapillary developer access token** required.
2. **Mashhad coverage must be verified** with that token before any build work starts. If
   coverage is too sparse, the imagery-source decision reopens and this design changes
   substantially — the classifier and labeling design survive, the ingestion path does not.
