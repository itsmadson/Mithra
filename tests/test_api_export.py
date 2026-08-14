import csv
import io

import pytest
from sqlalchemy.orm import Session

from mithra_api.models import Run, Feature
from tests.test_api_runs import client  # noqa: F401 - reuse the app fixture


@pytest.fixture
def job_with_signs(client):  # noqa: F811
    with Session(client.engine) as session:
        job = Run(bbox_west=59.60, bbox_south=36.29, bbox_east=59.61, bbox_north=36.30)
        session.add(job)
        session.commit()
        for i, class_name in enumerate(["street_name", "city_entry"]):
            session.add(
                Feature(
                    run_id=job.id,
                    source_feature_id=f"f{i}",
                    geom="SRID=4326;POINT(59.601 36.294)",
                    class_name=class_name,
                    confidence=0.8,
                    model_version="v1",
                    source_value="information--parking--g1",
                )
            )
        session.commit()
        return str(job.id)


def test_csv_export_has_a_header_and_one_row_per_sign(client, job_with_signs):  # noqa: F811
    response = client.get(f"/api/runs/{job_with_signs}/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "id",
        "class_name",
        "confidence",
        "lon",
        "lat",
        "source_value",
        "needs_review",
    ]
    assert len(rows) == 3


def test_csv_export_sets_a_download_filename(client, job_with_signs):  # noqa: F811
    response = client.get(f"/api/runs/{job_with_signs}/export.csv")
    assert "attachment" in response.headers["content-disposition"]


def test_geojson_export_is_a_valid_feature_collection(client, job_with_signs):  # noqa: F811
    body = client.get(f"/api/runs/{job_with_signs}/export.geojson").json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 2
    feature = body["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == pytest.approx([59.601, 36.294])
    assert feature["properties"]["class_name"] in {"street_name", "city_entry"}


def test_export_of_an_unknown_job_returns_404(client):  # noqa: F811
    assert (
        client.get(
            "/api/runs/00000000-0000-0000-0000-000000000000/export.csv"
        ).status_code
        == 404
    )
