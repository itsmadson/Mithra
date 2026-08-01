import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from bina_api.auth import current_user, same_org, visible_jobs
from bina_api.db import get_session
from bina_api.models import Label, Sign, User
from bina_api.schemas import SignList, SignOut
from bina_ml import ALL_CLASSES

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LabelCreate(BaseModel):
    sign_id: uuid.UUID
    sign_class: str

    @field_validator("sign_class")
    @classmethod
    def _known_class(cls, v: str) -> str:
        if v not in ALL_CLASSES:
            raise ValueError(f"sign_class must be one of {ALL_CLASSES}")
        return v


@router.get("/queue", response_model=SignList)
def queue(
    limit: int = Query(default=50, le=500),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> SignList:
    rows = session.execute(
        select(
            Sign.id,
            Sign.sign_class,
            Sign.confidence,
            ST_X(Sign.geom),
            ST_Y(Sign.geom),
            Sign.crop_path,
            Sign.needs_review,
            Sign.mapillary_value,
        )
        .where(
            Sign.needs_review.is_(True),
            Sign.job_id.in_(visible_jobs(user)),
            # Without a crop there is nothing to look at, and the queue is
            # ordered by lowest confidence — so one unviewable sign would sit
            # at the front and stop the whole queue.
            Sign.crop_path.is_not(None),
        )
        .order_by(Sign.confidence.asc())
        .limit(limit)
    ).all()
    return SignList(
        items=[
            SignOut(
                id=r[0],
                sign_class=r[1],
                confidence=r[2],
                lon=r[3],
                lat=r[4],
                crop_url=f"/api/crops/{r[0]}" if r[5] else None,
                needs_review=r[6],
                mapillary_value=r[7],
            )
            for r in rows
        ]
    )


@router.post("", status_code=201)
def create_label(
    payload: LabelCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict[str, str]:
    sign = session.get(Sign, payload.sign_id)
    # Labelling another organisation's sign would write into their training
    # data, so an out-of-scope sign is simply not there.
    if sign is None or not same_org(user, sign.job):
        raise HTTPException(status_code=404, detail="sign not found")

    session.add(
        Label(
            sign_id=sign.id,
            sign_class=payload.sign_class,
            labelled_by_id=user.id,
        )
    )
    sign.sign_class = payload.sign_class
    sign.needs_review = False
    session.commit()
    return {"status": "ok"}
