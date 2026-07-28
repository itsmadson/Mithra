import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bina_api.models import Job, Label, Sign
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
                job_id=job.id,
                mapillary_feature_id=f"f{i}",
                geom="SRID=4326;POINT(59.601 36.294)",
                sign_class=sign_class,
                confidence=confidence,
                model_version="v1",
                needs_review=review,
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
        sign = session.get(Sign, uuid.UUID(signs[0]))
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
    response = client.post(
        "/api/labels",
        json={"sign_id": "00000000-0000-0000-0000-000000000000", "sign_class": "city_entry"},
    )
    assert response.status_code == 404
