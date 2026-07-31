"""Run one detection job end to end.

The only module that knows about tiling, Mapillary, cropping, classification,
and the database at the same time. Everything it calls is independently
testable; this file is the wiring.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from bina_api.models import Job, JobReason, JobStatus, JobTile, Sign, SignReason
from bina_worker.cropper import CropError, crop_detection
from bina_worker.mapillary import MapillaryAuthError, MapillaryError
from bina_worker.tiler import split_bbox

UNKNOWN = "unknown"


def _point(coordinates: list[float]) -> str:
    return f"SRID=4326;POINT({coordinates[0]} {coordinates[1]})"


def _classify_feature(feature, client, classifier, crop_dir: Path):
    """Return (sign_class, confidence, model_version, crop_path, image_id, reason)."""
    image_ids = [i["id"] for i in feature.get("images", {}).get("data", [])]
    for image_id in image_ids:
        try:
            # A single image carries hundreds of detections — one real Mashhad
            # image held 486, nearly all curbs and fences. Only a detection
            # whose value matches this sign may be cropped. There is no
            # fallback: cropping an arbitrary object and filing it as a sign is
            # worse than recording that the sign was not located.
            detections = [
                d
                for d in client.get_detections(image_id)
                if d.get("value") == feature.get("object_value")
            ]
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
            prediction.sign_class,
            prediction.confidence,
            prediction.model_version,
            str(crop_path),
            image_id,
            SignReason.OK,
        )

    return (
        UNKNOWN,
        0.0,
        "",
        None,
        (image_ids[0] if image_ids else None),
        SignReason.NO_DETECTION,
    )


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

    try:
        _run_job(session, job, client, classifier, crop_dir, low_confidence_threshold)
    except BaseException:
        # Deliberately BaseException: RQ enforces its job timeout by raising
        # JobTimeoutException, and a killed worker must not leave the row in
        # `running`, which is indistinguishable from a job still progressing.
        session.rollback()
        job = session.get(Job, job_id)
        if job is not None and job.status not in (
            JobStatus.SUCCEEDED,
            JobStatus.PARTIAL,
            JobStatus.FAILED,
        ):
            job.status = JobStatus.FAILED
            job.reason = JobReason.WORKER_ERROR
            job.finished_at = datetime.now(UTC)
            session.commit()
        raise


def _run_job(
    session: Session,
    job: Job,
    client,
    classifier,
    crop_dir: Path,
    low_confidence_threshold: float,
) -> None:
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

            (
                sign_class,
                confidence,
                version,
                crop_path,
                image_id,
                reason,
            ) = _classify_feature(feature, client, classifier, job_crop_dir)
            session.add(
                Sign(
                    job_id=job.id,
                    mapillary_feature_id=feature_id,
                    image_id=image_id,
                    geom=_point(feature["geometry"]["coordinates"]),
                    sign_class=sign_class,
                    confidence=confidence,
                    model_version=version or getattr(classifier, "version", "unknown"),
                    mapillary_value=feature.get("object_value"),
                    crop_path=crop_path,
                    needs_review=(
                        sign_class == UNKNOWN or confidence < low_confidence_threshold
                    ),
                    reason=reason,
                )
            )

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


def enqueue_job(job_id: str) -> None:
    """RQ task entrypoint. Builds its own dependencies so it can run in a worker process."""
    from sqlalchemy.orm import Session as _Session

    from bina_api.config import get_settings
    from bina_api.db import get_engine
    from bina_ml.registry import get_classifier
    from bina_worker.mapillary import MapillaryClient

    settings = get_settings()
    with (
        _Session(get_engine()) as session,
        MapillaryClient(
            token=settings.mapillary_token.get_secret_value(), proxy=settings.https_proxy
        ) as client,
    ):
        run_job(
            session,
            uuid.UUID(job_id),
            client,
            get_classifier(),
            Path(settings.crop_dir),
            settings.low_confidence_threshold,
        )
