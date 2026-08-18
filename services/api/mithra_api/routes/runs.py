import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org, visible_jobs
from mithra_api.audit import Action, record
from mithra_api.db import get_session
from mithra_api.models import Run, RunKind, RunReason, RunStatus, Feature, FeatureReason, User
from mithra_api.schemas import (
    RunCreate,
    RunCreated,
    RunList,
    RunStatusOut,
    RunSummary,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])

# RQ defaults to a 180 second job timeout. A single Mapillary-legal tile in
# central Mashhad holds around 58 features, each needing an image download and a
# CLIP forward pass, so the default killed real jobs part-way through and left
# them stuck looking like they were still running.
JOB_TIMEOUT_SECONDS = 6 * 60 * 60


def enqueue(run_id: str) -> None:
    """Indirection so tests can substitute a recorder for the queue."""
    import redis
    import rq

    from mithra_api.config import get_settings

    queue = rq.Queue(connection=redis.Redis.from_url(get_settings().redis_url))
    queue.enqueue(
        "mithra_worker.pipeline.enqueue_job",
        run_id,
        job_timeout=JOB_TIMEOUT_SECONDS,
        result_ttl=24 * 60 * 60,
    )


def _counts(session: Session, run_id: uuid.UUID) -> tuple[dict[str, int], int]:
    rows = session.execute(
        select(Feature.class_name, func.count())
        .where(Feature.run_id == run_id)
        .group_by(Feature.class_name)
    ).all()
    counts = {class_name: n for class_name, n in rows}
    failed = (
        session.scalar(
            select(func.count())
            .select_from(Feature)
            .where(Feature.run_id == run_id, Feature.reason != FeatureReason.OK)
        )
        or 0
    )
    return counts, failed


@router.post("", response_model=RunCreated, status_code=201)
def create_job(
    payload: RunCreate,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> RunCreated:
    # The catalogue decides whether this pairing can produce an honest answer.
    # Refusing here costs a millisecond; refusing after the run costs an hour
    # and hands back an empty layer that reads as "there is none of that here".
    try:
        from mithra_worker.raster_pipeline import (
            RunRefused,
            check_imagery_kind,
            check_targets,
        )

        # Both gates, not just the resolution one. A drawn basemap used to be
        # accepted here and refused an hour later by the worker, which is the
        # exact cost this check exists to avoid.
        check_imagery_kind(payload.source_kind, payload.source_config)
        check_targets(payload.source_kind, payload.targets, payload.source_config.get("gsd_m"))
    except RunRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportError:  # pragma: no cover - the API can run without the worker
        pass

    if payload.bbox is not None:
        west, south, east, north = payload.bbox
        name = payload.name or f"{south:.4f},{west:.4f} → {north:.4f},{east:.4f}"
        job = Run(
            name=name,
            kind=RunKind.BBOX,
            bbox_west=west,
            bbox_south=south,
            bbox_east=east,
            bbox_north=north,
            owner_id=user.id,
            org_id=user.org_id,
            source_kind=payload.source_kind,
            source_config=payload.source_config,
            targets=payload.targets,
            detector=payload.detector,
        )
    else:
        # The corridor geometry is resolved by the worker, which owns the OSM
        # calls; the bbox here is a placeholder around the anchor point so the
        # row is valid before the worker replaces it with the real extent.
        lat, lon = payload.lat, payload.lon
        assert lat is not None and lon is not None  # guaranteed by RunCreate
        job = Run(
            name=payload.name or payload.street_name or f"way {payload.osm_id}",
            kind=RunKind.STREET,
            osm_id=payload.osm_id,
            buffer_m=payload.buffer_m,
            bbox_west=lon - 0.001,
            bbox_south=lat - 0.001,
            bbox_east=lon + 0.001,
            bbox_north=lat + 0.001,
            owner_id=user.id,
            org_id=user.org_id,
            source_kind=payload.source_kind,
            source_config=payload.source_config,
            targets=payload.targets,
            detector=payload.detector,
        )

    session.add(job)
    session.commit()

    # The row is committed first so there is an id to hand to the queue. If the
    # queue is unreachable, nothing will ever pick this job up, so it is marked
    # failed here rather than left sitting in `queued` looking like it is still
    # waiting its turn.
    try:
        enqueue(str(job.id))
    except Exception as exc:  # noqa: BLE001 - any queue failure has one outcome
        job.status = RunStatus.FAILED
        job.reason = RunReason.ENQUEUE_FAILED
        session.commit()
        raise HTTPException(
            status_code=503, detail="job queue unavailable, job not started"
        ) from exc

    # Recorded after the queue accepted it: a run that never started is not a
    # run somebody performed, and a log full of them is noise.
    record(
        session,
        action=Action.RUN_CREATED,
        actor=user,
        subject_type="run",
        subject_id=job.id,
        detail={
            "name": job.name,
            "source": job.source_kind,
            "targets": job.targets,
            "detector": job.detector,
        },
        request=request,
    )
    session.commit()

    return RunCreated(id=job.id, status=job.status)


@router.get("", response_model=RunList)
def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> RunList:
    """Newest first, and only this organisation's surveys."""
    mine = visible_jobs(user)
    total = session.scalar(select(func.count()).select_from(Run).where(Run.id.in_(mine))) or 0

    # One grouped query for the per-job totals rather than N queries in a loop.
    sign_totals = dict(
        session.execute(
            select(Feature.run_id, func.count())
            .where(Feature.run_id.in_(mine))
            .group_by(Feature.run_id)
        ).all()
    )
    failed_totals = dict(
        session.execute(
            select(Feature.run_id, func.count())
            .where(Feature.run_id.in_(mine), Feature.reason != FeatureReason.OK)
            .group_by(Feature.run_id)
        ).all()
    )

    jobs = session.scalars(
        select(Run)
        .where(Run.id.in_(mine))
        .order_by(Run.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return RunList(
        total=total,
        items=[
            RunSummary(
                id=job.id,
                name=job.name,
                kind=job.kind,
                status=job.status,
                reason=job.reason,
                total=sign_totals.get(job.id, 0),
                failed_count=failed_totals.get(job.id, 0),
                tile_count=job.tile_count,
                failed_tile_count=job.failed_tile_count,
                created_at=job.created_at,
                finished_at=job.finished_at,
            )
            for job in jobs
        ],
    )


@router.get("/{run_id}", response_model=RunStatusOut)
def get_job(
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> RunStatusOut:
    job = session.get(Run, run_id)
    # Another organisation's survey is reported as absent rather than
    # forbidden: "you may not see this" still confirms it exists.
    if job is None or not same_org(user, job):
        raise HTTPException(status_code=404, detail="job not found")

    counts, failed_count = _counts(session, job.id)

    geometry = None
    if job.geom is not None:
        raw = session.scalar(select(ST_AsGeoJSON(Run.geom)).where(Run.id == job.id))
        if raw:
            geometry = json.loads(raw)

    return RunStatusOut(
        id=job.id,
        name=job.name,
        kind=job.kind,
        status=job.status,
        reason=job.reason,
        bbox=[job.bbox_west, job.bbox_south, job.bbox_east, job.bbox_north],
        geometry=geometry,
        buffer_m=job.buffer_m,
        osm_id=job.osm_id,
        tile_count=job.tile_count,
        failed_tile_count=job.failed_tile_count,
        counts=counts,
        total=sum(counts.values()),
        failed_count=failed_count,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.delete("/{run_id}", status_code=204)
def delete_job(
    run_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> None:
    job = session.get(Run, run_id)
    if job is None or not same_org(user, job):
        raise HTTPException(status_code=404, detail="job not found")

    # Surveys are shared, but deleting one destroys work. Only the person who
    # ran it, or an administrator, may do that. Ownerless surveys predate
    # accounts and are administrator-only.
    from mithra_api.models import UserRole

    if user.role != UserRole.ADMIN and job.owner_id != user.id:
        raise HTTPException(status_code=403, detail="only the owner may delete this survey")

    # Written before the delete, while there is still something to describe —
    # and it names what was destroyed, since that is the question asked
    # afterwards.
    record(
        session,
        action=Action.RUN_DELETED,
        actor=user,
        subject_type="run",
        subject_id=job.id,
        detail={"name": job.name, "features": sum(_counts(session, job.id)[0].values())},
        request=request,
    )
    session.delete(job)
    session.commit()
