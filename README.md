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

Run the whole stack (API on 8010, RQ worker, web on 3000):

```bash
make up                                   # Postgres + Redis
make migrate                              # once
MAPILLARY_TOKEN='MLY|...' make dev
```

Then open `http://localhost:3000/fa`. Hold **Shift** and drag on the map to draw a box.

Without `MAPILLARY_TOKEN` the UI is fully browsable and existing results render, but the
worker is skipped and submitted jobs stay queued. `make dev` says so on startup.

> Mapillary answers a bad or missing token with **HTTP 500, not 401**. Since 500 is a
> retryable status, an invalid token burns the full retry budget on every tile and the job
> lands in `partial` with `Mapillary returned 500` on each tile, rather than failing fast
> as an auth error. If you see that, check the token before suspecting coverage.

Tests run against a separate `bina_test` database, created automatically on first run, so
`make test` never touches your development data. Override with `BINA_TEST_DATABASE_URL`.

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
