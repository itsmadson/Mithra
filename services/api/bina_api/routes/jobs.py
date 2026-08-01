import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bina_api.auth import current_user
from bina_api.db import get_session
from bina_api.models import Job, JobKind, JobReason, JobStatus, Sign, SignReason, User
from bina_api.schemas import (
    JobCreate,
    JobCreated,
    JobList,
    JobStatusOut,
    JobSummary,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# RQ defaults to a 180 second job timeout. A single Mapillary-legal tile in
# central Mashhad holds around 58 signs, each needing an image download and a
# CLIP forward pass, so the default killed real jobs part-way through and left
# them stuck looking like they were still running.
JOB_TIMEOUT_SECONDS = 6 * 60 * 60


def enqueue(job_id: str) -> None:
    """Indirection so tests can substitute a recorder for the queue."""
    import redis
    import rq

    from bina_api.config import get_settings

    queue = rq.Queue(connection=redis.Redis.from_url(get_settings().redis_url))
    queue.enqueue(
        "bina_worker.pipeline.enqueue_job",
        job_id,
        job_timeout=JOB_TIMEOUT_SECONDS,
        result_ttl=24 * 60 * 60,
    )


def _counts(session: Session, job_id: uuid.UUID) -> tuple[dict[str, int], int]:
    rows = session.execute(
        select(Sign.sign_class, func.count())
        .where(Sign.job_id == job_id)
        .group_by(Sign.sign_class)
    ).all()
    counts = {sign_class: n for sign_class, n in rows}
    failed = (
        session.scalar(
            select(func.count())
            .select_from(Sign)
            .where(Sign.job_id == job_id, Sign.reason != SignReason.OK)
        )
        or 0
    )
    return counts, failed


@router.post("", response_model=JobCreated, status_code=201)
def create_job(
    payload: JobCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> JobCreated:
    if payload.bbox is not None:
        west, south, east, north = payload.bbox
        name = payload.name or f"{south:.4f},{west:.4f} → {north:.4f},{east:.4f}"
        job = Job(
            name=name,
            kind=JobKind.BBOX,
            bbox_west=west,
            bbox_south=south,
            bbox_east=east,
            bbox_north=north,
            owner_id=user.id,
        )
    else:
        # The corridor geometry is resolved by the worker, which owns the OSM
        # calls; the bbox here is a placeholder around the anchor point so the
        # row is valid before the worker replaces it with the real extent.
        lat, lon = payload.lat, payload.lon
        assert lat is not None and lon is not None  # guaranteed by JobCreate
        job = Job(
            name=payload.name or payload.street_name or f"way {payload.osm_id}",
            kind=JobKind.STREET,
            osm_id=payload.osm_id,
            buffer_m=payload.buffer_m,
            bbox_west=lon - 0.001,
            bbox_south=lat - 0.001,
            bbox_east=lon + 0.001,
            bbox_north=lat + 0.001,
            owner_id=user.id,
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
        job.status = JobStatus.FAILED
        job.reason = JobReason.ENQUEUE_FAILED
        session.commit()
        raise HTTPException(
            status_code=503, detail="job queue unavailable, job not started"
        ) from exc

    return JobCreated(id=job.id, status=job.status)


@router.get("", response_model=JobList)
def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    _user=Depends(current_user),
) -> JobList:
    """Newest first. This is the dashboard's home view."""
    total = session.scalar(select(func.count()).select_from(Job)) or 0

    # One grouped query for the per-job totals rather than N queries in a loop.
    sign_totals = dict(
        session.execute(select(Sign.job_id, func.count()).group_by(Sign.job_id)).all()
    )
    failed_totals = dict(
        session.execute(
            select(Sign.job_id, func.count())
            .where(Sign.reason != SignReason.OK)
            .group_by(Sign.job_id)
        ).all()
    )

    jobs = session.scalars(
        select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()

    return JobList(
        total=total,
        items=[
            JobSummary(
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


@router.get("/{job_id}", response_model=JobStatusOut)
def get_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    _user: User = Depends(current_user),
) -> JobStatusOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    counts, failed_count = _counts(session, job.id)

    geometry = None
    if job.geom is not None:
        raw = session.scalar(select(ST_AsGeoJSON(Job.geom)).where(Job.id == job.id))
        if raw:
            geometry = json.loads(raw)

    return JobStatusOut(
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


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> None:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    # Surveys are shared, but deleting one destroys work. Only the person who
    # ran it, or an administrator, may do that. Ownerless surveys predate
    # accounts and are administrator-only.
    from bina_api.models import UserRole

    if user.role != UserRole.ADMIN and job.owner_id != user.id:
        raise HTTPException(status_code=403, detail="only the owner may delete this survey")

    session.delete(job)
    session.commit()
