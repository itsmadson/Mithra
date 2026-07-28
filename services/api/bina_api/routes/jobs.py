import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bina_api.db import get_session
from bina_api.models import Job, Sign, SignReason
from bina_api.schemas import JobCreate, JobCreated, JobStatusOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def enqueue(job_id: str) -> None:
    """Indirection so tests can substitute a recorder for the queue."""
    from redis import Redis
    from rq import Queue

    from bina_api.config import get_settings

    Queue(connection=Redis.from_url(get_settings().redis_url)).enqueue(
        "bina_worker.pipeline.enqueue_job", job_id
    )


@router.post("", response_model=JobCreated, status_code=201)
def create_job(payload: JobCreate, session: Session = Depends(get_session)) -> JobCreated:
    west, south, east, north = payload.bbox
    job = Job(bbox_west=west, bbox_south=south, bbox_east=east, bbox_north=north)
    session.add(job)
    session.commit()
    enqueue(str(job.id))
    return JobCreated(id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusOut)
def get_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> JobStatusOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    rows = session.execute(
        select(Sign.sign_class, func.count())
        .where(Sign.job_id == job.id)
        .group_by(Sign.sign_class)
    ).all()
    counts = {sign_class: n for sign_class, n in rows}
    failed_count = (
        session.scalar(
            select(func.count())
            .select_from(Sign)
            .where(Sign.job_id == job.id, Sign.reason != SignReason.OK)
        )
        or 0
    )

    return JobStatusOut(
        id=job.id,
        status=job.status,
        reason=job.reason,
        tile_count=job.tile_count,
        failed_tile_count=job.failed_tile_count,
        counts=counts,
        total=sum(counts.values()),
        failed_count=failed_count,
    )
