# bina · بینا

Draw a box on a map of Mashhad, get a counted and classified inventory of the road
signs inside it, and export it as CSV or GeoJSON.

Street-level imagery and sign detections come from Mapillary. Classification into the
Persian sign taxonomy is ours, cold-started on CLIP zero-shot and improved through an
in-app labeling queue.

| Class | Persian |
|---|---|
| `direction_guide` | تابلو مسیرنما |
| `street_name` | تابلو نام معبر |
| `city_entry` | تابلو ورودی شهر |
| `informational` | تابلو اطلاعاتی |
| `unknown` | نامشخص |

## Before anything else: verify coverage

The whole ingestion design assumes Mapillary has sign coverage in Mashhad. **This has
not been verified yet** — it needs a token.

```bash
export MAPILLARY_TOKEN='MLY|...'      # mapillary.com/dashboard/developers
make coverage-probe
```

The probe prints how many images and sign features exist in one central Mashhad tile and
ends with a VERDICT line. If it reports no coverage, the imagery source has to be
reconsidered before this app is useful — the classifier and labeling loop survive such a
change, the ingestion path does not.

Mapillary is Meta-owned and may be unreachable from Iran. The worker honours `HTTPS_PROXY`;
the API and web tiers never call Mapillary.

## Running it

```bash
make up          # Postgres + PostGIS, Redis
make migrate     # apply schema
make test        # backend suite
make web-test    # frontend suite
make e2e         # browser suite (seeds its own data, no token needed)
```

Dev servers:

```bash
# API
PYTHONPATH=services/api:services/worker:packages/ml \
  MAPILLARY_TOKEN='MLY|...' \
  DATABASE_URL='postgresql+psycopg://bina:bina@localhost:5432/bina' \
  .venv/bin/uvicorn bina_api.main:app --port 8010

# worker (needed for jobs to actually run)
PYTHONPATH=services/api:services/worker:packages/ml \
  MAPILLARY_TOKEN='MLY|...' \
  DATABASE_URL='postgresql+psycopg://bina:bina@localhost:5432/bina' \
  .venv/bin/rq worker

# web
cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8010 npm run dev
```

Then open `http://localhost:3000/fa`. Hold **Shift** and drag on the map to draw a box.

> **The test suites drop and recreate every table in `DATABASE_URL`.** Running `make test`
> against a database holding real jobs destroys them. Point `DATABASE_URL` at a throwaway
> database before running tests, or give tests their own.

## Layout

```
apps/web         Next.js 16 · next-intl (fa default, RTL) · MapLibre GL
services/api     FastAPI · Postgres/PostGIS · jobs, signs, export, labels
services/worker  tiler · Mapillary client · geometry decode · cropper · pipeline
packages/ml      classifier protocol · model registry · CLIP zero-shot
```

`tiler.py` and `geometry.py` are pure functions and carry the heaviest tests — they are
where being silently wrong is easiest and least visible.

## How counting works

Mapillary's `/map_features` returns **one record per physical sign**, already deduplicated
across every image that observed it. That record is the counting primitive, and a unique
constraint on `(job_id, mapillary_feature_id)` enforces it in the database rather than in
application logic.

Failures never silently shrink a count. A sign that cannot be cropped or classified is
still counted, as `unknown`, flagged for review. Every count response carries
`failed_count` beside it. An empty area returns success with reason `no_imagery` — absence
of coverage is an answer, not an error.

## Docs

- Design: `docs/superpowers/specs/2026-07-28-bina-sign-detection-design.md`
- Plan: `docs/superpowers/plans/2026-07-28-bina-v1-sign-detection.md`

## Not in v1

Tree detection, satellite imagery of any kind, own capture, auth, change detection over
time. Sentinel-2 is 10 m/pixel and cannot resolve road signs at all — satellite imagery
was ruled out for signs during design, not deferred.
