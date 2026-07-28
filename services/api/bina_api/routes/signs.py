import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.orm import Session

from bina_api.db import get_session
from bina_api.models import Job, Sign
from bina_api.schemas import SignList, SignOut

router = APIRouter(prefix="/api/jobs", tags=["signs"])


@router.get("/{job_id}/signs", response_model=SignList)
def list_signs(
    job_id: uuid.UUID,
    sign_class: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=1000, le=5000),
    session: Session = Depends(get_session),
) -> SignList:
    if session.get(Job, job_id) is None:
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
        )
        for row in session.execute(statement.limit(limit)).all()
    ]
    return SignList(items=items)
