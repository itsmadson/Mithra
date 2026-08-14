"""Custom tile sources, and the review queue's requirement that a feature be viewable."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.test_api_runs import client  # noqa: F401 - reuse the app fixture

from mithra_api.models import Basemap, Run, Feature

OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def test_a_basemap_can_be_added_and_listed(client):  # noqa: F811
    created = client.post(
        "/api/basemaps", json={"name": "City aerial", "url_template": OSM}
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "City aerial"

    items = client.get("/api/basemaps").json()["items"]
    assert [i["name"] for i in items] == ["City aerial"]


@pytest.mark.parametrize(
    "url",
    [
        "https://tiles.example.com/{z}/{x}.png",  # no {y}
        "https://tiles.example.com/{x}/{y}.png",  # no {z}
        "tiles.example.com/{z}/{x}/{y}.png",  # no scheme
    ],
)
def test_a_template_missing_its_coordinates_is_refused(client, url):  # noqa: F811
    """Every tile would resolve to the same image and the map would repeat one square."""
    assert client.post("/api/basemaps", json={"name": "Broken", "url_template": url}).status_code == 422


def test_only_one_basemap_is_the_default(client):  # noqa: F811
    first = client.post(
        "/api/basemaps", json={"name": "A", "url_template": OSM, "is_default": True}
    ).json()
    second = client.post(
        "/api/basemaps", json={"name": "B", "url_template": OSM, "is_default": True}
    ).json()

    items = {i["id"]: i["is_default"] for i in client.get("/api/basemaps").json()["items"]}
    assert items[second["id"]] is True
    assert items[first["id"]] is False


def test_making_one_default_clears_the_previous_one(client):  # noqa: F811
    a = client.post("/api/basemaps", json={"name": "A", "url_template": OSM, "is_default": True}).json()
    b = client.post("/api/basemaps", json={"name": "B", "url_template": OSM}).json()

    client.patch(f"/api/basemaps/{b['id']}", json={"is_default": True})
    items = {i["id"]: i["is_default"] for i in client.get("/api/basemaps").json()["items"]}
    assert items[b["id"]] is True
    assert items[a["id"]] is False


def test_a_basemap_can_be_deleted(client):  # noqa: F811
    created = client.post("/api/basemaps", json={"name": "Gone", "url_template": OSM}).json()
    assert client.delete(f"/api/basemaps/{created['id']}").status_code == 204
    assert client.get("/api/basemaps").json()["items"] == []


def test_basemaps_require_a_session(client):  # noqa: F811
    client.post("/api/auth/logout")
    assert client.get("/api/basemaps").status_code == 401
    assert client.post("/api/basemaps", json={"name": "X", "url_template": OSM}).status_code == 401


def test_an_operator_cannot_add_a_basemap(client):  # noqa: F811
    """It changes what every operator sees, so it is an administrator's call."""
    client.post(
        "/api/auth/register",
        json={"email": "op@example.com", "password": "a-long-enough-password"},
    )
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": "op@example.com", "password": "a-long-enough-password"},
    )
    assert client.post("/api/basemaps", json={"name": "X", "url_template": OSM}).status_code == 403
    # But they can read the ones their organisation has.
    assert client.get("/api/basemaps").status_code == 200


def _sign(session, run_id, *, crop, confidence):
    feature = Feature(
        run_id=run_id,
        source_feature_id=f"f{confidence}",
        geom="SRID=4326;POINT(59.601 36.294)",
        class_name="unknown",
        confidence=confidence,
        model_version="v1",
        needs_review=True,
        crop_path=crop,
    )
    session.add(feature)
    return feature


def test_the_review_queue_skips_signs_with_no_crop(client):  # noqa: F811
    """The queue is ordered by lowest confidence first.

    A feature with no crop cannot be judged — there is nothing to look at — so one
    of them at the front of the queue stops the operator entirely. That is
    exactly what happened: the lowest-confidence feature in the database had no
    saved crop, and the review screen showed "no image saved" and went no
    further.
    """
    with Session(client.engine) as session:
        job = Run(bbox_west=59.6, bbox_south=36.29, bbox_east=59.61, bbox_north=36.3)
        session.add(job)
        session.commit()
        _sign(session, job.id, crop=None, confidence=0.10)
        _sign(session, job.id, crop="data/crops/a.jpg", confidence=0.40)
        session.commit()

    items = client.get("/api/labels/queue").json()["items"]
    assert len(items) == 1
    assert items[0]["confidence"] == pytest.approx(0.40)


def test_the_queue_is_still_ordered_by_least_confident(client):  # noqa: F811
    with Session(client.engine) as session:
        job = Run(bbox_west=59.6, bbox_south=36.29, bbox_east=59.61, bbox_north=36.3)
        session.add(job)
        session.commit()
        _sign(session, job.id, crop="data/crops/b.jpg", confidence=0.50)
        _sign(session, job.id, crop="data/crops/c.jpg", confidence=0.20)
        session.commit()

    items = client.get("/api/labels/queue").json()["items"]
    assert [round(i["confidence"], 2) for i in items] == [0.20, 0.50]
