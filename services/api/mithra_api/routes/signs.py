import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org, visible_jobs
from mithra_api.db import get_session
from mithra_api.models import Job, Sign, User
from mithra_api.schemas import SignList, SignOut

router = APIRouter(prefix="/api/jobs", tags=["signs"])

# Cross-survey access. The per-survey routes above answer "what is on this
# street"; this one answers "what have we found anywhere", which is the
# question an inventory is actually for.
all_signs = APIRouter(prefix="/api/signs", tags=["signs"])


@all_signs.get("", response_model=SignList)
def list_all_signs(
    sign_class: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=500, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> SignList:
    statement = select(
        Sign.id,
        Sign.sign_class,
        Sign.confidence,
        ST_X(Sign.geom),
        ST_Y(Sign.geom),
        Sign.crop_path,
        Sign.needs_review,
        Sign.mapillary_value,
        Sign.image_id,
        Sign.model_version,
        Sign.reason,
    ).where(Sign.job_id.in_(visible_jobs(user))).order_by(Sign.created_at.desc())

    if sign_class is not None:
        statement = statement.where(Sign.sign_class == sign_class)
    if needs_review is not None:
        statement = statement.where(Sign.needs_review.is_(needs_review))

    return SignList(
        items=[
            SignOut(
                id=row[0],
                sign_class=row[1],
                confidence=row[2],
                lon=row[3],
                lat=row[4],
                crop_url=f"/api/crops/{row[0]}" if row[5] else None,
                needs_review=row[6],
                mapillary_value=row[7],
                image_id=row[8],
                model_version=row[9],
                reason=row[10],
            )
            for row in session.execute(statement.limit(limit).offset(offset)).all()
        ]
    )


@router.get("/{job_id}/signs", response_model=SignList)
def list_signs(
    job_id: uuid.UUID,
    sign_class: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=1000, le=5000),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> SignList:
    job = session.get(Job, job_id)
    if job is None or not same_org(user, job):
        raise HTTPException(status_code=404, detail="job not found")

    statement = select(
        Sign.id,
        Sign.sign_class,
        Sign.confidence,
        ST_X(Sign.geom),
        ST_Y(Sign.geom),
        Sign.crop_path,
        Sign.needs_review,
        Sign.mapillary_value,
        Sign.image_id,
        Sign.model_version,
        Sign.reason,
    ).where(Sign.job_id == job_id)
    if sign_class is not None:
        statement = statement.where(Sign.sign_class == sign_class)
    if needs_review is not None:
        statement = statement.where(Sign.needs_review.is_(needs_review))

    items = [
        SignOut(
            id=row[0],
            sign_class=row[1],
            confidence=row[2],
            lon=row[3],
            lat=row[4],
            crop_url=f"/api/crops/{row[0]}" if row[5] else None,
            needs_review=row[6],
            mapillary_value=row[7],
            image_id=row[8],
            model_version=row[9],
            reason=row[10],
        )
        for row in session.execute(statement.limit(limit)).all()
    ]
    return SignList(items=items)
