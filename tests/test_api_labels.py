import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.models import Run, Label, Feature
from tests.test_api_runs import client  # noqa: F401


@pytest.fixture
def features(client):  # noqa: F811
    with Session(client.engine) as session:
        job = Run(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        rows = [
            ("unknown", 0.10, True),
            ("street_name", 0.35, True),
            ("city_entry", 0.95, False),
        ]
        ids = []
        for i, (class_name, confidence, review) in enumerate(rows):
            feature = Feature(
                run_id=job.id,
                source_feature_id=f"f{i}",
                geom="SRID=4326;POINT(59.601 36.294)",
                class_name=class_name,
                confidence=confidence,
                model_version="v1",
                needs_review=review,
                # The queue only offers features that can actually be looked at.
                crop_path=f"data/crops/test/{i}.jpg",
            )
            session.add(feature)
            session.commit()
            ids.append(str(feature.id))
        return ids


def test_queue_returns_review_items_lowest_confidence_first(client, features):  # noqa: F811
    items = client.get("/api/labels/queue").json()["items"]
    assert [i["id"] for i in items] == [features[0], features[1]]


def test_queue_respects_the_limit(client, features):  # noqa: F811
    assert len(client.get("/api/labels/queue?limit=1").json()["items"]) == 1


def test_posting_a_label_updates_the_sign_and_clears_review(client, features):  # noqa: F811
    response = client.post("/api/labels", json={"feature_id": features[0], "class_name": "city_entry"})
    assert response.status_code == 201
    with Session(client.engine) as session:
        feature = session.get(Feature, uuid.UUID(features[0]))
        assert feature.class_name == "city_entry"
        assert feature.needs_review is False


def test_posting_a_label_records_ground_truth(client, features):  # noqa: F811
    client.post("/api/labels", json={"feature_id": features[0], "class_name": "city_entry"})
    with Session(client.engine) as session:
        label = session.scalar(select(Label))
        assert label.class_name == "city_entry"


def test_an_invalid_class_is_rejected(client, features):  # noqa: F811
    response = client.post("/api/labels", json={"feature_id": features[0], "class_name": "not_a_class"})
    assert response.status_code == 422


def test_labeling_an_unknown_sign_returns_404(client):  # noqa: F811
    response = client.post(
        "/api/labels",
        json={"feature_id": "00000000-0000-0000-0000-000000000000", "class_name": "city_entry"},
    )
    assert response.status_code == 404
