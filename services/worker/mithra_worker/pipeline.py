"""Run one detection job end to end.

The only module that knows about tiling, Mapillary, cropping, classification,
and the database at the same time. Everything it calls is independently
testable; this file is the wiring.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import shape
from sqlalchemy.orm import Session

from mithra_api.models import Run, RunKind, RunReason, RunStatus, RunTile, Feature, FeatureReason
from mithra_worker.corridor import (
    corridor_bbox,
    corridor_geojson,
    corridor_tiles,
    within_corridor,
)
from mithra_worker.osm import OsmError, fetch_named_street_geometry, fetch_way_geometry
from mithra_worker.cropper import CropError, crop_detection
from mithra_worker.mapillary import MapillaryAuthError, MapillaryError
from mithra_worker.tiler import split_bbox

UNKNOWN = "unknown"


def _resolve_street(job) -> list[list[tuple[float, float]]]:
    """Every way segment carrying this street's name, not just the one clicked.

    A named street in OSM is split at junctions and surface changes, so the way
    the operator picked in the search results is typically a few hundred metres
    of a road that runs for kilometres. Surveying only that way would silently
    report a fraction of the street.
    """
    anchor_lat = (job.bbox_south + job.bbox_north) / 2
    anchor_lon = (job.bbox_west + job.bbox_east) / 2

    if job.name:
        try:
            return fetch_named_street_geometry(job.name, anchor_lat, anchor_lon)
        except OsmError:
            pass  # fall back to the single way below

    if job.osm_id is None:
        raise OsmError("job has neither a street name nor an OSM way id")
    return [fetch_way_geometry(job.osm_id)]


def _point(coordinates: list[float]) -> str:
    return f"SRID=4326;POINT({coordinates[0]} {coordinates[1]})"


def _classify_feature(feature, client, classifier, crop_dir: Path):
    """Return (class_name, confidence, model_version, crop_path, image_id, reason)."""
    image_ids = [i["id"] for i in feature.get("images", {}).get("data", [])]
    for image_id in image_ids:
        try:
            # A single image carries hundreds of detections — one real Mashhad
            # image held 486, nearly all curbs and fences. Only a detection
            # whose value matches this feature may be cropped. There is no
            # fallback: cropping an arbitrary object and filing it as a feature is
            # worse than recording that the feature was not located.
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
            return UNKNOWN, 0.0, "", None, image_id, FeatureReason.CROP_FAILED
        except MapillaryError:
            continue

        crop_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crop_dir / f"{feature['id']}.jpg"
        crop.save(crop_path, format="JPEG", quality=90)
        prediction = classifier.predict(crop)
        return (
            prediction.class_name,
            prediction.confidence,
            prediction.model_version,
            str(crop_path),
            image_id,
            FeatureReason.OK,
        )

    return (
        UNKNOWN,
        0.0,
        "",
        None,
        (image_ids[0] if image_ids else None),
        FeatureReason.NO_DETECTION,
    )


def run_job(
    session: Session,
    run_id: uuid.UUID,
    client,
    classifier,
    crop_dir: Path,
    low_confidence_threshold: float = 0.45,
) -> None:
    job = session.get(Run, run_id)
    if job is None:
        raise ValueError(f"job {run_id} not found")

    try:
        # Two genuinely different jobs share this record: walking a street with
        # panoramas, and reading a window of overhead imagery. They branch here
        # rather than inside one function pretending to do both.
        if job.source_kind and job.source_kind != "mapillary":
            _run_raster(session, job)
        else:
            _run_job(session, job, client, classifier, crop_dir, low_confidence_threshold)
    except BaseException:
        # Deliberately BaseException: RQ enforces its job timeout by raising
        # JobTimeoutException, and a killed worker must not leave the row in
        # `running`, which is indistinguishable from a job still progressing.
        session.rollback()
        job = session.get(Run, run_id)
        if job is not None and job.status not in (
            RunStatus.SUCCEEDED,
            RunStatus.PARTIAL,
            RunStatus.FAILED,
        ):
            job.status = RunStatus.FAILED
            job.reason = RunReason.WORKER_ERROR
            job.finished_at = datetime.now(UTC)
            session.commit()
        raise


def _run_raster(session: Session, job: Run) -> None:
    """A detection run over satellite, aerial or uploaded imagery."""
    from mithra_worker.raster_pipeline import (
        RunRefused,
        detect_over_area,
        geometry_to_ewkt,
    )
    from mithra_worker.imagery import ImageryError

    job.status = RunStatus.RUNNING
    session.commit()

    bbox = (job.bbox_west, job.bbox_south, job.bbox_east, job.bbox_north)
    try:
        detections, provenance = detect_over_area(
            job.source_kind,
            dict(job.source_config or {}),
            bbox,
            list(job.targets or []),
            job.detector,
        )
    except RunRefused as exc:
        # A refusal is a finished run with an answer, not a crash: the answer
        # is "this cannot be asked of this imagery", and it belongs on the row.
        job.status = RunStatus.FAILED
        job.reason = str(exc)[:32]
        job.finished_at = datetime.now(UTC)
        session.commit()
        return
    except ImageryError as exc:
        job.status = RunStatus.FAILED
        job.reason = RunReason.NO_IMAGERY
        job.finished_at = datetime.now(UTC)
        session.commit()
        raise RuntimeError(str(exc)) from exc

    job.gsd_m = provenance.get("gsd_m")
    job.tile_count = 1

    for index, detection in enumerate(detections):
        session.add(
            Feature(
                run_id=job.id,
                # Stable within the run, so a re-run cannot double-count.
                source_feature_id=f"{provenance.get('scene_id', job.source_kind)}:{index}",
                geom=geometry_to_ewkt(detection.geometry),
                class_name=detection.class_name,
                confidence=detection.confidence,
                area_m2=detection.area_m2,
                model_version=job.detector,
                source_value=provenance.get("scene_id"),
                needs_review=False,
            )
        )

    job.status = RunStatus.SUCCEEDED
    job.finished_at = datetime.now(UTC)
    session.commit()


def _run_job(
    session: Session,
    job: Run,
    client,
    classifier,
    crop_dir: Path,
    low_confidence_threshold: float,
) -> None:
    job.status = RunStatus.RUNNING
    session.commit()

    # A street survey resolves its geometry first: the tiles follow the road,
    # and features are afterwards checked against the centreline so a tile that
    # happens to clip a neighbouring street does not contribute its features.
    segments: list[list[tuple[float, float]]] | None = None
    if job.kind == RunKind.STREET:
        try:
            segments = _resolve_street(job)
        except OsmError as exc:
            job.status = RunStatus.FAILED
            job.reason = RunReason.STREET_NOT_FOUND
            job.finished_at = datetime.now(UTC)
            session.commit()
            raise ValueError(f"street lookup failed for job {job.id}: {exc}") from exc

        west, south, east, north = corridor_bbox(segments, job.buffer_m)
        job.bbox_west, job.bbox_south, job.bbox_east, job.bbox_north = (
            west,
            south,
            east,
            north,
        )
        job.geom = f"SRID=4326;{shape(corridor_geojson(segments)).wkt}"
        tiles = corridor_tiles(segments, job.buffer_m)
    else:
        tiles = split_bbox(
            (job.bbox_west, job.bbox_south, job.bbox_east, job.bbox_north)
        )

    job.tile_count = len(tiles)
    job.failed_tile_count = 0
    session.commit()

    seen: set[str] = set()
    job_crop_dir = Path(crop_dir) / str(job.id)

    for west, south, east, north in tiles:
        tile = RunTile(run_id=job.id, west=west, south=south, east=east, north=north)
        session.add(tile)
        try:
            features = client.get_sign_features((west, south, east, north))
        except MapillaryAuthError as exc:
            tile.status = RunStatus.FAILED
            tile.error = str(exc)[:500]
            job.status = RunStatus.FAILED
            job.reason = RunReason.AUTH_FAILED
            job.failed_tile_count += 1
            job.finished_at = datetime.now(UTC)
            session.commit()
            return
        except MapillaryError as exc:
            tile.status = RunStatus.FAILED
            tile.error = str(exc)[:500]
            job.failed_tile_count += 1
            session.commit()
            continue

        for feature in features:
            feature_id = feature["id"]
            if feature_id in seen:
                continue

            # Outside the corridor means it belongs to another street, not to
            # this survey. Skipped before classification so no work is wasted.
            if segments is not None:
                lon, lat = feature["geometry"]["coordinates"][:2]
                if not within_corridor(segments, job.buffer_m, lon, lat):
                    continue

            seen.add(feature_id)

            (
                class_name,
                confidence,
                version,
                crop_path,
                image_id,
                reason,
            ) = _classify_feature(feature, client, classifier, job_crop_dir)
            session.add(
                Feature(
                    run_id=job.id,
                    source_feature_id=feature_id,
                    image_id=image_id,
                    geom=_point(feature["geometry"]["coordinates"]),
                    class_name=class_name,
                    confidence=confidence,
                    model_version=version or getattr(classifier, "version", "unknown"),
                    source_value=feature.get("object_value"),
                    crop_path=crop_path,
                    needs_review=(
                        class_name == UNKNOWN or confidence < low_confidence_threshold
                    ),
                    reason=reason,
                )
            )

        tile.status = RunStatus.SUCCEEDED
        session.commit()

    if job.failed_tile_count:
        job.status = RunStatus.PARTIAL
    else:
        job.status = RunStatus.SUCCEEDED
        if not seen:
            job.reason = RunReason.NO_IMAGERY
    job.finished_at = datetime.now(UTC)
    session.commit()


def enqueue_job(run_id: str) -> None:
    """RQ task entrypoint. Builds its own dependencies so it can run in a worker process."""
    from sqlalchemy.orm import Session as _Session

    from mithra_api.config import get_settings
    from mithra_api.db import get_engine
    from mithra_ml.registry import get_classifier
    from mithra_worker.mapillary import MapillaryClient

    settings = get_settings()
    with (
        _Session(get_engine()) as session,
        MapillaryClient(
            token=settings.mapillary_token.get_secret_value(), proxy=settings.https_proxy
        ) as client,
    ):
        run_job(
            session,
            uuid.UUID(run_id),
            client,
            get_classifier(),
            Path(settings.crop_dir),
            settings.low_confidence_threshold,
        )
