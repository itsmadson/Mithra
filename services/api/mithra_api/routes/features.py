import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org, visible_jobs
from mithra_api.db import get_session
from mithra_api.models import Run, Feature, User
from mithra_api.schemas import FeatureList, FeatureOut

router = APIRouter(prefix="/api/runs", tags=["features"])

# Cross-survey access. The per-survey routes above answer "what is on this
# street"; this one answers "what have we found anywhere", which is the
# question an inventory is actually for.
all_features = APIRouter(prefix="/api/features", tags=["features"])


@all_features.get("", response_model=FeatureList)
def list_all_features(
    class_name: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=500, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FeatureList:
    statement = select(
        Feature.id,
        Feature.class_name,
        Feature.confidence,
        ST_X(Feature.geom),
        ST_Y(Feature.geom),
        Feature.crop_path,
        Feature.needs_review,
        Feature.source_value,
        Feature.image_id,
        Feature.model_version,
        Feature.reason,
    ).where(Feature.run_id.in_(visible_jobs(user))).order_by(Feature.created_at.desc())

    if class_name is not None:
        statement = statement.where(Feature.class_name == class_name)
    if needs_review is not None:
        statement = statement.where(Feature.needs_review.is_(needs_review))

    return FeatureList(
        items=[
            FeatureOut(
                id=row[0],
                class_name=row[1],
                confidence=row[2],
                lon=row[3],
                lat=row[4],
                crop_url=f"/api/crops/{row[0]}" if row[5] else None,
                needs_review=row[6],
                source_value=row[7],
                image_id=row[8],
                model_version=row[9],
                reason=row[10],
            )
            for row in session.execute(statement.limit(limit).offset(offset)).all()
        ]
    )


@router.get("/{run_id}/features", response_model=FeatureList)
def list_signs(
    run_id: uuid.UUID,
    class_name: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=1000, le=5000),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FeatureList:
    job = session.get(Run, run_id)
    if job is None or not same_org(user, job):
        raise HTTPException(status_code=404, detail="job not found")

    statement = select(
        Feature.id,
        Feature.class_name,
        Feature.confidence,
        ST_X(Feature.geom),
        ST_Y(Feature.geom),
        Feature.crop_path,
        Feature.needs_review,
        Feature.source_value,
        Feature.image_id,
        Feature.model_version,
        Feature.reason,
    ).where(Feature.run_id == run_id)
    if class_name is not None:
        statement = statement.where(Feature.class_name == class_name)
    if needs_review is not None:
        statement = statement.where(Feature.needs_review.is_(needs_review))

    items = [
        FeatureOut(
            id=row[0],
            class_name=row[1],
            confidence=row[2],
            lon=row[3],
            lat=row[4],
            crop_url=f"/api/crops/{row[0]}" if row[5] else None,
            needs_review=row[6],
            source_value=row[7],
            image_id=row[8],
            model_version=row[9],
            reason=row[10],
        )
        for row in session.execute(statement.limit(limit)).all()
    ]
    return FeatureList(items=items)
