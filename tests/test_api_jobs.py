import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.conftest import DB_URL

from mithra_api.db import Base, get_session
from mithra_api.main import app
from mithra_api.models import Job, JobReason, JobStatus, Sign



@pytest.fixture
def client(monkeypatch):
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
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

    # Every data route now requires a session. The first registration becomes
    # the administrator and is signed in, which is the state these tests assume.
    test_client.post(
        "/api/auth/register",
        json={"email": "tester@example.com", "password": "a-long-enough-password"},
    )

    yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    # Dispose the pool, not just the tables: every fixture opens its own
    # engine, and Postgres allows 100 clients. Leaving them behind means the
    # suite fails on whichever test happens to be running when it crosses that
    # line, which reads as a bug in that test rather than in the fixtures.
    engine.dispose()


def test_creating_a_job_returns_queued_and_enqueues_work(client):
    response = client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.64, 36.33]})
    assert response.status_code == 201
    assert response.json()["status"] == JobStatus.QUEUED
    assert len(client.enqueued) == 1


def test_enqueue_failure_does_not_leave_an_orphan_queued_job(client, monkeypatch):
    """A job that was never enqueued must not sit in `queued` forever.

    The row is committed before the enqueue so the id exists to hand to the
    queue. If the queue is unreachable, nothing will ever pick the job up, so
    it has to be marked failed rather than left looking like it is waiting.
    """

    def unreachable(job_id):
        raise ConnectionError("Error 111 connecting to localhost:6381")

    monkeypatch.setattr("mithra_api.routes.jobs.enqueue", unreachable)

    response = client.post("/api/jobs", json={"bbox": [59.60, 36.29, 59.61, 36.30]})
    assert response.status_code == 503

    with Session(client.engine) as session:
        job = session.scalars(select(Job)).one()
        assert job.status == JobStatus.FAILED
        assert job.reason == JobReason.ENQUEUE_FAILED


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
        job = Job(
            bbox_west=59.60,
            bbox_south=36.29,
            bbox_east=59.61,
            bbox_north=36.30,
            status=JobStatus.SUCCEEDED,
            tile_count=4,
            failed_tile_count=0,
        )
        session.add(job)
        session.commit()
        for i, (sign_class, reason) in enumerate(
            [
                ("street_name", "ok"),
                ("street_name", "ok"),
                ("direction_guide", "ok"),
                ("unknown", "crop_failed"),
            ]
        ):
            session.add(
                Sign(
                    job_id=job.id,
                    mapillary_feature_id=f"f{i}",
                    geom="SRID=4326;POINT(59.601 36.294)",
                    sign_class=sign_class,
                    confidence=0.8,
                    model_version="v1",
                    reason=reason,
                )
            )
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
            session.add(
                Sign(
                    job_id=job.id,
                    mapillary_feature_id=f"f{i}",
                    geom="SRID=4326;POINT(59.601 36.294)",
                    sign_class=sign_class,
                    confidence=0.8,
                    model_version="v1",
                )
            )
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
        session.add(
            Sign(
                job_id=job.id,
                mapillary_feature_id="f1",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class="street_name",
                confidence=0.8,
                model_version="v1",
            )
        )
        session.commit()
        job_id = str(job.id)

    item = client.get(f"/api/jobs/{job_id}/signs").json()["items"][0]
    assert item["lon"] == pytest.approx(59.601)
    assert item["lat"] == pytest.approx(36.294)


def test_enqueue_sets_a_timeout_long_enough_for_a_real_job(monkeypatch):
    """RQ defaults to a 180 second job timeout, which real jobs exceed.

    A central Mashhad tile alone holds ~58 signs, each needing an image
    download and a CLIP forward pass. The default killed the job mid-run.
    """
    from mithra_api.routes.jobs import JOB_TIMEOUT_SECONDS, enqueue

    assert JOB_TIMEOUT_SECONDS >= 3600

    captured = {}

    class FakeQueue:
        def __init__(self, connection=None):
            captured["connected"] = True

        def enqueue(self, func, *args, **kwargs):
            captured["func"] = func
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr("redis.Redis.from_url", lambda url: object())
    monkeypatch.setattr("rq.Queue", FakeQueue)

    enqueue("job-1")

    assert captured["func"] == "mithra_worker.pipeline.enqueue_job"
    assert captured["args"] == ("job-1",)
    assert captured["kwargs"]["job_timeout"] == JOB_TIMEOUT_SECONDS


def test_signs_expose_detection_provenance(client):
    """A count that cannot be traced back to an image is not auditable."""
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        session.add(
            Sign(
                job_id=job.id,
                mapillary_feature_id="f1",
                image_id="1020361045275024",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class="direction_guide",
                confidence=0.81,
                model_version="clip-zeroshot-ViT-B-32-v1",
                mapillary_value="information--general-directions--g1",
                reason="ok",
            )
        )
        session.commit()
        job_id = str(job.id)

    item = client.get(f"/api/jobs/{job_id}/signs").json()["items"][0]
    assert item["image_id"] == "1020361045275024"
    assert item["model_version"] == "clip-zeroshot-ViT-B-32-v1"
    assert item["mapillary_value"] == "information--general-directions--g1"
    assert item["reason"] == "ok"


def test_job_status_returns_the_requested_bbox(client):
    """The client frames its map on this; without it an empty result has no context."""
    with Session(client.engine) as session:
        job = Job(bbox_west=59.600, bbox_south=36.293, bbox_east=59.609, bbox_north=36.302)
        session.add(job)
        session.commit()
        job_id = str(job.id)

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["bbox"] == pytest.approx([59.600, 36.293, 59.609, 36.302])


def test_street_survey_is_created_without_a_bbox(client):
    """A survey is defined by a معبر; the corridor bbox is the worker's job."""
    response = client.post(
        "/api/jobs",
        json={
            "street_name": "خیابان امام رضا",
            "osm_id": 44641660,
            "lat": 36.2857,
            "lon": 59.6138,
            "buffer_m": 30,
        },
    )
    assert response.status_code == 201

    with Session(client.engine) as session:
        job = session.scalars(select(Job)).one()
        assert job.kind == "street"
        assert job.name == "خیابان امام رضا"
        assert job.osm_id == 44641660
        assert job.buffer_m == 30


def test_a_survey_cannot_be_both_a_street_and_a_bbox(client):
    response = client.post(
        "/api/jobs",
        json={
            "street_name": "x",
            "lat": 36.3,
            "lon": 59.6,
            "bbox": [59.60, 36.29, 59.61, 36.30],
        },
    )
    assert response.status_code == 422


def test_a_survey_must_be_one_or_the_other(client):
    assert client.post("/api/jobs", json={}).status_code == 422


def test_a_street_survey_needs_an_anchor_point(client):
    response = client.post("/api/jobs", json={"street_name": "x", "osm_id": 1})
    assert response.status_code == 422


def test_buffer_width_is_bounded(client):
    response = client.post(
        "/api/jobs",
        json={"street_name": "x", "lat": 36.3, "lon": 59.6, "buffer_m": 5000},
    )
    assert response.status_code == 422


def test_job_list_is_newest_first_and_carries_counts(client):
    with Session(client.engine) as session:
        for i in range(3):
            job = Job(
                name=f"survey {i}",
                bbox_west=59.60,
                bbox_south=36.29,
                bbox_east=59.61,
                bbox_north=36.30,
            )
            session.add(job)
            session.commit()
            if i == 2:
                session.add(
                    Sign(
                        job_id=job.id,
                        mapillary_feature_id="f1",
                        geom="SRID=4326;POINT(59.601 36.294)",
                        sign_class="street_name",
                        confidence=0.8,
                        model_version="v1",
                    )
                )
                session.commit()

    body = client.get("/api/jobs").json()
    assert body["total"] == 3
    assert [i["name"] for i in body["items"]] == ["survey 2", "survey 1", "survey 0"]
    assert body["items"][0]["total"] == 1
    assert body["items"][1]["total"] == 0


def test_a_survey_can_be_deleted(client):
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        job_id = str(job.id)

    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_features_endpoint_serves_geojson(client):
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        session.add(
            Sign(
                job_id=job.id,
                mapillary_feature_id="f1",
                image_id="img1",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class="direction_guide",
                confidence=0.81,
                model_version="clip-v1",
                mapillary_value="information--general-directions--g1",
            )
        )
        session.commit()
        job_id = str(job.id)

    response = client.get(f"/api/jobs/{job_id}/features")
    assert response.status_code == 200
    assert "geo+json" in response.headers["content-type"]

    body = response.json()
    assert body["type"] == "FeatureCollection"
    feature = body["features"][0]
    assert feature["geometry"] == {"type": "Point", "coordinates": [59.601, 36.294]}
    assert feature["properties"]["sign_class"] == "direction_guide"
    assert feature["properties"]["image_id"] == "img1"


def test_features_can_be_filtered_by_class(client):
    with Session(client.engine) as session:
        job = Job(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        for i, cls in enumerate(["direction_guide", "street_name"]):
            session.add(
                Sign(
                    job_id=job.id,
                    mapillary_feature_id=f"f{i}",
                    geom="SRID=4326;POINT(59.601 36.294)",
                    sign_class=cls,
                    confidence=0.8,
                    model_version="v1",
                )
            )
        session.commit()
        job_id = str(job.id)

    body = client.get(f"/api/jobs/{job_id}/features?sign_class=street_name").json()
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["sign_class"] == "street_name"
