import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Query
# A detection may be a polygon now, and ST_X only accepts points. The
# list needs one location to show; the centroid is it. The map layer
# keeps the real outline, through the GeoJSON route.
from geoalchemy2.functions import ST_Centroid, ST_X, ST_Y
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org, visible_jobs
from mithra_api.audit import Action, record
from mithra_api.db import get_session
from mithra_api.models import Label, Feature, User
from mithra_api.schemas import FeatureList, FeatureOut
from mithra_ml import ALL_CLASSES

router = APIRouter(prefix="/api/labels", tags=["labels"])


def _labellable() -> frozenset[str]:
    """Every class a person may assign.

    Was the five sign classes, which quietly meant a misdetected lake could not
    be corrected to anything: the review queue holds land cover and tree crowns
    now, and a queue that can only answer in one taxonomy cannot judge them.
    The catalogue is the authority; the sign classes stay because they predate
    it and are still in the data.
    """
    try:
        from mithra_ml.catalog import TARGETS

        return frozenset(ALL_CLASSES) | frozenset(target.key for target in TARGETS)
    except ImportError:  # pragma: no cover - API served without the ml package
        return frozenset(ALL_CLASSES)


class LabelCreate(BaseModel):
    feature_id: uuid.UUID
    class_name: str

    @field_validator("class_name")
    @classmethod
    def _known_class(cls, v: str) -> str:
        if v not in _labellable():
            raise ValueError("class_name must be a class from the catalogue")
        return v


class BulkLabel(BaseModel):
    """One decision applied to many detections.

    A review queue that can only be answered one row at a time is not a review
    queue; it is four hundred forms. The cap is deliberate — a mistake applied
    to five hundred rows is a mistake somebody has to undo by hand.
    """

    feature_ids: list[uuid.UUID]
    class_name: str

    @field_validator("feature_ids")
    @classmethod
    def _not_too_many(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not v:
            raise ValueError("no detections given")
        if len(v) > 500:
            raise ValueError("at most 500 detections at a time")
        return v

    @field_validator("class_name")
    @classmethod
    def _known_class(cls, v: str) -> str:
        if v not in _labellable():
            raise ValueError("class_name must be a class from the catalogue")
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
            ST_X(ST_Centroid(Feature.geom)),
            ST_Y(ST_Centroid(Feature.geom)),
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
    request: Request,
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
    # A person overriding the model is the single event most worth keeping:
    # it is the moment the inventory stops being what the model said and starts
    # being what somebody decided, and the old class is not recoverable
    # afterwards because the row is overwritten in place.
    record(
        session,
        action=Action.FEATURE_LABELLED,
        actor=user,
        subject_type="feature",
        subject_id=feature.id,
        detail={
            "from": feature.class_name,
            "to": payload.class_name,
            "model_version": feature.model_version,
            "confidence": feature.confidence,
        },
        request=request,
    )

    feature.class_name = payload.class_name
    feature.needs_review = False
    session.commit()
    return {"status": "ok"}


@router.post("/bulk")
def create_labels(
    payload: BulkLabel,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict:
    """Apply one class to many detections.

    Out-of-scope ids are skipped rather than refused: a selection made against a
    list that has since changed should not fail wholesale, and the count that
    comes back says exactly how many were actually written — so the console can
    report "412 of 415" rather than implying it did them all.
    """
    features = session.scalars(
        select(Feature).where(
            Feature.id.in_(payload.feature_ids),
            Feature.run_id.in_(visible_jobs(user)),
        )
    ).all()

    changed = []
    for feature in features:
        if feature.class_name == payload.class_name and not feature.needs_review:
            continue
        changed.append({"id": str(feature.id), "from": feature.class_name})
        session.add(
            Label(
                feature_id=feature.id,
                class_name=payload.class_name,
                labelled_by_id=user.id,
            )
        )
        feature.class_name = payload.class_name
        feature.needs_review = False

    if changed:
        # One event for the batch, listing what it covered: five hundred
        # separate rows would bury every other event in the log.
        record(
            session,
            action=Action.FEATURE_LABELLED,
            actor=user,
            subject_type="feature",
            subject_id=f"{len(changed)} detections",
            detail={
                "to": payload.class_name,
                "count": len(changed),
                "requested": len(payload.feature_ids),
                "sample": changed[:10],
            },
            request=request,
        )

    session.commit()
    return {"labelled": len(changed), "requested": len(payload.feature_ids)}
