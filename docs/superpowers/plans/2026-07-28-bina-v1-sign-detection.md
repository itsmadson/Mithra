# Bina v1 — Sign Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw a bounding box on a map of Mashhad and get a counted, classified, exportable inventory of the road signs inside it.

**Architecture:** Mapillary supplies street-level imagery and precomputed sign detections; its `/map_features` endpoint returns one record per *physical* sign, which makes counting a query rather than a clustering problem. We crop each detection out of its source image and run our own classifier to place it in a four-class Persian sign taxonomy. Classification cold-starts on CLIP zero-shot and improves through an in-app labeling queue. Postgres/PostGIS is the only state shared between the Next.js frontend, the FastAPI backend, and the RQ worker.

**Tech Stack:** Next.js 15 (App Router, TypeScript), next-intl, MapLibre GL, FastAPI, SQLAlchemy 2 + Alembic + GeoAlchemy2, Postgres 16 + PostGIS 3.4, Redis + RQ, httpx, Pillow, mapbox-vector-tile, open_clip (CLIP ViT-B/32), pytest + respx, Playwright.

## Global Constraints

- **Mapillary bbox queries must be strictly smaller than 0.01 degrees square.** Every outbound bbox is tiled first. This is a hard API limit formalized 2026-01-16, not a guideline.
- **Auth header format is `Authorization: OAuth {token}`** — not `Bearer`. Token format is `MLY|...`.
- **Only the worker may make outbound calls to Mapillary.** The API and web tiers never do. The worker honours `HTTPS_PROXY`.
- **The token is read from the `MAPILLARY_TOKEN` environment variable and is never logged, never returned in an API response, and never committed.**
- **CI makes no live network calls.** All HTTP in tests is mocked with `respx`.
- **The four sign classes are fixed:** `direction_guide`, `street_name`, `city_entry`, `informational`. Plus `unknown` for anything unclassifiable. Class keys are the database values; display names are translation keys.
- **Counts are never silently reduced by failures.** Every count response carries a `failed_count` alongside it.
- **Python 3.12+. Node 20+.**
- **Default locale is `fa` with RTL.** `en` is secondary.
- **Reference spec:** `docs/superpowers/specs/2026-07-28-bina-sign-detection-design.md`

### Note on VCR

The spec calls for VCR fixtures for the Mapillary API. In practice: unit tests use `respx` with hand-written response payloads (deterministic, no token needed, runs in CI). Task 3 additionally includes a single opt-in live test, skipped unless `MAPILLARY_TOKEN` is set, that records a real cassette for coverage verification. This satisfies the spec's intent — CI never touches the network — while unblocking work before a token exists.

---

## File Structure

```
bina/
├── docker-compose.yml              Postgres+PostGIS, Redis
├── Makefile                        test / dev / migrate entrypoints
├── services/api/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/versions/        Alembic migrations
│   └── mithra_api/
│       ├── main.py                 FastAPI app assembly only
│       ├── config.py               env settings
│       ├── db.py                   engine + session
│       ├── models.py               SQLAlchemy ORM: Job, JobTile, Sign, Label, ModelVersion
│       ├── schemas.py              Pydantic request/response
│       └── routes/
│           ├── jobs.py             POST /jobs, GET /jobs/{id}
│           ├── signs.py            GET /jobs/{id}/signs
│           ├── export.py           GET /jobs/{id}/export.{csv,geojson}
│           └── labels.py           GET /labels/queue, POST /labels
├── services/worker/
│   └── mithra_worker/
│       ├── tiler.py                bbox → legal tiles (pure)
│       ├── mapillary.py            HTTP client (auth, proxy, retry)
│       ├── geometry.py             base64 MVT → pixel polygon (pure)
│       ├── cropper.py              image fetch + crop
│       └── pipeline.py             job runner, ties the above together
├── packages/ml/
│   └── mithra_ml/
│       ├── registry.py             model version resolution
│       └── clip_classifier.py      zero-shot classifier
├── apps/web/
│   ├── messages/{fa,en}.json       translations
│   └── src/
│       ├── app/[locale]/layout.tsx      RTL + locale wiring
│       ├── app/[locale]/page.tsx        map + bbox draw + submit
│       ├── app/[locale]/jobs/[id]/page.tsx   results
│       ├── app/[locale]/label/page.tsx       labeling queue
│       ├── components/BboxMap.tsx       MapLibre + rectangle draw
│       ├── components/CountsPanel.tsx   per-class counts
│       ├── components/SignTable.tsx     results table
│       └── lib/api.ts                   typed fetch client
└── tests/                          pytest (unit + integration), e2e/ (Playwright)
```

Boundaries that matter: `tiler.py` and `geometry.py` are pure functions with no I/O and are the most heavily tested files. `mapillary.py` knows about HTTP but nothing about signs. `mithra_ml` knows about images and classes but nothing about HTTP, jobs, or the database. `pipeline.py` is the only file that knows about all of them.

---

### Task 1: Scaffold, database, and the coverage probe

This is the blocker-clearing task. It ends with a runnable command that answers "does Mashhad actually have Mapillary coverage?" — the question that decides whether the rest of this plan survives.

**Files:**
- Create: `docker-compose.yml`, `Makefile`, `services/api/pyproject.toml`, `services/api/mithra_api/config.py`, `services/api/mithra_api/db.py`, `scripts/check_coverage.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_USER: bina
      POSTGRES_PASSWORD: bina
      POSTGRES_DB: bina
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bina"]
      interval: 2s
      timeout: 3s
      retries: 20
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

- [ ] **Step 2: Write `services/api/pyproject.toml`**

```toml
[project]
name = "bina"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy>=2.0",
  "geoalchemy2>=0.15",
  "alembic>=1.13",
  "psycopg[binary]>=3.2",
  "pydantic-settings>=2.5",
  "httpx>=0.27",
  "rq>=1.16",
  "redis>=5.0",
  "pillow>=10.4",
  "mapbox-vector-tile>=2.1",
  "shapely>=2.0",
]

[project.optional-dependencies]
ml = ["torch>=2.4", "open_clip_torch>=2.26"]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "respx>=0.21", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["../../tests"]
pythonpath = [".", "../worker", "../../packages/ml"]
```

- [ ] **Step 3: Write the failing test**

`tests/test_config.py`:

```python
import pytest
from mithra_api.config import Settings


def test_settings_reads_mapillary_token(monkeypatch):
    monkeypatch.setenv("MAPILLARY_TOKEN", "MLY|test|secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://bina:bina@localhost/bina")
    s = Settings()
    assert s.mapillary_token == "MLY|test|secret"


def test_settings_never_leaks_token_in_repr(monkeypatch):
    monkeypatch.setenv("MAPILLARY_TOKEN", "MLY|test|secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://bina:bina@localhost/bina")
    s = Settings()
    assert "secret" not in repr(s)


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("MAPILLARY_TOKEN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://bina:bina@localhost/bina")
    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 4: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_api.config'`

- [ ] **Step 5: Implement `config.py`**

```python
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mapillary_token: SecretStr
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    https_proxy: str | None = None
    crop_dir: str = "./data/crops"
    low_confidence_threshold: float = 0.45

    @field_validator("mapillary_token")
    @classmethod
    def _token_shape(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().startswith("MLY|"):
            raise ValueError("MAPILLARY_TOKEN must start with 'MLY|'")
        return v


settings = None


def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = Settings()
    return settings
```

`SecretStr` is what makes `repr()` safe — it renders as `**********`.

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 7: Implement `db.py`**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from mithra_api.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Iterator[Session]:
    get_engine()
    with _SessionLocal() as session:
        yield session
```

- [ ] **Step 8: Write the coverage probe**

`scripts/check_coverage.py`:

```python
"""Answer the blocking question: does Mashhad have usable Mapillary sign coverage?

Usage: MAPILLARY_TOKEN=... python scripts/check_coverage.py
"""

import os
import sys
from collections import Counter

import httpx

# Central Mashhad, one Mapillary-legal tile (< 0.01 deg square).
BBOX = "59.600,36.293,59.609,36.302"
GRAPH = "https://graph.mapillary.com"


def main() -> int:
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        print("MAPILLARY_TOKEN not set", file=sys.stderr)
        return 2

    client = httpx.Client(
        headers={"Authorization": f"OAuth {token}"},
        timeout=30.0,
        proxy=os.environ.get("HTTPS_PROXY"),
    )

    imgs = client.get(f"{GRAPH}/images", params={"bbox": BBOX, "limit": 100, "fields": "id,captured_at"})
    print(f"images: HTTP {imgs.status_code}")
    if imgs.status_code != 200:
        print(imgs.text[:500])
        return 1
    image_data = imgs.json().get("data", [])
    print(f"images found: {len(image_data)}")

    feats = client.get(
        f"{GRAPH}/map_features",
        params={"bbox": BBOX, "limit": 500, "fields": "id,object_value,geometry"},
    )
    print(f"map_features: HTTP {feats.status_code}")
    if feats.status_code != 200:
        print(feats.text[:500])
        return 1
    features = feats.json().get("data", [])
    print(f"sign features found: {len(features)}")

    counts = Counter(f.get("object_value", "?").split("--")[0] for f in features)
    for category, n in counts.most_common():
        print(f"  {category}: {n}")

    if not features:
        print("\nVERDICT: no sign coverage in this tile. Widen the probe or reconsider imagery source.")
        return 1
    print("\nVERDICT: coverage exists. Proceed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Write the `Makefile`**

```makefile
.PHONY: up down test coverage-probe
up:
	docker compose up -d
	@until docker compose exec -T db pg_isready -U bina >/dev/null 2>&1; do sleep 1; done

down:
	docker compose down -v

test:
	cd services/api && pytest ../../tests -v

coverage-probe:
	python scripts/check_coverage.py
```

- [ ] **Step 10: Run the probe**

Run: `make coverage-probe`
Expected: prints image and sign feature counts and a VERDICT line.

**STOP HERE if the verdict is "no sign coverage."** Report the numbers and stop. Everything downstream assumes coverage exists; building it against an empty data source wastes the effort. The classifier and labeling design survive a source change, the ingestion path does not.

- [ ] **Step 11: Commit**

```bash
git add docker-compose.yml Makefile services/api tests scripts
git commit -m "feat: scaffold api package, database config, and Mapillary coverage probe"
```

---

### Task 2: The tiler

**Files:**
- Create: `services/worker/mithra_worker/tiler.py`
- Test: `tests/test_tiler.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Bbox = tuple[float, float, float, float]` (west, south, east, north) and `split_bbox(bbox: Bbox, max_side: float = 0.009) -> list[Bbox]`

- [ ] **Step 1: Write the failing test**

`tests/test_tiler.py`:

```python
import pytest
from mithra_worker.tiler import MAX_SIDE, split_bbox


def test_small_bbox_returns_itself():
    bbox = (59.600, 36.293, 59.605, 36.298)
    assert split_bbox(bbox) == [bbox]


def test_large_bbox_is_split():
    bbox = (59.60, 36.29, 59.64, 36.33)
    tiles = split_bbox(bbox)
    assert len(tiles) > 1


def test_every_tile_is_under_the_api_limit():
    bbox = (59.60, 36.29, 59.64, 36.33)
    for w, s, e, n in split_bbox(bbox):
        assert e - w < 0.01
        assert n - s < 0.01


def test_tiles_cover_the_whole_bbox():
    w0, s0, e0, n0 = (59.60, 36.29, 59.64, 36.33)
    tiles = split_bbox((w0, s0, e0, n0))
    assert min(t[0] for t in tiles) == pytest.approx(w0)
    assert min(t[1] for t in tiles) == pytest.approx(s0)
    assert max(t[2] for t in tiles) == pytest.approx(e0)
    assert max(t[3] for t in tiles) == pytest.approx(n0)


def test_tiles_do_not_overlap():
    tiles = split_bbox((59.60, 36.29, 59.64, 36.33))
    assert len(tiles) == len(set(tiles))
    xs = sorted({(t[0], t[2]) for t in tiles})
    for (_, prev_e), (next_w, _) in zip(xs, xs[1:]):
        assert prev_e == pytest.approx(next_w)


def test_bbox_exactly_on_the_limit_is_split():
    # 0.01 is NOT strictly smaller than 0.01, so it must be split.
    tiles = split_bbox((59.60, 36.29, 59.61, 36.30))
    assert len(tiles) > 1
    for w, _, e, _ in tiles:
        assert e - w < 0.01


def test_max_side_is_below_the_api_limit():
    assert MAX_SIDE < 0.01


def test_inverted_bbox_raises():
    with pytest.raises(ValueError):
        split_bbox((59.64, 36.29, 59.60, 36.33))


def test_degenerate_bbox_raises():
    with pytest.raises(ValueError):
        split_bbox((59.60, 36.29, 59.60, 36.33))
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_tiler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_worker.tiler'`

- [ ] **Step 3: Implement the tiler**

```python
"""Split a user bbox into Mapillary-legal tiles.

Mapillary requires every bbox query to be strictly smaller than 0.01 degrees
square. MAX_SIDE sits just under that so floating-point addition across many
tiles can never drift over the limit.
"""

import math

Bbox = tuple[float, float, float, float]  # west, south, east, north

MAX_SIDE = 0.009


def split_bbox(bbox: Bbox, max_side: float = MAX_SIDE) -> list[Bbox]:
    west, south, east, north = bbox
    if east <= west or north <= south:
        raise ValueError(f"bbox must have positive extent, got {bbox!r}")

    cols = math.ceil((east - west) / max_side)
    rows = math.ceil((north - south) / max_side)
    col_step = (east - west) / cols
    row_step = (north - south) / rows

    tiles: list[Bbox] = []
    for r in range(rows):
        for c in range(cols):
            tiles.append((
                west + c * col_step,
                south + r * row_step,
                west + (c + 1) * col_step if c < cols - 1 else east,
                south + (r + 1) * row_step if r < rows - 1 else north,
            ))
    return tiles
```

Using the exact original edge for the last row and column is what makes the coverage test pass exactly rather than approximately — accumulated float addition would otherwise land just short of the boundary and silently drop signs at the edge.

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_tiler.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add services/worker/mithra_worker/tiler.py tests/test_tiler.py
git commit -m "feat: split user bboxes into Mapillary-legal tiles

Mapillary rejects any bbox query 0.01 degrees or larger. Tiles use the
original edge coordinates on the last row and column so float drift cannot
leave an uncovered strip where signs would be silently missed."
```

---

### Task 3: The Mapillary client

**Files:**
- Create: `services/worker/mithra_worker/mapillary.py`
- Test: `tests/test_mapillary.py`

**Interfaces:**
- Consumes: `Bbox` from `mithra_worker.tiler`, `get_settings()` from `mithra_api.config`
- Produces:
  - `class MapillaryError(Exception)`, `class MapillaryAuthError(MapillaryError)`, `class MapillaryRateLimited(MapillaryError)`
  - `class MapillaryClient` with:
    - `get_sign_features(bbox: Bbox, limit: int = 2000) -> list[dict]` — each dict has `id`, `object_value`, `object_type`, `geometry`, `images`
    - `get_detections(image_id: str) -> list[dict]` — each dict has `id`, `geometry` (base64 str), `value`
    - `get_image_meta(image_id: str) -> dict` — has `id`, `width`, `height`, `thumb_2048_url`
    - `download(url: str) -> bytes`

- [ ] **Step 1: Write the failing test**

`tests/test_mapillary.py`:

```python
import httpx
import pytest
import respx

from mithra_worker.mapillary import (
    GRAPH,
    MapillaryAuthError,
    MapillaryClient,
    MapillaryRateLimited,
)

BBOX = (59.600, 36.293, 59.605, 36.298)


@pytest.fixture
def client():
    return MapillaryClient(token="MLY|test|secret", max_retries=3, backoff_base=0.0)


@respx.mock
def test_sends_oauth_header_not_bearer(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client.get_sign_features(BBOX)
    assert route.calls[0].request.headers["authorization"] == "OAuth MLY|test|secret"


@respx.mock
def test_requests_only_the_traffic_sign_layer(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    client.get_sign_features(BBOX)
    assert route.calls[0].request.url.params["object_types"] == "trafficsign"


@respx.mock
def test_returns_feature_dicts(client):
    respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(200, json={"data": [
            {"id": "1", "object_value": "information--parking--g1",
             "object_type": "trafficsign",
             "geometry": {"type": "Point", "coordinates": [59.601, 36.294]},
             "images": {"data": [{"id": "img1"}]}},
        ]})
    )
    features = client.get_sign_features(BBOX)
    assert features[0]["id"] == "1"
    assert features[0]["geometry"]["coordinates"] == [59.601, 36.294]


@respx.mock
def test_auth_failure_raises_immediately_without_retry(client):
    route = respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(401, json={"error": "bad token"})
    )
    with pytest.raises(MapillaryAuthError):
        client.get_sign_features(BBOX)
    assert route.call_count == 1


@respx.mock
def test_rate_limit_is_retried_then_succeeds(client):
    route = respx.get(f"{GRAPH}/map_features").mock(side_effect=[
        httpx.Response(429),
        httpx.Response(429),
        httpx.Response(200, json={"data": []}),
    ])
    assert client.get_sign_features(BBOX) == []
    assert route.call_count == 3


@respx.mock
def test_rate_limit_beyond_retries_raises(client):
    respx.get(f"{GRAPH}/map_features").mock(return_value=httpx.Response(429))
    with pytest.raises(MapillaryRateLimited):
        client.get_sign_features(BBOX)


@respx.mock
def test_server_error_is_retried(client):
    route = respx.get(f"{GRAPH}/map_features").mock(side_effect=[
        httpx.Response(500),
        httpx.Response(200, json={"data": []}),
    ])
    client.get_sign_features(BBOX)
    assert route.call_count == 2


@respx.mock
def test_get_detections_hits_the_image_scoped_endpoint(client):
    route = respx.get(f"{GRAPH}/img1/detections").mock(
        return_value=httpx.Response(200, json={"data": [
            {"id": "d1", "geometry": "GmYKBHRlc3Q=", "value": "information--parking--g1"},
        ]})
    )
    detections = client.get_detections("img1")
    assert detections[0]["geometry"] == "GmYKBHRlc3Q="
    assert route.called


@respx.mock
def test_get_image_meta_requests_dimensions_and_thumb(client):
    route = respx.get(f"{GRAPH}/img1").mock(
        return_value=httpx.Response(200, json={
            "id": "img1", "width": 4096, "height": 3072,
            "thumb_2048_url": "https://cdn.example/img1.jpg",
        })
    )
    meta = client.get_image_meta("img1")
    assert meta["width"] == 4096
    fields = route.calls[0].request.url.params["fields"]
    assert "thumb_2048_url" in fields and "width" in fields and "height" in fields


@respx.mock
def test_token_is_not_included_in_exception_messages(client):
    respx.get(f"{GRAPH}/map_features").mock(
        return_value=httpx.Response(401, json={"error": "bad token"})
    )
    with pytest.raises(MapillaryAuthError) as exc:
        client.get_sign_features(BBOX)
    assert "secret" not in str(exc.value)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_mapillary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_worker.mapillary'`

- [ ] **Step 3: Implement the client**

```python
"""HTTP access to the Mapillary graph API.

Knows about auth, proxying, and retry. Knows nothing about signs, jobs, or
the database — callers interpret the payloads.
"""

import os
import time
from typing import Any

import httpx

from mithra_worker.tiler import Bbox

GRAPH = "https://graph.mapillary.com"

FEATURE_FIELDS = "id,object_value,object_type,geometry,images,first_seen_at,last_seen_at"
DETECTION_FIELDS = "id,geometry,value"
IMAGE_FIELDS = "id,width,height,thumb_2048_url,captured_at,geometry"

RETRY_STATUSES = {429, 500, 502, 503, 504}


class MapillaryError(Exception):
    """Base for all Mapillary transport failures."""


class MapillaryAuthError(MapillaryError):
    """Credentials rejected. Never retried."""


class MapillaryRateLimited(MapillaryError):
    """Rate limited beyond the retry budget."""


class MapillaryClient:
    def __init__(
        self,
        token: str,
        *,
        max_retries: int = 4,
        backoff_base: float = 1.0,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._client = httpx.Client(
            headers={"Authorization": f"OAuth {token}"},
            timeout=timeout,
            proxy=proxy if proxy is not None else os.environ.get("HTTPS_PROXY"),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MapillaryClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        last_status = None
        for attempt in range(self._max_retries):
            response = self._client.get(f"{GRAPH}{path}", params=params)
            if response.status_code in (401, 403):
                # Deliberately does not echo the response body, which can
                # contain the submitted token.
                raise MapillaryAuthError(
                    f"Mapillary rejected credentials (HTTP {response.status_code}) for {path}"
                )
            if response.status_code in RETRY_STATUSES:
                last_status = response.status_code
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2**attempt))
                continue
            response.raise_for_status()
            return response.json()
        raise MapillaryRateLimited(
            f"Mapillary returned {last_status} for {path} after {self._max_retries} attempts"
        )

    def get_sign_features(self, bbox: Bbox, limit: int = 2000) -> list[dict]:
        west, south, east, north = bbox
        payload = self._get("/map_features", {
            "bbox": f"{west},{south},{east},{north}",
            "object_types": "trafficsign",
            "fields": FEATURE_FIELDS,
            "limit": limit,
        })
        return payload.get("data", [])

    def get_detections(self, image_id: str) -> list[dict]:
        payload = self._get(f"/{image_id}/detections", {"fields": DETECTION_FIELDS})
        return payload.get("data", [])

    def get_image_meta(self, image_id: str) -> dict:
        return self._get(f"/{image_id}", {"fields": IMAGE_FIELDS})

    def download(self, url: str) -> bytes:
        response = self._client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_mapillary.py -v`
Expected: 10 passed

- [ ] **Step 5: Add the opt-in live cassette test**

Append to `tests/test_mapillary.py`:

```python
import json
import os
from pathlib import Path

CASSETTE = Path(__file__).parent / "fixtures" / "mashhad_features.json"


@pytest.mark.skipif(not os.environ.get("MAPILLARY_TOKEN"), reason="needs a real token")
def test_record_live_mashhad_cassette():
    """Not a CI test. Records a real payload for fixture use and sanity checks it."""
    live = MapillaryClient(token=os.environ["MAPILLARY_TOKEN"])
    features = live.get_sign_features(BBOX)
    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    CASSETTE.write_text(json.dumps(features[:50], indent=2))
    for feature in features:
        assert feature["object_type"] == "trafficsign"
        assert feature["geometry"]["type"] == "Point"
```

- [ ] **Step 6: Run the suite and confirm the live test skips without a token**

Run: `cd services/api && pytest ../../tests/test_mapillary.py -v`
Expected: 10 passed, 1 skipped

- [ ] **Step 7: Commit**

```bash
git add services/worker/mithra_worker/mapillary.py tests/test_mapillary.py
git commit -m "feat: add Mapillary graph API client

Auth uses the OAuth header scheme Mapillary requires, not Bearer. 401 and
403 fail fast since retrying rejected credentials only burns quota, while
429 and 5xx back off exponentially. Error messages omit response bodies,
which can echo the submitted token."
```

---

### Task 4: Detection geometry decoding

Mapillary returns detection outlines as a base64-encoded Mapbox vector tile. Decoding it is the step most likely to be silently wrong, so it gets its own pure module and its own tests.

**Files:**
- Create: `services/worker/mithra_worker/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: nothing
- Produces: `decode_detection_geometry(encoded: str, image_width: int, image_height: int) -> tuple[int, int, int, int]` returning a pixel bbox `(left, top, right, bottom)`, and `GeometryDecodeError`

- [ ] **Step 1: Write the failing test**

`tests/test_geometry.py`:

```python
import base64

import mapbox_vector_tile
import pytest

from mithra_worker.geometry import GeometryDecodeError, decode_detection_geometry

EXTENT = 4096


def encode(coords: list[tuple[int, int]]) -> str:
    """Build a base64 MVT payload the way Mapillary does."""
    tile = mapbox_vector_tile.encode({
        "name": "mpy-or",
        "features": [{
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {},
        }],
    }, extents=EXTENT)
    return base64.b64encode(tile).decode()


def test_decodes_a_centered_square_to_pixel_bbox():
    # A square covering the middle half of the tile, in MVT units.
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode([
        (quarter, quarter), (three_quarters, quarter),
        (three_quarters, three_quarters), (quarter, three_quarters),
        (quarter, quarter),
    ])
    left, top, right, bottom = decode_detection_geometry(encoded, 4000, 2000)
    assert (right - left) == pytest.approx(2000, abs=8)
    assert (bottom - top) == pytest.approx(1000, abs=8)


def test_scales_with_image_dimensions():
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode([
        (quarter, quarter), (three_quarters, quarter),
        (three_quarters, three_quarters), (quarter, three_quarters),
        (quarter, quarter),
    ])
    small = decode_detection_geometry(encoded, 1000, 500)
    large = decode_detection_geometry(encoded, 2000, 1000)
    assert (large[2] - large[0]) == pytest.approx(2 * (small[2] - small[0]), abs=8)


def test_result_is_clamped_inside_the_image():
    encoded = encode([(0, 0), (EXTENT, 0), (EXTENT, EXTENT), (0, EXTENT), (0, 0)])
    left, top, right, bottom = decode_detection_geometry(encoded, 800, 600)
    assert left >= 0 and top >= 0
    assert right <= 800 and bottom <= 600


def test_returns_integers():
    encoded = encode([(100, 100), (300, 100), (300, 300), (100, 300), (100, 100)])
    assert all(isinstance(v, int) for v in decode_detection_geometry(encoded, 1024, 768))


def test_bbox_is_ordered_left_top_right_bottom():
    encoded = encode([(100, 100), (300, 100), (300, 300), (100, 300), (100, 100)])
    left, top, right, bottom = decode_detection_geometry(encoded, 1024, 768)
    assert left < right and top < bottom


def test_garbage_base64_raises_decode_error():
    with pytest.raises(GeometryDecodeError):
        decode_detection_geometry("not-valid-base64!!", 1024, 768)


def test_empty_geometry_raises_decode_error():
    encoded = base64.b64encode(mapbox_vector_tile.encode({"name": "mpy-or", "features": []})).decode()
    with pytest.raises(GeometryDecodeError):
        decode_detection_geometry(encoded, 1024, 768)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_worker.geometry'`

- [ ] **Step 3: Implement the decoder**

```python
"""Decode Mapillary detection geometry into a pixel bounding box.

Mapillary encodes each detection outline as a base64 Mapbox vector tile whose
coordinates run 0..extent (4096). Normalising by the extent and multiplying by
the real image dimensions maps them back onto image pixels.
"""

import base64

import mapbox_vector_tile

DEFAULT_EXTENT = 4096


class GeometryDecodeError(Exception):
    """The detection geometry could not be decoded into a usable bbox."""


def _iter_points(geometry: dict):
    coords = geometry.get("coordinates", [])
    stack = [coords]
    while stack:
        item = stack.pop()
        if not isinstance(item, (list, tuple)) or not item:
            continue
        if len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
            yield float(item[0]), float(item[1])
        else:
            stack.extend(item)


def decode_detection_geometry(
    encoded: str, image_width: int, image_height: int
) -> tuple[int, int, int, int]:
    try:
        tile = mapbox_vector_tile.decode(base64.b64decode(encoded, validate=True))
    except Exception as exc:  # noqa: BLE001 - any malformed payload is one failure mode
        raise GeometryDecodeError(f"could not decode detection geometry: {exc}") from exc

    points: list[tuple[float, float]] = []
    extent = DEFAULT_EXTENT
    for layer in tile.values():
        extent = layer.get("extent", DEFAULT_EXTENT) or DEFAULT_EXTENT
        for feature in layer.get("features", []):
            points.extend(_iter_points(feature.get("geometry", {})))

    if not points:
        raise GeometryDecodeError("detection geometry contained no coordinates")

    xs = [p[0] / extent * image_width for p in points]
    ys = [p[1] / extent * image_height for p in points]

    left = max(0, int(min(xs)))
    top = max(0, int(min(ys)))
    right = min(image_width, int(max(xs)) + 1)
    bottom = min(image_height, int(max(ys)) + 1)

    if right <= left or bottom <= top:
        raise GeometryDecodeError("detection geometry produced an empty bbox")
    return left, top, right, bottom
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_geometry.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add services/worker/mithra_worker/geometry.py tests/test_geometry.py
git commit -m "feat: decode Mapillary detection geometry to pixel bboxes

Detection outlines arrive as base64 Mapbox vector tiles in 0..4096 tile
units. Normalising by the layer extent rather than a hardcoded 4096 keeps
this correct if Mapillary ever changes it."
```

---

### Task 5: The cropper

**Files:**
- Create: `services/worker/mithra_worker/cropper.py`
- Test: `tests/test_cropper.py`

**Interfaces:**
- Consumes: `decode_detection_geometry` from `mithra_worker.geometry`
- Produces: `crop_detection(image_bytes: bytes, encoded_geometry: str, image_width: int, image_height: int, padding: float = 0.10) -> PIL.Image.Image` and `CropError`

- [ ] **Step 1: Write the failing test**

`tests/test_cropper.py`:

```python
import base64
import io

import mapbox_vector_tile
import pytest
from PIL import Image

from mithra_worker.cropper import CropError, crop_detection

EXTENT = 4096


def encode_box(x0: int, y0: int, x1: int, y1: int) -> str:
    tile = mapbox_vector_tile.encode({
        "name": "mpy-or",
        "features": [{
            "geometry": {"type": "Polygon",
                         "coordinates": [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]},
            "properties": {},
        }],
    }, extents=EXTENT)
    return base64.b64encode(tile).decode()


def make_image(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_returns_a_cropped_image():
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    crop = crop_detection(make_image(800, 600), encode_box(quarter, quarter, three_quarters, three_quarters), 800, 600, padding=0.0)
    assert isinstance(crop, Image.Image)
    assert crop.width == pytest.approx(400, abs=4)
    assert crop.height == pytest.approx(300, abs=4)


def test_padding_expands_the_crop():
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode_box(quarter, quarter, three_quarters, three_quarters)
    tight = crop_detection(make_image(800, 600), encoded, 800, 600, padding=0.0)
    padded = crop_detection(make_image(800, 600), encoded, 800, 600, padding=0.25)
    assert padded.width > tight.width


def test_padding_is_clamped_at_the_image_edge():
    crop = crop_detection(make_image(800, 600), encode_box(0, 0, EXTENT, EXTENT), 800, 600, padding=0.5)
    assert crop.width <= 800
    assert crop.height <= 600


def test_corrupt_image_bytes_raise_crop_error():
    with pytest.raises(CropError):
        crop_detection(b"not an image", encode_box(100, 100, 300, 300), 800, 600)


def test_undecodable_geometry_raises_crop_error():
    with pytest.raises(CropError):
        crop_detection(make_image(800, 600), "not-base64!!", 800, 600)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_cropper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_worker.cropper'`

- [ ] **Step 3: Implement the cropper**

```python
"""Cut a detected sign out of its source image.

Padding matters: a sign cropped exactly to its detection outline loses the
border and backing plate, which are strong signals for distinguishing a
street-name plate from a direction sign.
"""

import io

from PIL import Image, UnidentifiedImageError

from mithra_worker.geometry import GeometryDecodeError, decode_detection_geometry


class CropError(Exception):
    """The detection could not be cropped out of its source image."""


def crop_detection(
    image_bytes: bytes,
    encoded_geometry: str,
    image_width: int,
    image_height: int,
    padding: float = 0.10,
) -> Image.Image:
    try:
        left, top, right, bottom = decode_detection_geometry(
            encoded_geometry, image_width, image_height
        )
    except GeometryDecodeError as exc:
        raise CropError(str(exc)) from exc

    pad_x = int((right - left) * padding)
    pad_y = int((bottom - top) * padding)
    box = (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(image_width, right + pad_x),
        min(image_height, bottom + pad_y),
    )

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CropError(f"could not open source image: {exc}") from exc

    return image.convert("RGB").crop(box)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_cropper.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/worker/mithra_worker/cropper.py tests/test_cropper.py
git commit -m "feat: crop detected signs out of source imagery

Crops carry 10% padding by default. The plate border and backing are part of
what distinguishes a street-name sign from a direction sign, so a crop tight
to the detection outline throws away signal the classifier needs."
```

---

### Task 6: Classifier and model registry

**Files:**
- Create: `packages/ml/mithra_ml/__init__.py`, `packages/ml/mithra_ml/registry.py`, `packages/ml/mithra_ml/clip_classifier.py`
- Test: `tests/test_registry.py`, `tests/test_clip_classifier.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `SIGN_CLASSES: tuple[str, ...] = ("direction_guide", "street_name", "city_entry", "informational")`
  - `UNKNOWN = "unknown"`
  - `@dataclass(frozen=True) class Prediction: sign_class: str; confidence: float; model_version: str`
  - `class Classifier(Protocol): def predict(self, image: PIL.Image.Image) -> Prediction: ...`
  - `class ClipZeroShotClassifier(Classifier)` with `__init__(self, threshold: float = 0.45, model_name: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k")` and property `version: str`
  - `get_classifier() -> Classifier` in `registry.py` (cached singleton)

- [ ] **Step 1: Write the failing registry test**

`tests/test_registry.py`:

```python
from PIL import Image

from mithra_ml import UNKNOWN, Prediction
from mithra_ml.registry import get_classifier, register_classifier, reset_registry


class FakeClassifier:
    version = "fake-v1"

    def predict(self, image):
        return Prediction(sign_class="street_name", confidence=0.9, model_version=self.version)


def test_registry_returns_the_registered_classifier():
    reset_registry()
    register_classifier(FakeClassifier())
    assert get_classifier().version == "fake-v1"


def test_registry_returns_the_same_instance_each_call():
    reset_registry()
    register_classifier(FakeClassifier())
    assert get_classifier() is get_classifier()


def test_prediction_carries_the_model_version():
    reset_registry()
    register_classifier(FakeClassifier())
    prediction = get_classifier().predict(Image.new("RGB", (32, 32)))
    assert prediction.model_version == "fake-v1"
    assert prediction.sign_class != UNKNOWN
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_ml'`

- [ ] **Step 3: Implement `mithra_ml/__init__.py`**

```python
from dataclasses import dataclass
from typing import Protocol

from PIL.Image import Image

SIGN_CLASSES: tuple[str, ...] = (
    "direction_guide",
    "street_name",
    "city_entry",
    "informational",
)
UNKNOWN = "unknown"
ALL_CLASSES: tuple[str, ...] = SIGN_CLASSES + (UNKNOWN,)


@dataclass(frozen=True)
class Prediction:
    sign_class: str
    confidence: float
    model_version: str


class Classifier(Protocol):
    version: str

    def predict(self, image: Image) -> Prediction: ...
```

- [ ] **Step 4: Implement `mithra_ml/registry.py`**

```python
"""Resolves which classifier the pipeline uses.

Every prediction records its model version, so swapping the registered
classifier changes future results without rewriting past ones.
"""

from mithra_ml import Classifier

_classifier: Classifier | None = None


def register_classifier(classifier: Classifier) -> None:
    global _classifier
    _classifier = classifier


def reset_registry() -> None:
    global _classifier
    _classifier = None


def get_classifier() -> Classifier:
    global _classifier
    if _classifier is None:
        from mithra_ml.clip_classifier import ClipZeroShotClassifier

        _classifier = ClipZeroShotClassifier()
    return _classifier
```

- [ ] **Step 5: Run the registry tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_registry.py -v`
Expected: 3 passed

- [ ] **Step 6: Write the failing classifier test**

`tests/test_clip_classifier.py`:

```python
import pytest
from PIL import Image

from mithra_ml import SIGN_CLASSES, UNKNOWN
from mithra_ml.clip_classifier import PROMPTS, ClipZeroShotClassifier

torch = pytest.importorskip("torch")


def test_every_class_has_prompts_in_both_languages():
    for sign_class in SIGN_CLASSES:
        assert sign_class in PROMPTS
        prompts = PROMPTS[sign_class]
        assert len(prompts) >= 2
        assert any(any("؀" <= ch <= "ۿ" for ch in p) for p in prompts), (
            f"{sign_class} has no Persian prompt"
        )


def test_predict_returns_a_known_class_and_bounded_confidence():
    classifier = ClipZeroShotClassifier()
    prediction = classifier.predict(Image.new("RGB", (224, 224), (120, 140, 160)))
    assert prediction.sign_class in (*SIGN_CLASSES, UNKNOWN)
    assert 0.0 <= prediction.confidence <= 1.0


def test_low_confidence_predictions_become_unknown():
    classifier = ClipZeroShotClassifier(threshold=1.1)  # nothing can clear this
    prediction = classifier.predict(Image.new("RGB", (224, 224)))
    assert prediction.sign_class == UNKNOWN


def test_version_string_identifies_the_model():
    classifier = ClipZeroShotClassifier()
    assert "clip" in classifier.version.lower()
    assert classifier.predict(Image.new("RGB", (224, 224))).model_version == classifier.version


def test_grayscale_input_is_accepted():
    classifier = ClipZeroShotClassifier()
    assert classifier.predict(Image.new("L", (224, 224))).confidence >= 0.0
```

- [ ] **Step 7: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_clip_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_ml.clip_classifier'`

- [ ] **Step 8: Implement the classifier**

```python
"""Zero-shot sign classification with CLIP.

This exists so the product works on day one, before any labels are collected.
Prompts are bilingual because the signs carry Persian text and CLIP's Persian
grounding, while weaker than its English grounding, still contributes signal.
Everything below the confidence threshold becomes `unknown` and goes to the
top of the labeling queue — that queue is how this gets replaced by a
fine-tuned head.
"""

import functools

import torch
from PIL.Image import Image

from mithra_ml import SIGN_CLASSES, UNKNOWN, Prediction

PROMPTS: dict[str, list[str]] = {
    "direction_guide": [
        "a road direction sign with arrows pointing to destinations",
        "a green or blue highway guide sign showing place names",
        "تابلو مسیرنما با فلش و نام مقصد",
    ],
    "street_name": [
        "a street name plate mounted on a wall or pole",
        "a small rectangular sign showing the name of a street or alley",
        "تابلو نام معبر یا نام خیابان",
    ],
    "city_entry": [
        "a city entrance sign showing the name of a town",
        "a place name boundary sign at the edge of a city",
        "تابلو ورودی شهر با نام شهر",
    ],
    "informational": [
        "an information sign showing a service symbol like parking, hospital or fuel",
        "a blue service information sign with a pictogram",
        "تابلو اطلاعاتی خدمات مانند پارکینگ یا بیمارستان",
    ],
}


class ClipZeroShotClassifier:
    def __init__(
        self,
        threshold: float = 0.45,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
    ) -> None:
        self._threshold = threshold
        self._model_name = model_name
        self._pretrained = pretrained
        self.version = f"clip-zeroshot-{model_name}-{pretrained}-v1"

    @functools.cached_property
    def _loaded(self):
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            self._model_name, pretrained=self._pretrained
        )
        model.eval()
        tokenizer = open_clip.get_tokenizer(self._model_name)

        # One averaged text embedding per class, computed once.
        with torch.no_grad():
            class_embeddings = []
            for sign_class in SIGN_CLASSES:
                tokens = tokenizer(PROMPTS[sign_class])
                features = model.encode_text(tokens)
                features = features / features.norm(dim=-1, keepdim=True)
                averaged = features.mean(dim=0)
                class_embeddings.append(averaged / averaged.norm())
            text_matrix = torch.stack(class_embeddings)
        return model, preprocess, text_matrix

    def predict(self, image: Image) -> Prediction:
        model, preprocess, text_matrix = self._loaded
        tensor = preprocess(image.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            features = model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
            probabilities = (100.0 * features @ text_matrix.T).softmax(dim=-1)[0]

        best = int(probabilities.argmax())
        confidence = float(probabilities[best])
        if confidence < self._threshold:
            return Prediction(UNKNOWN, confidence, self.version)
        return Prediction(SIGN_CLASSES[best], confidence, self.version)
```

- [ ] **Step 9: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_clip_classifier.py -v`
Expected: 5 passed (downloads CLIP weights on first run; allow a few minutes)

- [ ] **Step 10: Commit**

```bash
git add packages/ml tests/test_registry.py tests/test_clip_classifier.py
git commit -m "feat: add CLIP zero-shot sign classifier and model registry

Zero-shot classification makes the product useful before a single label
exists, and the confidence threshold routes its weakest predictions straight
into the labeling queue that will eventually replace it. Class embeddings are
averaged over bilingual prompts and computed once at load."
```

---

### Task 7: Database schema

**Files:**
- Create: `services/api/mithra_api/models.py`, `services/api/alembic.ini`, `services/api/migrations/env.py`, `services/api/migrations/versions/0001_initial.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `Base` from `mithra_api.db`
- Produces: ORM classes `Job`, `JobTile`, `Sign`, `Label`, and enums `JobStatus`, `SignReason`

Columns other tasks rely on:
- `Job(id: UUID, bbox_west/south/east/north: float, status: str, reason: str|None, created_at, finished_at, tile_count: int, failed_tile_count: int)`
- `JobTile(id, job_id, west, south, east, north, status, error: str|None)`
- `Sign(id: UUID, job_id, mapillary_feature_id: str, image_id: str|None, geom: Point(4326), sign_class: str, confidence: float, model_version: str, mapillary_value: str|None, crop_path: str|None, needs_review: bool, reason: str|None, created_at)`
- `Label(id: UUID, sign_id, sign_class: str, created_at)`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:

```python
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mithra_api.db import Base
from mithra_api.models import Job, JobStatus, Label, Sign

DB_URL = "postgresql+psycopg://bina:bina@localhost:5432/bina"


@pytest.fixture
def session():
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)


def make_job(session) -> Job:
    job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.64, bbox_north=36.33)
    session.add(job)
    session.commit()
    return job


def test_new_job_starts_queued(session):
    assert make_job(session).status == JobStatus.QUEUED


def test_sign_stores_a_geographic_point(session):
    job = make_job(session)
    session.add(Sign(
        job_id=job.id, mapillary_feature_id="f1", image_id="i1",
        geom="SRID=4326;POINT(59.601 36.294)",
        sign_class="street_name", confidence=0.8, model_version="clip-v1",
    ))
    session.commit()
    assert session.scalar(select(Sign)).sign_class == "street_name"


def test_a_feature_cannot_be_counted_twice_in_one_job(session):
    job = make_job(session)
    for _ in range(2):
        session.add(Sign(
            job_id=job.id, mapillary_feature_id="dup",
            geom="SRID=4326;POINT(59.601 36.294)",
            sign_class="street_name", confidence=0.8, model_version="clip-v1",
        ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_the_same_feature_may_appear_in_two_different_jobs(session):
    first, second = make_job(session), make_job(session)
    for job in (first, second):
        session.add(Sign(
            job_id=job.id, mapillary_feature_id="shared",
            geom="SRID=4326;POINT(59.601 36.294)",
            sign_class="street_name", confidence=0.8, model_version="clip-v1",
        ))
    session.commit()
    assert len(session.scalars(select(Sign)).all()) == 2


def test_label_attaches_to_a_sign(session):
    job = make_job(session)
    sign = Sign(
        job_id=job.id, mapillary_feature_id="f1",
        geom="SRID=4326;POINT(59.601 36.294)",
        sign_class="unknown", confidence=0.1, model_version="clip-v1", needs_review=True,
    )
    session.add(sign)
    session.commit()
    session.add(Label(sign_id=sign.id, sign_class="city_entry"))
    session.commit()
    assert session.scalar(select(Label)).sign_class == "city_entry"
```

- [ ] **Step 2: Start the database and run the test to see it fail**

Run: `make up && cd services/api && pytest ../../tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_api.models'`

- [ ] **Step 3: Implement the models**

```python
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mithra_api.db import Base


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class SignReason:
    OK = "ok"
    CROP_FAILED = "crop_failed"
    NO_DETECTION = "no_detection"
    CLASSIFY_FAILED = "classify_failed"


class JobReason:
    NO_IMAGERY = "no_imagery"
    AUTH_FAILED = "auth_failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bbox_west: Mapped[float] = mapped_column(Float)
    bbox_south: Mapped[float] = mapped_column(Float)
    bbox_east: Mapped[float] = mapped_column(Float)
    bbox_north: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, index=True)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tile_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_tile_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    signs: Mapped[list["Sign"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    tiles: Mapped[list["JobTile"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobTile(Base):
    __tablename__ = "job_tiles"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    west: Mapped[float] = mapped_column(Float)
    south: Mapped[float] = mapped_column(Float)
    east: Mapped[float] = mapped_column(Float)
    north: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    job: Mapped[Job] = relationship(back_populates="tiles")


class Sign(Base):
    __tablename__ = "signs"
    __table_args__ = (
        UniqueConstraint("job_id", "mapillary_feature_id", name="uq_sign_per_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    mapillary_feature_id: Mapped[str] = mapped_column(String(64), index=True)
    image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geom: Mapped[str] = mapped_column(Geometry("POINT", srid=4326))
    sign_class: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(80))
    mapillary_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    crop_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(32), default=SignReason.OK)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="signs")


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signs.id", ondelete="CASCADE"), index=True)
    sign_class: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

The `uq_sign_per_job` constraint is the design's dedup guarantee expressed as a database rule rather than as careful application code.

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_models.py -v`
Expected: 5 passed

- [ ] **Step 5: Generate the Alembic migration**

```bash
cd services/api
alembic init -t async migrations 2>/dev/null || alembic init migrations
```

Edit `alembic.ini` to set `sqlalchemy.url = postgresql+psycopg://bina:bina@localhost:5432/bina`.
Edit `migrations/env.py` to add, above `target_metadata`:

```python
from mithra_api.db import Base
import mithra_api.models  # noqa: F401 - registers tables on Base.metadata

target_metadata = Base.metadata
```

Then:

```bash
alembic revision --autogenerate -m "initial schema"
```

- [ ] **Step 6: Add the PostGIS extension to the migration**

At the top of the generated `upgrade()` in `migrations/versions/*_initial_schema.py`:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
```

- [ ] **Step 7: Apply and verify the migration**

Run: `cd services/api && alembic upgrade head && alembic current`
Expected: prints the revision id with `(head)`

- [ ] **Step 8: Commit**

```bash
git add services/api/mithra_api/models.py services/api/alembic.ini services/api/migrations tests/test_models.py
git commit -m "feat: add job, tile, sign, and label schema

The unique constraint on (job_id, mapillary_feature_id) enforces the counting
guarantee at the database level: one physical sign can contribute at most one
row to a job's count, regardless of how many images observed it."
```

---

### Task 8: The pipeline

**Files:**
- Create: `services/worker/mithra_worker/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `split_bbox`, `MapillaryClient` (+ its exceptions), `crop_detection`, `CropError`, `get_classifier`, all ORM models
- Produces: `run_job(session: Session, job_id: uuid.UUID, client: MapillaryClient, classifier: Classifier, crop_dir: Path) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline.py`:

```python
import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from mithra_api.db import Base
from mithra_api.models import Job, JobStatus, JobReason, Sign, SignReason
from mithra_ml import Prediction
from mithra_worker.mapillary import MapillaryRateLimited
from mithra_worker.pipeline import run_job

DB_URL = "postgresql+psycopg://bina:bina@localhost:5432/bina"


@pytest.fixture
def session():
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)


@pytest.fixture
def job(session):
    j = Job(bbox_west=59.600, bbox_south=36.293, bbox_east=59.605, bbox_north=36.298)
    session.add(j)
    session.commit()
    return j


def jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (800, 600), (30, 60, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeClient:
    """Two images observing ONE physical sign — the dedup case."""

    def __init__(self, features=None, detections=None, raise_on_features=None):
        self.features = features if features is not None else [{
            "id": "feat1", "object_value": "information--parking--g1",
            "object_type": "trafficsign",
            "geometry": {"type": "Point", "coordinates": [59.601, 36.294]},
            "images": {"data": [{"id": "imgA"}, {"id": "imgB"}]},
        }]
        self.detections = detections if detections is not None else [
            {"id": "d1", "geometry": "ENCODED", "value": "information--parking--g1"}
        ]
        self.raise_on_features = raise_on_features
        self.download_calls = 0

    def get_sign_features(self, bbox, limit=2000):
        if self.raise_on_features:
            raise self.raise_on_features
        return self.features

    def get_detections(self, image_id):
        return self.detections

    def get_image_meta(self, image_id):
        return {"id": image_id, "width": 800, "height": 600,
                "thumb_2048_url": f"https://cdn.example/{image_id}.jpg"}

    def download(self, url):
        self.download_calls += 1
        return jpeg_bytes()


class FakeClassifier:
    version = "fake-v1"

    def predict(self, image):
        return Prediction("informational", 0.91, self.version)


def test_one_physical_sign_produces_exactly_one_row(session, job, monkeypatch, tmp_path):
    monkeypatch.setattr("mithra_worker.pipeline.crop_detection",
                        lambda *a, **k: Image.new("RGB", (64, 64)))
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    assert len(session.scalars(select(Sign)).all()) == 1


def test_job_succeeds_and_records_the_class(session, job, monkeypatch, tmp_path):
    monkeypatch.setattr("mithra_worker.pipeline.crop_detection",
                        lambda *a, **k: Image.new("RGB", (64, 64)))
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED
    sign = session.scalar(select(Sign))
    assert sign.sign_class == "informational"
    assert sign.model_version == "fake-v1"
    assert sign.mapillary_value == "information--parking--g1"


def test_crop_is_written_to_disk(session, job, monkeypatch, tmp_path):
    monkeypatch.setattr("mithra_worker.pipeline.crop_detection",
                        lambda *a, **k: Image.new("RGB", (64, 64)))
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    from pathlib import Path
    assert Path(session.scalar(select(Sign)).crop_path).exists()


def test_empty_coverage_succeeds_with_no_imagery_reason(session, job, tmp_path):
    run_job(session, job.id, FakeClient(features=[]), FakeClassifier(), tmp_path)
    session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED
    assert job.reason == JobReason.NO_IMAGERY


def test_rate_limited_tile_makes_the_job_partial(session, job, tmp_path):
    client = FakeClient(raise_on_features=MapillaryRateLimited("429"))
    run_job(session, job.id, client, FakeClassifier(), tmp_path)
    session.refresh(job)
    assert job.status == JobStatus.PARTIAL
    assert job.failed_tile_count == job.tile_count


def test_crop_failure_still_counts_the_sign_as_unknown(session, job, monkeypatch, tmp_path):
    from mithra_worker.cropper import CropError

    def boom(*a, **k):
        raise CropError("bad geometry")

    monkeypatch.setattr("mithra_worker.pipeline.crop_detection", boom)
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    sign = session.scalar(select(Sign))
    assert sign.sign_class == "unknown"
    assert sign.reason == SignReason.CROP_FAILED
    assert sign.needs_review is True


def test_feature_with_no_detection_is_counted_as_unknown(session, job, tmp_path):
    run_job(session, job.id, FakeClient(detections=[]), FakeClassifier(), tmp_path)
    sign = session.scalar(select(Sign))
    assert sign.sign_class == "unknown"
    assert sign.reason == SignReason.NO_DETECTION


def test_low_confidence_prediction_is_flagged_for_review(session, job, monkeypatch, tmp_path):
    class Unsure:
        version = "unsure-v1"

        def predict(self, image):
            return Prediction("street_name", 0.20, self.version)

    monkeypatch.setattr("mithra_worker.pipeline.crop_detection",
                        lambda *a, **k: Image.new("RGB", (64, 64)))
    run_job(session, job.id, FakeClient(), Unsure(), tmp_path, low_confidence_threshold=0.45)
    sign = session.scalar(select(Sign))
    assert sign.needs_review is True
    assert sign.sign_class == "street_name"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_worker.pipeline'`

- [ ] **Step 3: Implement the pipeline**

```python
"""Run one detection job end to end.

The only module that knows about tiling, Mapillary, cropping, classification,
and the database at the same time. Everything it calls is independently
testable; this file is the wiring.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.models import Job, JobReason, JobStatus, JobTile, Sign, SignReason
from mithra_worker.cropper import CropError, crop_detection
from mithra_worker.mapillary import MapillaryAuthError, MapillaryError
from mithra_worker.tiler import split_bbox

UNKNOWN = "unknown"


def _point(coordinates: list[float]) -> str:
    return f"SRID=4326;POINT({coordinates[0]} {coordinates[1]})"


def _classify_feature(feature, client, classifier, crop_dir: Path):
    """Return (sign_class, confidence, model_version, crop_path, image_id, reason)."""
    image_ids = [i["id"] for i in feature.get("images", {}).get("data", [])]
    for image_id in image_ids:
        try:
            detections = [
                d for d in client.get_detections(image_id)
                if d.get("value") == feature.get("object_value")
            ] or client.get_detections(image_id)
            if not detections:
                continue
            meta = client.get_image_meta(image_id)
            image_bytes = client.download(meta["thumb_2048_url"])
            crop = crop_detection(
                image_bytes, detections[0]["geometry"], meta["width"], meta["height"]
            )
        except CropError:
            return UNKNOWN, 0.0, "", None, image_id, SignReason.CROP_FAILED
        except MapillaryError:
            continue

        crop_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crop_dir / f"{feature['id']}.jpg"
        crop.save(crop_path, format="JPEG", quality=90)
        prediction = classifier.predict(crop)
        return (
            prediction.sign_class, prediction.confidence, prediction.model_version,
            str(crop_path), image_id, SignReason.OK,
        )

    return UNKNOWN, 0.0, "", None, (image_ids[0] if image_ids else None), SignReason.NO_DETECTION


def run_job(
    session: Session,
    job_id: uuid.UUID,
    client,
    classifier,
    crop_dir: Path,
    low_confidence_threshold: float = 0.45,
) -> None:
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")

    job.status = JobStatus.RUNNING
    tiles = split_bbox((job.bbox_west, job.bbox_south, job.bbox_east, job.bbox_north))
    job.tile_count = len(tiles)
    job.failed_tile_count = 0
    session.commit()

    seen: set[str] = set()
    job_crop_dir = Path(crop_dir) / str(job.id)

    for west, south, east, north in tiles:
        tile = JobTile(job_id=job.id, west=west, south=south, east=east, north=north)
        session.add(tile)
        try:
            features = client.get_sign_features((west, south, east, north))
        except MapillaryAuthError as exc:
            tile.status = JobStatus.FAILED
            tile.error = str(exc)[:500]
            job.status = JobStatus.FAILED
            job.reason = JobReason.AUTH_FAILED
            job.failed_tile_count += 1
            job.finished_at = datetime.now(UTC)
            session.commit()
            return
        except MapillaryError as exc:
            tile.status = JobStatus.FAILED
            tile.error = str(exc)[:500]
            job.failed_tile_count += 1
            session.commit()
            continue

        for feature in features:
            feature_id = feature["id"]
            if feature_id in seen:
                continue
            seen.add(feature_id)

            sign_class, confidence, version, crop_path, image_id, reason = _classify_feature(
                feature, client, classifier, job_crop_dir
            )
            session.add(Sign(
                job_id=job.id,
                mapillary_feature_id=feature_id,
                image_id=image_id,
                geom=_point(feature["geometry"]["coordinates"]),
                sign_class=sign_class,
                confidence=confidence,
                model_version=version or getattr(classifier, "version", "unknown"),
                mapillary_value=feature.get("object_value"),
                crop_path=crop_path,
                needs_review=(sign_class == UNKNOWN or confidence < low_confidence_threshold),
                reason=reason,
            ))

        tile.status = JobStatus.SUCCEEDED
        session.commit()

    if job.failed_tile_count:
        job.status = JobStatus.PARTIAL
    else:
        job.status = JobStatus.SUCCEEDED
        if not seen:
            job.reason = JobReason.NO_IMAGERY
    job.finished_at = datetime.now(UTC)
    session.commit()
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_pipeline.py -v`
Expected: 8 passed

- [ ] **Step 5: Add the RQ entrypoint**

Append to `pipeline.py`:

```python
def enqueue_job(job_id: str) -> None:
    """RQ task entrypoint. Builds its own dependencies so it can run in a worker process."""
    from mithra_api.config import get_settings
    from mithra_api.db import get_engine
    from mithra_ml.registry import get_classifier
    from mithra_worker.mapillary import MapillaryClient
    from sqlalchemy.orm import Session

    settings = get_settings()
    with Session(get_engine()) as session, MapillaryClient(
        token=settings.mapillary_token.get_secret_value(), proxy=settings.https_proxy
    ) as client:
        run_job(
            session, uuid.UUID(job_id), client, get_classifier(),
            Path(settings.crop_dir), settings.low_confidence_threshold,
        )
```

- [ ] **Step 6: Run the whole suite**

Run: `make test`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add services/worker/mithra_worker/pipeline.py tests/test_pipeline.py
git commit -m "feat: run detection jobs end to end

Failures degrade rather than erase: a rate-limited tile marks the job partial
with the tile recorded, an uncroppable sign is still counted as unknown and
flagged for review, and an empty bbox succeeds with a no_imagery reason
because absence of coverage is a valid answer."
```

---

### Task 9: Job and results API

**Files:**
- Create: `services/api/mithra_api/schemas.py`, `services/api/mithra_api/routes/jobs.py`, `services/api/mithra_api/routes/signs.py`, `services/api/mithra_api/main.py`
- Test: `tests/test_api_jobs.py`

**Interfaces:**
- Consumes: all ORM models, `enqueue_job`
- Produces: HTTP endpoints
  - `POST /api/jobs` body `{"bbox": [west, south, east, north]}` → `201 {"id", "status"}`
  - `GET /api/jobs/{id}` → `{"id","status","reason","tile_count","failed_tile_count","counts":{class: n},"total","failed_count"}`
  - `GET /api/jobs/{id}/signs?sign_class=&needs_review=` → `{"items":[{"id","sign_class","confidence","lon","lat","crop_url","needs_review","mapillary_value"}]}`

- [ ] **Step 1: Write the failing test**

`tests/test_api_jobs.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mithra_api.db import Base, get_session
from mithra_api.main import app
from mithra_api.models import Job, JobStatus, Sign

DB_URL = "postgresql+psycopg://bina:bina@localhost:5432/bina"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    enqueued = []
    monkeypatch.setattr("mithra_api.routes.jobs.enqueue", lambda job_id: enqueued.append(job_id))
    test_client = TestClient(app)
    test_client.enqueued = enqueued
    test_client.engine = engine
    yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_creating_a_job_returns_queued_and_enqueues_work(client):
    response = client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.64, 36.33]})
    assert response.status_code == 201
    assert response.json()["status"] == JobStatus.QUEUED
    assert len(client.enqueued) == 1


def test_inverted_bbox_is_rejected(client):
    response = client.post("/api/jobs", json={"bbox": [59.64, 36.29, 59.60, 36.33]})
    assert response.status_code == 422


def test_out_of_range_coordinates_are_rejected(client):
    response = client.post("/api/jobs", json={"bbox": [200.0, 36.29, 201.0, 36.33]})
    assert response.status_code == 422


def test_oversized_bbox_is_rejected(client):
    response = client.post("/api/jobs", json={"bbox": [58.0, 35.0, 61.0, 38.0]})
    assert response.status_code == 422


def test_status_reports_counts_per_class_and_failures(client):
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30,
                  status=JobStatus.SUCCEEDED, tile_count=4, failed_tile_count=0)
        session.add(job)
        session.commit()
        for i, (sign_class, reason) in enumerate([
            ("street_name", "ok"), ("street_name", "ok"),
            ("direction_guide", "ok"), ("unknown", "crop_failed"),
        ]):
            session.add(Sign(
                job_id=job.id, mapillary_feature_id=f"f{i}",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class=sign_class, confidence=0.8, model_version="v1", reason=reason,
            ))
        session.commit()
        job_id = str(job.id)

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["counts"]["street_name"] == 2
    assert body["counts"]["direction_guide"] == 1
    assert body["total"] == 4
    assert body["failed_count"] == 1


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000").status_code == 404


def test_signs_can_be_filtered_by_class(client):
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        for i, sign_class in enumerate(["street_name", "city_entry"]):
            session.add(Sign(
                job_id=job.id, mapillary_feature_id=f"f{i}",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class=sign_class, confidence=0.8, model_version="v1",
            ))
        session.commit()
        job_id = str(job.id)

    items = client.get(f"/api/jobs/{job_id}/signs?sign_class=city_entry").json()["items"]
    assert len(items) == 1
    assert items[0]["sign_class"] == "city_entry"


def test_signs_expose_coordinates(client):
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        session.add(Sign(
            job_id=job.id, mapillary_feature_id="f1",
            geom="SRID=4326;POINT(59.601 36.294)",
            sign_class="street_name", confidence=0.8, model_version="v1",
        ))
        session.commit()
        job_id = str(job.id)

    item = client.get(f"/api/jobs/{job_id}/signs").json()["items"][0]
    assert item["lon"] == pytest.approx(59.601)
    assert item["lat"] == pytest.approx(36.294)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_api_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mithra_api.main'`

- [ ] **Step 3: Implement the schemas**

`services/api/mithra_api/schemas.py`:

```python
import uuid

from pydantic import BaseModel, Field, model_validator

MAX_JOB_SIDE_DEGREES = 0.5  # ~55 km; a whole-city box, not a whole-country one


class JobCreate(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _check(self) -> "JobCreate":
        west, south, east, north = self.bbox
        if not (-180 <= west < east <= 180):
            raise ValueError("longitudes must satisfy -180 <= west < east <= 180")
        if not (-90 <= south < north <= 90):
            raise ValueError("latitudes must satisfy -90 <= south < north <= 90")
        if (east - west) > MAX_JOB_SIDE_DEGREES or (north - south) > MAX_JOB_SIDE_DEGREES:
            raise ValueError(f"bbox side must not exceed {MAX_JOB_SIDE_DEGREES} degrees")
        return self


class JobCreated(BaseModel):
    id: uuid.UUID
    status: str


class JobStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    reason: str | None
    tile_count: int
    failed_tile_count: int
    counts: dict[str, int]
    total: int
    failed_count: int


class SignOut(BaseModel):
    id: uuid.UUID
    sign_class: str
    confidence: float
    lon: float
    lat: float
    crop_url: str | None
    needs_review: bool
    mapillary_value: str | None


class SignList(BaseModel):
    items: list[SignOut]
```

- [ ] **Step 4: Implement the jobs route**

`services/api/mithra_api/routes/jobs.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mithra_api.db import get_session
from mithra_api.models import Job, Sign, SignReason
from mithra_api.schemas import JobCreate, JobCreated, JobStatusOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def enqueue(job_id: str) -> None:
    """Indirection so tests can substitute a recorder for the queue."""
    from redis import Redis
    from rq import Queue

    from mithra_api.config import get_settings

    Queue(connection=Redis.from_url(get_settings().redis_url)).enqueue(
        "mithra_worker.pipeline.enqueue_job", job_id
    )


@router.post("", response_model=JobCreated, status_code=201)
def create_job(payload: JobCreate, session: Session = Depends(get_session)) -> JobCreated:
    west, south, east, north = payload.bbox
    job = Job(bbox_west=west, bbox_south=south, bbox_east=east, bbox_north=north)
    session.add(job)
    session.commit()
    enqueue(str(job.id))
    return JobCreated(id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusOut)
def get_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> JobStatusOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    rows = session.execute(
        select(Sign.sign_class, func.count()).where(Sign.job_id == job.id).group_by(Sign.sign_class)
    ).all()
    counts = {sign_class: n for sign_class, n in rows}
    failed_count = session.scalar(
        select(func.count()).select_from(Sign).where(
            Sign.job_id == job.id, Sign.reason != SignReason.OK
        )
    ) or 0

    return JobStatusOut(
        id=job.id, status=job.status, reason=job.reason,
        tile_count=job.tile_count, failed_tile_count=job.failed_tile_count,
        counts=counts, total=sum(counts.values()), failed_count=failed_count,
    )
```

- [ ] **Step 5: Implement the signs route**

`services/api/mithra_api/routes/signs.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.db import get_session
from mithra_api.models import Job, Sign
from mithra_api.schemas import SignList, SignOut

router = APIRouter(prefix="/api/jobs", tags=["signs"])


@router.get("/{job_id}/signs", response_model=SignList)
def list_signs(
    job_id: uuid.UUID,
    sign_class: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=1000, le=5000),
    session: Session = Depends(get_session),
) -> SignList:
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    statement = select(
        Sign.id, Sign.sign_class, Sign.confidence, ST_X(Sign.geom), ST_Y(Sign.geom),
        Sign.crop_path, Sign.needs_review, Sign.mapillary_value,
    ).where(Sign.job_id == job_id)
    if sign_class is not None:
        statement = statement.where(Sign.sign_class == sign_class)
    if needs_review is not None:
        statement = statement.where(Sign.needs_review.is_(needs_review))

    items = [
        SignOut(
            id=row[0], sign_class=row[1], confidence=row[2], lon=row[3], lat=row[4],
            crop_url=f"/api/crops/{row[0]}" if row[5] else None,
            needs_review=row[6], mapillary_value=row[7],
        )
        for row in session.execute(statement.limit(limit)).all()
    ]
    return SignList(items=items)
```

- [ ] **Step 6: Implement `main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mithra_api.routes import jobs, signs

app = FastAPI(title="bina", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(signs.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

Also create empty `services/api/mithra_api/routes/__init__.py`.

- [ ] **Step 7: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_api_jobs.py -v`
Expected: 8 passed

- [ ] **Step 8: Commit**

```bash
git add services/api/mithra_api tests/test_api_jobs.py
git commit -m "feat: add job creation and results endpoints

Job status returns failed_count alongside the per-class counts so a caller can
never read a total without also seeing how many signs failed to classify."
```

---

### Task 10: Crop serving, export, and labeling API

**Files:**
- Create: `services/api/mithra_api/routes/export.py`, `services/api/mithra_api/routes/labels.py`, `services/api/mithra_api/routes/crops.py`
- Modify: `services/api/mithra_api/main.py`
- Test: `tests/test_api_export.py`, `tests/test_api_labels.py`

**Interfaces:**
- Consumes: ORM models, `SIGN_CLASSES` and `UNKNOWN` from `mithra_ml`
- Produces:
  - `GET /api/crops/{sign_id}` → the crop JPEG
  - `GET /api/jobs/{id}/export.csv` → CSV with header `id,sign_class,confidence,lon,lat,mapillary_value,needs_review`
  - `GET /api/jobs/{id}/export.geojson` → FeatureCollection
  - `GET /api/labels/queue?limit=` → `{"items":[SignOut]}` ordered by ascending confidence, `needs_review` first
  - `POST /api/labels` body `{"sign_id","sign_class"}` → `201`; writes a `Label`, updates the sign's class, clears `needs_review`

- [ ] **Step 1: Write the failing export test**

`tests/test_api_export.py`:

```python
import csv
import io

import pytest
from sqlalchemy.orm import Session

from mithra_api.models import Job, Sign
from tests.test_api_jobs import client  # noqa: F401 - reuse the app fixture


@pytest.fixture
def job_with_signs(client):  # noqa: F811
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        for i, sign_class in enumerate(["street_name", "city_entry"]):
            session.add(Sign(
                job_id=job.id, mapillary_feature_id=f"f{i}",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class=sign_class, confidence=0.8, model_version="v1",
                mapillary_value="information--parking--g1",
            ))
        session.commit()
        return str(job.id)


def test_csv_export_has_a_header_and_one_row_per_sign(client, job_with_signs):  # noqa: F811
    response = client.get(f"/api/jobs/{job_with_signs}/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["id", "sign_class", "confidence", "lon", "lat", "mapillary_value", "needs_review"]
    assert len(rows) == 3


def test_csv_export_sets_a_download_filename(client, job_with_signs):  # noqa: F811
    response = client.get(f"/api/jobs/{job_with_signs}/export.csv")
    assert "attachment" in response.headers["content-disposition"]


def test_geojson_export_is_a_valid_feature_collection(client, job_with_signs):  # noqa: F811
    body = client.get(f"/api/jobs/{job_with_signs}/export.geojson").json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 2
    feature = body["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == pytest.approx([59.601, 36.294])
    assert feature["properties"]["sign_class"] in {"street_name", "city_entry"}


def test_export_of_an_unknown_job_returns_404(client):  # noqa: F811
    assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000/export.csv").status_code == 404
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_api_export.py -v`
Expected: FAIL — `/export.csv` returns 404 because the route does not exist

- [ ] **Step 3: Implement the export route**

`services/api/mithra_api/routes/export.py`:

```python
import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.db import get_session
from mithra_api.models import Job, Sign

router = APIRouter(prefix="/api/jobs", tags=["export"])

COLUMNS = ["id", "sign_class", "confidence", "lon", "lat", "mapillary_value", "needs_review"]


def _rows(session: Session, job_id: uuid.UUID):
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return session.execute(
        select(
            Sign.id, Sign.sign_class, Sign.confidence, ST_X(Sign.geom), ST_Y(Sign.geom),
            Sign.mapillary_value, Sign.needs_review,
        ).where(Sign.job_id == job_id)
    ).all()


@router.get("/{job_id}/export.csv")
def export_csv(job_id: uuid.UUID, session: Session = Depends(get_session)) -> StreamingResponse:
    rows = _rows(session, job_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([str(row[0]), row[1], f"{row[2]:.4f}", row[3], row[4], row[5] or "", row[6]])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="bina-{job_id}.csv"'},
    )


@router.get("/{job_id}/export.geojson")
def export_geojson(job_id: uuid.UUID, session: Session = Depends(get_session)) -> JSONResponse:
    rows = _rows(session, job_id)
    return JSONResponse({
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row[3], row[4]]},
                "properties": {
                    "id": str(row[0]), "sign_class": row[1], "confidence": row[2],
                    "mapillary_value": row[5], "needs_review": row[6],
                },
            }
            for row in rows
        ],
    }, headers={"Content-Disposition": f'attachment; filename="bina-{job_id}.geojson"'})
```

- [ ] **Step 4: Run the export tests and make sure they pass**

Run: `cd services/api && pytest ../../tests/test_api_export.py -v`
Expected: 4 passed (register the router in `main.py` first: `from mithra_api.routes import export` and `app.include_router(export.router)`)

- [ ] **Step 5: Write the failing labels test**

`tests/test_api_labels.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.models import Job, Label, Sign
from tests.test_api_jobs import client  # noqa: F401


@pytest.fixture
def signs(client):  # noqa: F811
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        rows = [
            ("unknown", 0.10, True),
            ("street_name", 0.35, True),
            ("city_entry", 0.95, False),
        ]
        ids = []
        for i, (sign_class, confidence, review) in enumerate(rows):
            sign = Sign(
                job_id=job.id, mapillary_feature_id=f"f{i}",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class=sign_class, confidence=confidence,
                model_version="v1", needs_review=review,
            )
            session.add(sign)
            session.commit()
            ids.append(str(sign.id))
        return ids


def test_queue_returns_review_items_lowest_confidence_first(client, signs):  # noqa: F811
    items = client.get("/api/labels/queue").json()["items"]
    assert [i["id"] for i in items] == [signs[0], signs[1]]


def test_queue_respects_the_limit(client, signs):  # noqa: F811
    assert len(client.get("/api/labels/queue?limit=1").json()["items"]) == 1


def test_posting_a_label_updates_the_sign_and_clears_review(client, signs):  # noqa: F811
    response = client.post("/api/labels", json={"sign_id": signs[0], "sign_class": "city_entry"})
    assert response.status_code == 201
    with Session(client.engine) as session:
        sign = session.get(Sign, __import__("uuid").UUID(signs[0]))
        assert sign.sign_class == "city_entry"
        assert sign.needs_review is False


def test_posting_a_label_records_ground_truth(client, signs):  # noqa: F811
    client.post("/api/labels", json={"sign_id": signs[0], "sign_class": "city_entry"})
    with Session(client.engine) as session:
        label = session.scalar(select(Label))
        assert label.sign_class == "city_entry"


def test_an_invalid_class_is_rejected(client, signs):  # noqa: F811
    response = client.post("/api/labels", json={"sign_id": signs[0], "sign_class": "not_a_class"})
    assert response.status_code == 422


def test_labeling_an_unknown_sign_returns_404(client):  # noqa: F811
    response = client.post("/api/labels", json={
        "sign_id": "00000000-0000-0000-0000-000000000000", "sign_class": "city_entry"})
    assert response.status_code == 404
```

- [ ] **Step 6: Run it to make sure it fails**

Run: `cd services/api && pytest ../../tests/test_api_labels.py -v`
Expected: FAIL — the labels routes do not exist

- [ ] **Step 7: Implement the labels and crops routes**

`services/api/mithra_api/routes/labels.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.db import get_session
from mithra_api.models import Label, Sign
from mithra_api.schemas import SignList, SignOut
from mithra_ml import ALL_CLASSES

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LabelCreate(BaseModel):
    sign_id: uuid.UUID
    sign_class: str

    @field_validator("sign_class")
    @classmethod
    def _known_class(cls, v: str) -> str:
        if v not in ALL_CLASSES:
            raise ValueError(f"sign_class must be one of {ALL_CLASSES}")
        return v


@router.get("/queue", response_model=SignList)
def queue(limit: int = Query(default=50, le=500), session: Session = Depends(get_session)) -> SignList:
    rows = session.execute(
        select(
            Sign.id, Sign.sign_class, Sign.confidence, ST_X(Sign.geom), ST_Y(Sign.geom),
            Sign.crop_path, Sign.needs_review, Sign.mapillary_value,
        )
        .where(Sign.needs_review.is_(True))
        .order_by(Sign.confidence.asc())
        .limit(limit)
    ).all()
    return SignList(items=[
        SignOut(
            id=r[0], sign_class=r[1], confidence=r[2], lon=r[3], lat=r[4],
            crop_url=f"/api/crops/{r[0]}" if r[5] else None,
            needs_review=r[6], mapillary_value=r[7],
        )
        for r in rows
    ])


@router.post("", status_code=201)
def create_label(payload: LabelCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    sign = session.get(Sign, payload.sign_id)
    if sign is None:
        raise HTTPException(status_code=404, detail="sign not found")

    session.add(Label(sign_id=sign.id, sign_class=payload.sign_class))
    sign.sign_class = payload.sign_class
    sign.needs_review = False
    session.commit()
    return {"status": "ok"}
```

`services/api/mithra_api/routes/crops.py`:

```python
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mithra_api.db import get_session
from mithra_api.models import Sign

router = APIRouter(prefix="/api/crops", tags=["crops"])


@router.get("/{sign_id}")
def get_crop(sign_id: uuid.UUID, session: Session = Depends(get_session)) -> FileResponse:
    sign = session.get(Sign, sign_id)
    if sign is None or not sign.crop_path or not Path(sign.crop_path).exists():
        raise HTTPException(status_code=404, detail="crop not found")
    return FileResponse(sign.crop_path, media_type="image/jpeg")
```

Register both in `main.py` alongside the existing routers.

- [ ] **Step 8: Run the tests and make sure they pass**

Run: `cd services/api && pytest ../../tests -v`
Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
git add services/api/mithra_api tests/test_api_export.py tests/test_api_labels.py
git commit -m "feat: add crop serving, CSV/GeoJSON export, and labeling endpoints

Labels are stored as their own rows rather than only overwriting the sign's
class, so the corrections remain available as training data after the sign
row is reclassified by a later model."
```

---

### Task 11: Next.js shell, i18n, and RTL

**Files:**
- Create: `apps/web/package.json`, `apps/web/next.config.ts`, `apps/web/src/i18n.ts`, `apps/web/src/middleware.ts`, `apps/web/messages/fa.json`, `apps/web/messages/en.json`, `apps/web/src/app/[locale]/layout.tsx`, `apps/web/src/lib/api.ts`
- Test: `apps/web/src/lib/api.test.ts`

**Interfaces:**
- Consumes: the API endpoints from Tasks 9 and 10
- Produces: `createJob(bbox)`, `getJob(id)`, `listSigns(id, filters)`, `getLabelQueue(limit)`, `postLabel(signId, signClass)`, plus the TypeScript types `Bbox`, `JobStatus`, `Sign`

- [ ] **Step 1: Scaffold the app**

```bash
cd apps && npx create-next-app@latest web --typescript --app --tailwind --eslint --src-dir --no-import-alias
cd web && npm install next-intl maplibre-gl && npm install -D vitest
```

- [ ] **Step 2: Write the translation files**

`apps/web/messages/fa.json`:

```json
{
  "app": { "name": "بینا", "tagline": "شمارش و دسته‌بندی تابلوهای شهری" },
  "map": { "drawBox": "کادر بکشید", "clear": "پاک کردن", "submit": "شروع تحلیل" },
  "job": {
    "status": "وضعیت",
    "queued": "در صف",
    "running": "در حال اجرا",
    "succeeded": "کامل شد",
    "partial": "ناقص",
    "failed": "ناموفق",
    "total": "مجموع تابلوها",
    "failedCount": "طبقه‌بندی‌نشده",
    "tiles": "کاشی‌ها",
    "noImagery": "تصویری در این محدوده موجود نیست"
  },
  "classes": {
    "direction_guide": "تابلو مسیرنما",
    "street_name": "تابلو نام معبر",
    "city_entry": "تابلو ورودی شهر",
    "informational": "تابلو اطلاعاتی",
    "unknown": "نامشخص"
  },
  "table": { "class": "نوع", "confidence": "اطمینان", "location": "موقعیت", "review": "نیازمند بازبینی" },
  "export": { "csv": "خروجی CSV", "geojson": "خروجی GeoJSON" },
  "label": { "title": "برچسب‌گذاری", "question": "این تابلو از چه نوعی است؟", "empty": "چیزی برای بازبینی نیست", "skip": "رد کردن" }
}
```

`apps/web/messages/en.json`:

```json
{
  "app": { "name": "Bina", "tagline": "Count and classify urban signs" },
  "map": { "drawBox": "Draw a box", "clear": "Clear", "submit": "Run analysis" },
  "job": {
    "status": "Status",
    "queued": "Queued",
    "running": "Running",
    "succeeded": "Complete",
    "partial": "Partial",
    "failed": "Failed",
    "total": "Total signs",
    "failedCount": "Unclassified",
    "tiles": "Tiles",
    "noImagery": "No imagery available in this area"
  },
  "classes": {
    "direction_guide": "Direction / guide sign",
    "street_name": "Street name sign",
    "city_entry": "City entry sign",
    "informational": "Informational sign",
    "unknown": "Unknown"
  },
  "table": { "class": "Type", "confidence": "Confidence", "location": "Location", "review": "Needs review" },
  "export": { "csv": "Export CSV", "geojson": "Export GeoJSON" },
  "label": { "title": "Labeling", "question": "What type of sign is this?", "empty": "Nothing to review", "skip": "Skip" }
}
```

- [ ] **Step 3: Write the failing API client test**

`apps/web/src/lib/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { createJob, getJob, listSigns, postLabel } from "./api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(body: unknown, ok = true, status = 200) {
  const spy = vi.fn().mockResolvedValue({ ok, status, json: async () => body });
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("api client", () => {
  it("posts the bbox as an array", async () => {
    const spy = mockFetch({ id: "abc", status: "queued" });
    await createJob([59.6, 36.29, 59.64, 36.33]);
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.bbox).toEqual([59.6, 36.29, 59.64, 36.33]);
  });

  it("returns the created job id", async () => {
    mockFetch({ id: "abc", status: "queued" });
    expect((await createJob([59.6, 36.29, 59.64, 36.33])).id).toBe("abc");
  });

  it("reads job counts", async () => {
    mockFetch({ id: "abc", status: "succeeded", counts: { street_name: 3 }, total: 3, failed_count: 0 });
    expect((await getJob("abc")).counts.street_name).toBe(3);
  });

  it("passes the class filter as a query param", async () => {
    const spy = mockFetch({ items: [] });
    await listSigns("abc", { signClass: "city_entry" });
    expect(String(spy.mock.calls[0][0])).toContain("sign_class=city_entry");
  });

  it("throws on a non-ok response", async () => {
    mockFetch({ detail: "job not found" }, false, 404);
    await expect(getJob("missing")).rejects.toThrow();
  });

  it("posts labels with snake_case keys the API expects", async () => {
    const spy = mockFetch({ status: "ok" });
    await postLabel("sign-1", "city_entry");
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body).toEqual({ sign_id: "sign-1", sign_class: "city_entry" });
  });
});
```

- [ ] **Step 4: Run it to make sure it fails**

Run: `cd apps/web && npx vitest run src/lib/api.test.ts`
Expected: FAIL — cannot resolve `./api`

- [ ] **Step 5: Implement the API client**

`apps/web/src/lib/api.ts`:

```ts
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

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
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
  if (filters.needsReview !== undefined) params.set("needs_review", String(filters.needsReview));
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
  return `${BASE}/api/jobs/${id}/export.${format}`;
}
```

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `cd apps/web && npx vitest run src/lib/api.test.ts`
Expected: 6 passed

- [ ] **Step 7: Wire up i18n and RTL**

`apps/web/src/i18n.ts`:

```ts
import { getRequestConfig } from "next-intl/server";
import { notFound } from "next/navigation";

export const locales = ["fa", "en"] as const;
export const defaultLocale = "fa";

export default getRequestConfig(async ({ requestLocale }) => {
  const locale = (await requestLocale) ?? defaultLocale;
  if (!locales.includes(locale as (typeof locales)[number])) notFound();
  return { locale, messages: (await import(`../messages/${locale}.json`)).default };
});
```

`apps/web/src/middleware.ts`:

```ts
import createMiddleware from "next-intl/middleware";
import { defaultLocale, locales } from "./i18n";

export default createMiddleware({ locales, defaultLocale, localePrefix: "always" });

export const config = { matcher: ["/", "/(fa|en)/:path*"] };
```

`apps/web/src/app/[locale]/layout.tsx`:

```tsx
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import "maplibre-gl/dist/maplibre-gl.css";
import "../globals.css";

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const messages = await getMessages();
  return (
    <html lang={locale} dir={locale === "fa" ? "rtl" : "ltr"}>
      <body>
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
```

Add to `next.config.ts`:

```ts
import createNextIntlPlugin from "next-intl/plugin";
export default createNextIntlPlugin("./src/i18n.ts")({});
```

- [ ] **Step 8: Verify both locales render with the correct direction**

Run: `cd apps/web && npm run dev`
Then check `http://localhost:3000/fa` renders `dir="rtl"` and `http://localhost:3000/en` renders `dir="ltr"` in the page source.

- [ ] **Step 9: Commit**

```bash
git add apps/web
git commit -m "feat: scaffold Next.js app with Persian-first i18n and RTL

Persian is the default locale and the html dir attribute follows it, so the
Persian experience is the designed one rather than an English layout with
translated strings."
```

---

### Task 12: Map, bbox drawing, and job submission

**Files:**
- Create: `apps/web/src/components/BboxMap.tsx`, `apps/web/src/app/[locale]/page.tsx`
- Test: `apps/web/src/components/bbox.test.ts`, `apps/web/src/lib/bbox.ts`

**Interfaces:**
- Consumes: `createJob`, `Bbox` from `lib/api`
- Produces: `BboxMap` component with props `{ value: Bbox | null; onChange: (bbox: Bbox | null) => void }`, and `normalizeBbox(a: [number, number], b: [number, number]) -> Bbox` in `lib/bbox.ts`

- [ ] **Step 1: Write the failing bbox helper test**

`apps/web/src/components/bbox.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { MASHHAD_CENTER, normalizeBbox } from "../lib/bbox";

describe("normalizeBbox", () => {
  it("orders corners west,south,east,north regardless of drag direction", () => {
    const topRightToBottomLeft = normalizeBbox([59.64, 36.33], [59.6, 36.29]);
    const bottomLeftToTopRight = normalizeBbox([59.6, 36.29], [59.64, 36.33]);
    expect(topRightToBottomLeft).toEqual(bottomLeftToTopRight);
  });

  it("produces west < east and south < north", () => {
    const [w, s, e, n] = normalizeBbox([59.64, 36.29], [59.6, 36.33]);
    expect(w).toBeLessThan(e);
    expect(s).toBeLessThan(n);
  });

  it("centers on Mashhad", () => {
    expect(MASHHAD_CENTER[0]).toBeCloseTo(59.606, 2);
    expect(MASHHAD_CENTER[1]).toBeCloseTo(36.297, 2);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd apps/web && npx vitest run src/components/bbox.test.ts`
Expected: FAIL — cannot resolve `../lib/bbox`

- [ ] **Step 3: Implement the helper**

`apps/web/src/lib/bbox.ts`:

```ts
import type { Bbox } from "./api";

export const MASHHAD_CENTER: [number, number] = [59.6062, 36.2972];

export function normalizeBbox(a: [number, number], b: [number, number]): Bbox {
  return [
    Math.min(a[0], b[0]),
    Math.min(a[1], b[1]),
    Math.max(a[0], b[0]),
    Math.max(a[1], b[1]),
  ];
}

export function bboxToPolygon(bbox: Bbox) {
  const [w, s, e, n] = bbox;
  return {
    type: "Feature" as const,
    properties: {},
    geometry: {
      type: "Polygon" as const,
      coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    },
  };
}
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd apps/web && npx vitest run src/components/bbox.test.ts`
Expected: 3 passed

- [ ] **Step 5: Implement the map component**

`apps/web/src/components/BboxMap.tsx`:

```tsx
"use client";

import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import type { Bbox } from "../lib/api";
import { MASHHAD_CENTER, bboxToPolygon, normalizeBbox } from "../lib/bbox";

const STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

export default function BboxMap({
  value,
  onChange,
}: {
  value: Bbox | null;
  onChange: (bbox: Bbox | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const anchor = useRef<[number, number] | null>(null);

  useEffect(() => {
    if (!container.current || map.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: MASHHAD_CENTER,
      zoom: 13,
    });
    map.current = instance;

    instance.on("load", () => {
      instance.addSource("bbox", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      instance.addLayer({
        id: "bbox-fill", type: "fill", source: "bbox",
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.15 },
      });
      instance.addLayer({
        id: "bbox-line", type: "line", source: "bbox",
        paint: { "line-color": "#2563eb", "line-width": 2 },
      });
    });

    // Shift-drag draws the box; plain drag still pans the map.
    instance.on("mousedown", (event) => {
      if (!event.originalEvent.shiftKey) return;
      instance.dragPan.disable();
      anchor.current = [event.lngLat.lng, event.lngLat.lat];
    });
    instance.on("mousemove", (event) => {
      if (!anchor.current) return;
      onChange(normalizeBbox(anchor.current, [event.lngLat.lng, event.lngLat.lat]));
    });
    instance.on("mouseup", () => {
      anchor.current = null;
      instance.dragPan.enable();
    });

    return () => {
      instance.remove();
      map.current = null;
    };
  }, [onChange]);

  useEffect(() => {
    const source = map.current?.getSource("bbox") as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(
      value
        ? { type: "FeatureCollection", features: [bboxToPolygon(value)] }
        : { type: "FeatureCollection", features: [] },
    );
  }, [value]);

  return <div ref={container} className="h-[70vh] w-full rounded-lg" />;
}
```

- [ ] **Step 6: Implement the submission page**

`apps/web/src/app/[locale]/page.tsx`:

```tsx
"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import BboxMap from "../../components/BboxMap";
import { createJob, type Bbox } from "../../lib/api";

export default function HomePage() {
  const t = useTranslations();
  const router = useRouter();
  const [bbox, setBbox] = useState<Bbox | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!bbox) return;
    setBusy(true);
    setError(null);
    try {
      const job = await createJob(bbox);
      router.push(`jobs/${job.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-bold">{t("app.name")}</h1>
      <p className="mb-4 text-sm opacity-70">{t("app.tagline")}</p>

      <BboxMap value={bbox} onChange={setBbox} />

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={submit}
          disabled={!bbox || busy}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-40"
        >
          {t("map.submit")}
        </button>
        <button onClick={() => setBbox(null)} className="rounded border px-4 py-2">
          {t("map.clear")}
        </button>
        {!bbox && <span className="text-sm opacity-60">{t("map.drawBox")}</span>}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </main>
  );
}
```

- [ ] **Step 7: Verify by hand**

Run: `cd apps/web && npm run dev`, open `http://localhost:3000/fa`, shift-drag on the map. The blue rectangle should appear and the submit button should enable.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src
git commit -m "feat: add map bbox drawing and job submission

Shift-drag draws the box so plain drag keeps panning, which matters because
selecting a survey area usually takes several pan-and-adjust rounds."
```

---

### Task 13: Results view

**Files:**
- Create: `apps/web/src/components/CountsPanel.tsx`, `apps/web/src/components/SignTable.tsx`, `apps/web/src/app/[locale]/jobs/[id]/page.tsx`
- Test: `apps/web/src/components/counts.test.ts`, `apps/web/src/lib/counts.ts`

**Interfaces:**
- Consumes: `getJob`, `listSigns`, `exportUrl`, types from `lib/api`
- Produces: `orderedCounts(counts: Partial<Record<SignClass, number>>) -> Array<{ signClass: SignClass; count: number }>` in `lib/counts.ts`

- [ ] **Step 1: Write the failing test**

`apps/web/src/components/counts.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { isTerminal, orderedCounts } from "../lib/counts";

describe("orderedCounts", () => {
  it("lists every known class even when the count is zero", () => {
    const rows = orderedCounts({ street_name: 3 });
    expect(rows.map((r) => r.signClass)).toContain("city_entry");
    expect(rows.find((r) => r.signClass === "city_entry")?.count).toBe(0);
  });

  it("keeps the four real classes ahead of unknown", () => {
    const rows = orderedCounts({ unknown: 9, street_name: 1 });
    expect(rows[rows.length - 1].signClass).toBe("unknown");
  });

  it("includes unknown when it is present", () => {
    expect(orderedCounts({ unknown: 2 }).find((r) => r.signClass === "unknown")?.count).toBe(2);
  });
});

describe("isTerminal", () => {
  it("treats succeeded, partial, and failed as terminal", () => {
    expect(isTerminal("succeeded")).toBe(true);
    expect(isTerminal("partial")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
  });

  it("treats queued and running as non-terminal", () => {
    expect(isTerminal("queued")).toBe(false);
    expect(isTerminal("running")).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd apps/web && npx vitest run src/components/counts.test.ts`
Expected: FAIL — cannot resolve `../lib/counts`

- [ ] **Step 3: Implement the helper**

`apps/web/src/lib/counts.ts`:

```ts
import { SIGN_CLASSES, type JobStatus, type SignClass } from "./api";

const DISPLAY_ORDER: SignClass[] = [...SIGN_CLASSES, "unknown"];

export function orderedCounts(counts: Partial<Record<SignClass, number>>) {
  return DISPLAY_ORDER.map((signClass) => ({ signClass, count: counts[signClass] ?? 0 }));
}

export function isTerminal(status: JobStatus["status"]) {
  return status === "succeeded" || status === "partial" || status === "failed";
}
```

Every class always renders, including zeros — a missing row reads as "not measured", while a zero reads as "measured, none found", and those are different answers for a survey.

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd apps/web && npx vitest run src/components/counts.test.ts`
Expected: 5 passed

- [ ] **Step 5: Implement the counts panel**

`apps/web/src/components/CountsPanel.tsx`:

```tsx
"use client";

import { useTranslations } from "next-intl";
import type { JobStatus } from "../lib/api";
import { orderedCounts } from "../lib/counts";

export default function CountsPanel({ job }: { job: JobStatus }) {
  const t = useTranslations();
  return (
    <section>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {orderedCounts(job.counts).map(({ signClass, count }) => (
          <div key={signClass} className="rounded-lg border p-3">
            <div className="text-2xl font-bold">{count.toLocaleString()}</div>
            <div className="text-xs opacity-70">{t(`classes.${signClass}`)}</div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-sm opacity-70">
        {t("job.total")}: {job.total.toLocaleString()} · {t("job.failedCount")}:{" "}
        {job.failed_count.toLocaleString()} · {t("job.tiles")}:{" "}
        {job.tile_count - job.failed_tile_count}/{job.tile_count}
      </p>
      {job.reason === "no_imagery" && (
        <p className="mt-2 rounded bg-amber-50 p-3 text-sm">{t("job.noImagery")}</p>
      )}
    </section>
  );
}
```

The failed count sits directly beside the total, on purpose — the spec requires that no count is ever readable without its failure context.

- [ ] **Step 6: Implement the table**

`apps/web/src/components/SignTable.tsx`:

```tsx
"use client";

import { useTranslations } from "next-intl";
import type { Sign } from "../lib/api";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function SignTable({ signs }: { signs: Sign[] }) {
  const t = useTranslations();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-start">
            <th className="p-2"> </th>
            <th className="p-2 text-start">{t("table.class")}</th>
            <th className="p-2 text-start">{t("table.confidence")}</th>
            <th className="p-2 text-start">{t("table.location")}</th>
            <th className="p-2 text-start">{t("table.review")}</th>
          </tr>
        </thead>
        <tbody>
          {signs.map((sign) => (
            <tr key={sign.id} className="border-b">
              <td className="p-2">
                {sign.crop_url && (
                  <img src={`${API}${sign.crop_url}`} alt="" className="h-10 w-10 rounded object-cover" />
                )}
              </td>
              <td className="p-2">{t(`classes.${sign.sign_class}`)}</td>
              <td className="p-2">{(sign.confidence * 100).toFixed(0)}%</td>
              <td className="p-2 tabular-nums">
                {sign.lat.toFixed(5)}, {sign.lon.toFixed(5)}
              </td>
              <td className="p-2">{sign.needs_review ? "●" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 7: Implement the results page with polling**

`apps/web/src/app/[locale]/jobs/[id]/page.tsx`:

```tsx
"use client";

import { useTranslations } from "next-intl";
import { use, useEffect, useState } from "react";
import CountsPanel from "../../../../components/CountsPanel";
import SignTable from "../../../../components/SignTable";
import { exportUrl, getJob, listSigns, type JobStatus, type Sign } from "../../../../lib/api";
import { isTerminal } from "../../../../lib/counts";

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations();
  const [job, setJob] = useState<JobStatus | null>(null);
  const [signs, setSigns] = useState<Sign[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const next = await getJob(id);
        if (cancelled) return;
        setJob(next);
        if (isTerminal(next.status)) {
          setSigns((await listSigns(id)).items);
          return;
        }
        setTimeout(poll, 2000);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <main className="p-6 text-red-600">{error}</main>;
  if (!job) return <main className="p-6">{t("job.queued")}</main>;

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-bold">{t("app.name")}</h1>
        <p className="text-sm opacity-70">
          {t("job.status")}: {t(`job.${job.status}`)}
        </p>
      </header>

      <CountsPanel job={job} />

      {isTerminal(job.status) && (
        <div className="flex gap-3">
          <a className="rounded border px-3 py-2 text-sm" href={exportUrl(id, "csv")}>
            {t("export.csv")}
          </a>
          <a className="rounded border px-3 py-2 text-sm" href={exportUrl(id, "geojson")}>
            {t("export.geojson")}
          </a>
        </div>
      )}

      <SignTable signs={signs} />
    </main>
  );
}
```

- [ ] **Step 8: Run the full frontend test suite**

Run: `cd apps/web && npx vitest run`
Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
git add apps/web/src
git commit -m "feat: add job results view with counts, table, and export

Every class renders even at zero, and the unclassified count sits beside the
total. A missing row would read as 'not measured' when the truth is
'measured, none found' — for a survey those are different answers."
```

---

### Task 14: Labeling UI

**Files:**
- Create: `apps/web/src/app/[locale]/label/page.tsx`
- Test: `apps/web/src/app/label.test.ts`, `apps/web/src/lib/labelQueue.ts`

**Interfaces:**
- Consumes: `getLabelQueue`, `postLabel`, `SIGN_CLASSES`
- Produces: `advance<T>(items: T[], index: number) -> number` in `lib/labelQueue.ts`

- [ ] **Step 1: Write the failing test**

`apps/web/src/app/label.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { advance, needsRefill } from "../lib/labelQueue";

describe("advance", () => {
  it("moves to the next item", () => {
    expect(advance([1, 2, 3], 0)).toBe(1);
  });

  it("stops at the end rather than wrapping", () => {
    expect(advance([1, 2, 3], 2)).toBe(3);
  });

  it("handles an empty queue", () => {
    expect(advance([], 0)).toBe(0);
  });
});

describe("needsRefill", () => {
  it("asks for more when the queue is exhausted", () => {
    expect(needsRefill([1, 2], 2)).toBe(true);
  });

  it("does not ask while items remain", () => {
    expect(needsRefill([1, 2], 0)).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd apps/web && npx vitest run src/app/label.test.ts`
Expected: FAIL — cannot resolve `../lib/labelQueue`

- [ ] **Step 3: Implement the helper**

`apps/web/src/lib/labelQueue.ts`:

```ts
export function advance<T>(items: T[], index: number): number {
  return Math.min(index + 1, items.length);
}

export function needsRefill<T>(items: T[], index: number): boolean {
  return index >= items.length;
}
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd apps/web && npx vitest run src/app/label.test.ts`
Expected: 5 passed

- [ ] **Step 5: Implement the labeling page**

`apps/web/src/app/[locale]/label/page.tsx`:

```tsx
"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { SIGN_CLASSES, getLabelQueue, postLabel, type Sign } from "../../../lib/api";
import { advance, needsRefill } from "../../../lib/labelQueue";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LabelPage() {
  const t = useTranslations();
  const [items, setItems] = useState<Sign[]>([]);
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);

  const refill = useCallback(async () => {
    const { items: next } = await getLabelQueue(50);
    setItems(next);
    setIndex(0);
  }, []);

  useEffect(() => {
    refill();
  }, [refill]);

  useEffect(() => {
    if (items.length > 0 && needsRefill(items, index)) refill();
  }, [items, index, refill, items.length]);

  const current = items[index];

  async function choose(signClass: string) {
    if (!current || busy) return;
    setBusy(true);
    try {
      await postLabel(current.id, signClass);
      setIndex((i) => advance(items, i));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold">{t("label.title")}</h1>

      {!current ? (
        <p className="mt-6 opacity-70">{t("label.empty")}</p>
      ) : (
        <>
          <div className="mt-6 flex justify-center">
            {current.crop_url && (
              <img
                src={`${API}${current.crop_url}`}
                alt=""
                className="max-h-80 rounded-lg border object-contain"
              />
            )}
          </div>
          <p className="mt-4 text-center">{t("label.question")}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {SIGN_CLASSES.map((signClass) => (
              <button
                key={signClass}
                onClick={() => choose(signClass)}
                disabled={busy}
                className="rounded border p-3 disabled:opacity-40"
              >
                {t(`classes.${signClass}`)}
              </button>
            ))}
            <button
              onClick={() => choose("unknown")}
              disabled={busy}
              className="col-span-2 rounded border p-3 opacity-70 disabled:opacity-40"
            >
              {t("classes.unknown")}
            </button>
          </div>
          <p className="mt-4 text-center text-xs opacity-50">
            {index + 1} / {items.length}
          </p>
        </>
      )}
    </main>
  );
}
```

- [ ] **Step 6: Verify by hand**

Run: `cd apps/web && npm run dev`, open `http://localhost:3000/fa/label`. With a completed job in the database, crops should appear and clicking a class should advance to the next crop.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src
git commit -m "feat: add labeling queue UI

Presents one crop at a time with the four classes as large buttons. The queue
is served lowest-confidence-first, so labeling effort lands where the
classifier is least sure rather than being spread evenly."
```

---

### Task 15: End-to-end test

**Files:**
- Create: `tests/e2e/playwright.config.ts`, `tests/e2e/flow.spec.ts`, `tests/e2e/seed.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: the running API and web servers
- Produces: `make e2e`

- [ ] **Step 1: Install Playwright**

```bash
cd tests/e2e && npm init -y && npm install -D @playwright/test && npx playwright install chromium
```

- [ ] **Step 2: Write the seed script**

`tests/e2e/seed.py`:

```python
"""Insert one finished job so the e2e run never depends on Mapillary."""

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mithra_api.db import Base
from mithra_api.models import Job, JobStatus, Sign

DB_URL = "postgresql+psycopg://bina:bina@localhost:5432/bina"
JOB_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def main() -> None:
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.query(Sign).filter(Sign.job_id == JOB_ID).delete()
        session.query(Job).filter(Job.id == JOB_ID).delete()
        session.add(Job(
            id=JOB_ID, bbox_west=59.600, bbox_south=36.293, bbox_east=59.609, bbox_north=36.302,
            status=JobStatus.SUCCEEDED, tile_count=1, failed_tile_count=0,
        ))
        session.commit()
        for i, (sign_class, confidence) in enumerate([
            ("street_name", 0.91), ("street_name", 0.88),
            ("direction_guide", 0.79), ("unknown", 0.12),
        ]):
            session.add(Sign(
                job_id=JOB_ID, mapillary_feature_id=f"seed{i}",
                geom=f"SRID=4326;POINT(59.60{i} 36.29{i})",
                sign_class=sign_class, confidence=confidence, model_version="seed-v1",
                needs_review=(sign_class == "unknown"),
            ))
        session.commit()
    print(f"seeded job {JOB_ID}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the Playwright config**

`tests/e2e/playwright.config.ts`:

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  use: { baseURL: "http://localhost:3000", trace: "on-first-retry" },
  timeout: 30_000,
});
```

- [ ] **Step 4: Write the failing e2e test**

`tests/e2e/flow.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const JOB_ID = "11111111-1111-1111-1111-111111111111";

test("the Persian home page loads right-to-left", async ({ page }) => {
  await page.goto("/fa");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByText("بینا")).toBeVisible();
});

test("the English home page loads left-to-right", async ({ page }) => {
  await page.goto("/en");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

test("the results page shows per-class counts", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  await expect(page.getByText("تابلو نام معبر")).toBeVisible();
  await expect(page.getByText("2", { exact: true }).first()).toBeVisible();
});

test("export links are present once the job is finished", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  const csv = page.getByRole("link", { name: /CSV/i });
  await expect(csv).toBeVisible();
  await expect(csv).toHaveAttribute("href", new RegExp(`${JOB_ID}/export.csv`));
});

test("the labeling page offers all four classes", async ({ page }) => {
  await page.goto("/fa/label");
  await expect(page.getByRole("button", { name: "تابلو مسیرنما" })).toBeVisible();
  await expect(page.getByRole("button", { name: "تابلو ورودی شهر" })).toBeVisible();
});
```

- [ ] **Step 5: Add the e2e target to the `Makefile`**

```makefile
.PHONY: e2e
e2e:
	cd services/api && python ../../tests/e2e/seed.py
	cd services/api && uvicorn mithra_api.main:app --port 8000 & echo $$! > /tmp/bina-api.pid
	cd apps/web && npm run build && npm run start & echo $$! > /tmp/bina-web.pid
	sleep 8
	cd tests/e2e && npx playwright test; status=$$?; \
	  kill `cat /tmp/bina-api.pid` `cat /tmp/bina-web.pid` 2>/dev/null; exit $$status
```

- [ ] **Step 6: Run the e2e suite**

Run: `make up && make e2e`
Expected: 5 passed

- [ ] **Step 7: Run everything**

Run: `make test && cd apps/web && npx vitest run`
Expected: all suites pass

- [ ] **Step 8: Commit**

```bash
git add tests/e2e Makefile
git commit -m "test: add end-to-end coverage of the results and labeling flows

The run seeds a finished job directly into the database rather than calling
Mapillary, so e2e exercises the product without depending on a live third
party or a token."
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Tile bbox below 0.01° | 2 |
| OAuth header, proxy, retry/backoff | 3 |
| 401/403 fails fast | 3, 8 |
| Detection geometry decoding | 4 |
| Cropping | 5 |
| CLIP zero-shot cold start, bilingual prompts | 6 |
| Model versioning on every sign | 6, 7, 8 |
| Dedup via `map_features` + unique constraint | 7, 8 |
| `partial` status with failed tiles listed | 8 |
| `no_imagery` succeeds rather than errors | 8 |
| `crop_failed` → counted as `unknown` | 8 |
| Low confidence → `needs_review` | 8 |
| Counts never silently reduced (`failed_count`) | 9, 13 |
| CSV / GeoJSON export | 10 |
| Labeling queue, lowest confidence first | 10, 14 |
| Labels stored separately from sign class | 10 |
| fa default, RTL, en secondary | 11 |
| Map bbox drawing | 12 |
| Counts, pins, table | 13 |
| Unit / integration / e2e testing | 2–15 |
| No live network in CI | 3 (respx; live test skipped without token) |
| Token never logged or returned | 1, 3 |

**Gaps accepted:** The spec mentions fine-tuning a ViT head after ~200 labels per class. That is not a task here — the labels have to exist first, and training is a separate cycle once real label counts are in. Task 6's registry is the seam it plugs into: `register_classifier()` swaps the implementation without touching the pipeline. Map pins are rendered as the results table plus the drawn bbox in Task 13; per-sign pin markers on the results map are a small follow-up, not a separate task.

**Type consistency check:** `Prediction(sign_class, confidence, model_version)` is constructed identically in Tasks 6 and 8 and consumed in 8. `Bbox` is `(west, south, east, north)` in Python (Task 2) and `[west, south, east, north]` in TypeScript (Task 11). `SignOut` fields match `Sign` in `lib/api.ts` exactly. `JobStatus` string values (`queued`/`running`/`succeeded`/`partial`/`failed`) match between `models.py`, `lib/api.ts`, and both translation files. `crop_url` is built in the API as `/api/crops/{id}` and prefixed with the API base in the frontend.

**Ordering note:** Task 1 must run first and can hard-stop the plan. Tasks 2–6 are independent of each other and of the database — they can be built in parallel. Task 7 must precede 8, which must precede 9 and 10. Task 11 must precede 12–14. Task 15 is last.
