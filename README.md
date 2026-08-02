# Mithra · میترا

**AI-powered panoramic vision platform for intelligent asset detection and street inventory.**

Mithra surveys a street from panoramic street-level imagery and returns a counted,
mapped, auditable inventory of its signs. Name a street; it resolves the centreline,
walks the imagery along it, detects and classifies every sign it finds, and puts each
one on a map beside the photograph it came from.

Built for the people who have to answer *how many, of what kind, and where* — and who
will be asked to prove it.

| Class | Persian |
|---|---|
| `direction_guide` | تابلو مسیرنما |
| `street_name` | تابلو نام معبر |
| `city_entry` | تابلو ورودی شهر |
| `informational` | تابلو اطلاعاتی |
| `unknown` | نامشخص |

---

## What it does

- **Surveys a street, not a rectangle.** You name a street; Mithra resolves its
  geometry from OpenStreetMap, buffers a corridor around the centreline, and surveys
  that. A count for "Ahmadabad Boulevard" means the boulevard, not a box that happens
  to contain it.
- **Detects and classifies.** Signs are found in panoramic imagery and sorted into the
  taxonomy above. Anything the model is unsure about becomes `unknown` and goes to a
  person rather than into the count as a guess.
- **Shows its evidence.** Every sign carries its crop, its source image, its
  coordinates, its confidence, and the model version that produced it. A number you
  cannot trace back to a photograph is not an inventory.
- **Improves from the work.** The review queue collects labels; those labels train a
  classifier that must prove it beats the model in service before it can replace it.
- **Takes your own map.** Any XYZ tile service can be added as a basemap, so the
  inventory is read against the map the organisation already trusts.

## Screens

| Section | Question it answers |
|---|---|
| Dashboard | How big is the inventory, how much is trustworthy, what is waiting |
| Surveys | What has been surveyed, and run another |
| Signs | Every sign across every survey, on one map |
| Review | Judge what the model was unsure about |
| Settings | System state, basemaps, accounts |

Persian and English, right-to-left and left-to-right, dark and light.

---

## Quick start

You need Docker and a [Mapillary access token](https://www.mapillary.com/dashboard/developers).

```bash
git clone https://github.com/itsmadson/Mithra.git
cd Mithra
echo 'MAPILLARY_TOKEN=MLY|your|token' > .env

docker compose up -d
```

Open <http://localhost:3000>. The first account you create becomes the administrator
of a new organisation; there is no default password to change.

### Images

Published to the GitHub Container Registry from CI:

```
ghcr.io/itsmadson/mithra/api:latest   # API, worker, and migrations
ghcr.io/itsmadson/mithra/web:latest   # the console
```

The API and worker share one image because they import the same code; the command
decides which one a container becomes.

---

## Running from source

```bash
docker compose up -d db redis           # just the backing services
python -m venv .venv && .venv/bin/pip install -e "services/api[dev,ml]"
(cd services/api && ../../.venv/bin/alembic upgrade head)
(cd apps/web && npm install)

cp .env.example .env                    # set MAPILLARY_TOKEN
./scripts/dev.sh                        # API :8020, console :3100, worker
```

### Verifying coverage first

The pipeline can only find signs where the imagery provider has been. Before
expecting results in a new city:

```bash
export MAPILLARY_TOKEN='MLY|...'
make coverage-probe
```

It reports how many images and sign features exist in one central tile and ends with
a verdict. No coverage means no signs will be found there — which is a fact about the
imagery, not about the street.

### Tests

```bash
make test          # backend and ML
make web-test      # frontend units
make e2e           # browser, against a real stack
```

---

## Architecture

```
browser ── Next.js console ── FastAPI ── PostgreSQL + PostGIS
                                 │
                              Redis ── RQ worker ── Nominatim / Overpass  (street → corridor)
                                                 ── Mapillary            (imagery + detections)
                                                 ── CLIP / linear probe  (classification)
```

| Path | What lives there |
|---|---|
| `apps/web` | Next.js console: dashboard, maps, review queue, settings |
| `services/api` | FastAPI: auth, surveys, signs, labels, exports, stats |
| `services/worker` | The pipeline: corridor, tiling, imagery, cropping |
| `packages/ml` | Classification: CLIP zero-shot, the trained probe, the shared encoder |
| `tests` | Backend, ML, and browser tests |

Deeper detail in [`docs/`](docs/): [architecture](docs/architecture.md),
[pipeline](docs/pipeline.md), [model](docs/model.md),
[deployment](docs/deployment.md), [security](docs/security.md).

---

## Honest limitations

- **Classification is not trained yet.** Out of the box it runs CLIP zero-shot, which
  is frequently wrong on regulatory signs — it will confidently call a pedestrian
  crossing a guide sign. The review queue exists to fix exactly this; see
  [docs/model.md](docs/model.md).
- **Coverage is the imagery provider's coverage.** No imagery on a street means no
  signs found there, which is not the same as no signs being there. Surveys say so
  rather than reporting zero.
- **Everyone in an organisation sees all of its surveys.** Tenancy separates
  organisations; there is no per-user or per-project restriction inside one.
- **Positions are as accurate as the imagery provider's.** Good enough to find a sign
  on a street, not good enough for cadastre.

---

## Licence

MIT.
