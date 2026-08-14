import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.conftest import DB_URL

from mithra_api.db import Base
from mithra_api.models import Run, RunReason, RunStatus, Feature, FeatureReason
from mithra_ml import Prediction
from mithra_worker.mapillary import MapillaryRateLimited
from mithra_worker.pipeline import run_job



@pytest.fixture
def session():
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)


@pytest.fixture
def job(session):
    j = Run(bbox_west=59.600, bbox_south=36.293, bbox_east=59.605, bbox_north=36.298)
    session.add(j)
    session.commit()
    return j


def jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (800, 600), (30, 60, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeClient:
    """Two images observing ONE physical feature — the dedup case."""

    def __init__(self, features=None, detections=None, raise_on_features=None):
        self.features = (
            features
            if features is not None
            else [
                {
                    "id": "feat1",
                    "object_value": "information--parking--g1",
                    "object_type": "trafficsign",
                    "geometry": {"type": "Point", "coordinates": [59.601, 36.294]},
                    "images": {"data": [{"id": "imgA"}, {"id": "imgB"}]},
                }
            ]
        )
        self.detections = (
            detections
            if detections is not None
            else [
                {"id": "d1", "geometry": "ENCODED", "value": "information--parking--g1"}
            ]
        )
        self.raise_on_features = raise_on_features
        self.download_calls = 0

    def get_sign_features(self, bbox, limit=2000):
        if self.raise_on_features:
            raise self.raise_on_features
        return self.features

    def get_detections(self, image_id):
        return self.detections

    def get_image_meta(self, image_id):
        return {
            "id": image_id,
            "width": 800,
            "height": 600,
            "thumb_2048_url": f"https://cdn.example/{image_id}.jpg",
        }

    def download(self, url):
        self.download_calls += 1
        return jpeg_bytes()


class FakeClassifier:
    version = "fake-v1"

    def predict(self, image):
        return Prediction("informational", 0.91, self.version)


def test_one_physical_sign_produces_exactly_one_row(session, job, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "mithra_worker.pipeline.crop_detection", lambda *a, **k: Image.new("RGB", (64, 64))
    )
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    assert len(session.scalars(select(Feature)).all()) == 1


def test_job_succeeds_and_records_the_class(session, job, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "mithra_worker.pipeline.crop_detection", lambda *a, **k: Image.new("RGB", (64, 64))
    )
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    session.refresh(job)
    assert job.status == RunStatus.SUCCEEDED
    feature = session.scalar(select(Feature))
    assert feature.class_name == "informational"
    assert feature.model_version == "fake-v1"
    assert feature.source_value == "information--parking--g1"


def test_crop_is_written_to_disk(session, job, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "mithra_worker.pipeline.crop_detection", lambda *a, **k: Image.new("RGB", (64, 64))
    )
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    assert Path(session.scalar(select(Feature)).crop_path).exists()


def test_empty_coverage_succeeds_with_no_imagery_reason(session, job, tmp_path):
    run_job(session, job.id, FakeClient(features=[]), FakeClassifier(), tmp_path)
    session.refresh(job)
    assert job.status == RunStatus.SUCCEEDED
    assert job.reason == RunReason.NO_IMAGERY


def test_rate_limited_tile_makes_the_job_partial(session, job, tmp_path):
    client = FakeClient(raise_on_features=MapillaryRateLimited("429"))
    run_job(session, job.id, client, FakeClassifier(), tmp_path)
    session.refresh(job)
    assert job.status == RunStatus.PARTIAL
    assert job.failed_tile_count == job.tile_count


def test_crop_failure_still_counts_the_sign_as_unknown(session, job, monkeypatch, tmp_path):
    from mithra_worker.cropper import CropError

    def boom(*a, **k):
        raise CropError("bad geometry")

    monkeypatch.setattr("mithra_worker.pipeline.crop_detection", boom)
    run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)
    feature = session.scalar(select(Feature))
    assert feature.class_name == "unknown"
    assert feature.reason == FeatureReason.CROP_FAILED
    assert feature.needs_review is True


def test_a_non_matching_detection_is_never_cropped_as_the_sign(
    session, job, monkeypatch, tmp_path
):
    """Only a detection whose value matches the feature may be cropped.

    A single Mapillary image carries hundreds of detections — one real image
    held 486, nearly all of them curbs and fences. Falling back to the first
    available detection when none matched cropped a curb or a car window and
    filed it as a traffic feature. Observed directly in a Mashhad run.
    """
    cropped: list[str] = []

    def record(image_bytes, geometry, *a, **k):
        cropped.append(geometry)
        return Image.new("RGB", (64, 64))

    monkeypatch.setattr("mithra_worker.pipeline.crop_detection", record)

    client = FakeClient(
        detections=[
            {"id": "d1", "geometry": "CURB", "value": "construction--barrier--curb"},
            {"id": "d2", "geometry": "FENCE", "value": "construction--barrier--fence"},
        ]
    )
    run_job(session, job.id, client, FakeClassifier(), tmp_path)

    assert cropped == [], "cropped a detection that is not the feature"
    feature = session.scalar(select(Feature))
    assert feature.class_name == "unknown"
    assert feature.reason == FeatureReason.NO_DETECTION


def test_the_matching_detection_is_the_one_cropped(session, job, monkeypatch, tmp_path):
    cropped: list[str] = []

    def record(image_bytes, geometry, *a, **k):
        cropped.append(geometry)
        return Image.new("RGB", (64, 64))

    monkeypatch.setattr("mithra_worker.pipeline.crop_detection", record)

    client = FakeClient(
        detections=[
            {"id": "d1", "geometry": "CURB", "value": "construction--barrier--curb"},
            {"id": "d2", "geometry": "THE_SIGN", "value": "information--parking--g1"},
        ]
    )
    run_job(session, job.id, client, FakeClassifier(), tmp_path)

    assert cropped == ["THE_SIGN"]


def test_feature_with_no_detection_is_counted_as_unknown(session, job, tmp_path):
    run_job(session, job.id, FakeClient(detections=[]), FakeClassifier(), tmp_path)
    feature = session.scalar(select(Feature))
    assert feature.class_name == "unknown"
    assert feature.reason == FeatureReason.NO_DETECTION


def test_worker_crash_marks_the_job_failed_rather_than_leaving_it_running(
    session, job, monkeypatch, tmp_path
):
    """A job whose worker dies must not sit in `running` forever.

    Observed for real: RQ's default job timeout is 180 seconds, which a job that
    downloads and classifies dozens of images blows through. The worker raised
    JobTimeoutException mid-run and the row stayed `running` with nothing left
    to advance it, which is indistinguishable from a job still making progress.
    """

    def boom(*a, **k):
        raise RuntimeError("worker killed")

    monkeypatch.setattr("mithra_worker.pipeline.crop_detection", boom)
    monkeypatch.setattr(
        "mithra_worker.pipeline._classify_feature",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("worker killed")),
    )

    with pytest.raises(RuntimeError):
        run_job(session, job.id, FakeClient(), FakeClassifier(), tmp_path)

    session.refresh(job)
    assert job.status == RunStatus.FAILED
    assert job.reason == RunReason.WORKER_ERROR
    assert job.finished_at is not None


def test_low_confidence_prediction_is_flagged_for_review(session, job, monkeypatch, tmp_path):
    class Unsure:
        version = "unsure-v1"

        def predict(self, image):
            return Prediction("street_name", 0.20, self.version)

    monkeypatch.setattr(
        "mithra_worker.pipeline.crop_detection", lambda *a, **k: Image.new("RGB", (64, 64))
    )
    run_job(session, job.id, FakeClient(), Unsure(), tmp_path, low_confidence_threshold=0.45)
    feature = session.scalar(select(Feature))
    assert feature.needs_review is True
    assert feature.class_name == "street_name"
