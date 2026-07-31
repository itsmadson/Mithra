import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.conftest import DB_URL

from bina_api.db import Base, get_session
from bina_api.main import app
from bina_api.models import Job, JobReason, JobStatus, Sign



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
    monkeypatch.setattr("bina_api.routes.jobs.enqueue", lambda job_id: enqueued.append(job_id))
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


def test_enqueue_failure_does_not_leave_an_orphan_queued_job(client, monkeypatch):
    """A job that was never enqueued must not sit in `queued` forever.

    The row is committed before the enqueue so the id exists to hand to the
    queue. If the queue is unreachable, nothing will ever pick the job up, so
    it has to be marked failed rather than left looking like it is waiting.
    """

    def unreachable(job_id):
        raise ConnectionError("Error 111 connecting to localhost:6381")

    monkeypatch.setattr("bina_api.routes.jobs.enqueue", unreachable)

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
