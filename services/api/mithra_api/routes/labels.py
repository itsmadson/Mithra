import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org, visible_jobs
from mithra_api.db import get_session
from mithra_api.models import Label, Feature, User
from mithra_api.schemas import FeatureList, FeatureOut
from mithra_ml import ALL_CLASSES

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LabelCreate(BaseModel):
    feature_id: uuid.UUID
    class_name: str

    @field_validator("class_name")
    @classmethod
    def _known_class(cls, v: str) -> str:
        if v not in ALL_CLASSES:
            raise ValueError(f"class_name must be one of {ALL_CLASSES}")
        return v


@router.get("/queue", response_model=FeatureList)
def queue(
    limit: int = Query(default=50, le=500),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FeatureList:
    rows = session.execute(
        select(
            Feature.id,
            Feature.class_name,
            Feature.confidence,
            ST_X(Feature.geom),
            ST_Y(Feature.geom),
            Feature.crop_path,
            Feature.needs_review,
            Feature.source_value,
        )
        .where(
            Feature.needs_review.is_(True),
            Feature.run_id.in_(visible_jobs(user)),
            # Without a crop there is nothing to look at, and the queue is
            # ordered by lowest confidence — so one unviewable feature would sit
            # at the front and stop the whole queue.
            Feature.crop_path.is_not(None),
        )
        .order_by(Feature.confidence.asc())
        .limit(limit)
    ).all()
    return FeatureList(
        items=[
            FeatureOut(
                id=r[0],
                class_name=r[1],
                confidence=r[2],
                lon=r[3],
                lat=r[4],
                crop_url=f"/api/crops/{r[0]}" if r[5] else None,
                needs_review=r[6],
                source_value=r[7],
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
    feature = session.get(Feature, payload.feature_id)
    # Labelling another organisation's feature would write into their training
    # data, so an out-of-scope feature is simply not there.
    if feature is None or not same_org(user, feature.run):
        raise HTTPException(status_code=404, detail="feature not found")

    session.add(
        Label(
            feature_id=feature.id,
            class_name=payload.class_name,
            labelled_by_id=user.id,
        )
    )
    feature.class_name = payload.class_name
    feature.needs_review = False
    session.commit()
    return {"status": "ok"}
