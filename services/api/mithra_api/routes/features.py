import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
# A detection may be a polygon now, and ST_X only accepts points. The
# list needs one location to show; the centroid is it. The map layer
# keeps the real outline, through the GeoJSON route.
from geoalchemy2.functions import ST_Centroid, ST_X, ST_Y
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org, visible_jobs
from mithra_api.db import get_session
from mithra_api.models import Run, Feature, User
from mithra_api.schemas import FacetCount, FeatureFacets, FeatureList, FeatureOut

router = APIRouter(prefix="/api/runs", tags=["features"])

# Cross-survey access. The per-survey routes above answer "what is on this
# street"; this one answers "what have we found anywhere", which is the
# question an inventory is actually for.
all_features = APIRouter(prefix="/api/features", tags=["features"])


# Which column a table header maps to. Sorting is whitelisted rather than
# interpolated: an ORDER BY built from a query string is how a filter becomes a
# database read of somebody else's data.
SORTABLE = {
    "created_at": Feature.created_at,
    "class_name": Feature.class_name,
    "confidence": Feature.confidence,
    "area_m2": Feature.area_m2,
}


def _filtered(user: User, params: dict):
    """The one place the inventory filter lives.

    The list and the facet counts must agree exactly — a filter panel that says
    "water 24" beside a table showing 19 rows is worse than no counts at all —
    so they are built from the same predicate rather than from two queries that
    look similar.
    """
    statement = select(Feature).join(Run, Feature.run_id == Run.id).where(
        Feature.run_id.in_(visible_jobs(user))
    )
    if params.get("class_name"):
        statement = statement.where(Feature.class_name.in_(params["class_name"]))
    if params.get("needs_review") is not None:
        statement = statement.where(Feature.needs_review.is_(params["needs_review"]))
    if params.get("run_id"):
        statement = statement.where(Feature.run_id == params["run_id"])
    if params.get("detector"):
        statement = statement.where(Run.detector == params["detector"])
    if params.get("min_confidence") is not None:
        statement = statement.where(Feature.confidence >= params["min_confidence"])
    if params.get("max_confidence") is not None:
        statement = statement.where(Feature.confidence <= params["max_confidence"])
    if params.get("q"):
        # Free text across the fields an operator would actually type into:
        # what it is, what it says, and the run it came from.
        like = f"%{params['q'].strip()}%"
        statement = statement.where(
            or_(
                Feature.class_name.ilike(like),
                Feature.source_value.ilike(like),
                Feature.image_id.ilike(like),
                Run.name.ilike(like),
            )
        )
    return statement


def _target(class_name: str):
    try:
        from mithra_ml.catalog import TARGETS_BY_KEY

        return TARGETS_BY_KEY.get(class_name)
    except ImportError:  # pragma: no cover - API served without the ml package
        return None


def _domain_of(class_name: str) -> str | None:
    target = _target(class_name)
    return target.domain.value if target and target.domain else None


def _labels_of(class_name: str) -> tuple[str | None, str | None]:
    """The catalogue's own names for a class, in both languages.

    Sent with every row because the console cannot derive them: a Persian
    operator reading "forest_cover" is reading a database key, and the
    catalogue has carried پوشش جنگلی for it the whole time.
    """
    target = _target(class_name)
    if target is None:
        return None, None
    return target.label_en, target.label_fa


@all_features.get("", response_model=FeatureList)
def list_all_features(
    class_name: list[str] | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    run_id: uuid.UUID | None = Query(default=None),
    detector: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    max_confidence: float | None = Query(default=None, ge=0, le=1),
    q: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="created_at"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=500, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FeatureList:
    """The inventory, filtered and paged on the server.

    Everything here used to happen in the browser over a fixed two thousand
    rows, which works until an organisation has more than two thousand
    detections — at which point the console silently stops showing some of
    them, which is the worst way for a tool like this to fail.
    """
    params = {
        "class_name": class_name,
        "needs_review": needs_review,
        "run_id": run_id,
        "detector": detector,
        "min_confidence": min_confidence,
        "max_confidence": max_confidence,
        "q": q,
    }
    base = _filtered(user, params)

    total = session.scalar(
        select(func.count()).select_from(base.subquery())
    )

    column = SORTABLE.get(sort, Feature.created_at)
    # Nulls last in both directions. Area is null for every point detection, and
    # Postgres puts nulls first on a descending sort — so "largest first" opened
    # on a page of blanks, which reads as a broken sort rather than as missing
    # data.
    order = column.desc().nullslast() if direction == "desc" else column.asc().nullslast()
    ordered = base.order_by(order)

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
            Feature.image_id,
            Feature.model_version,
            Feature.reason,
            Feature.area_m2,
            Feature.run_id,
            Run.name,
            Feature.created_at,
        )
        .select_from(Feature)
        .join(Run, Feature.run_id == Run.id)
        .where(Feature.id.in_(select(ordered.subquery().c.id)))
        .order_by(order)
        .limit(limit)
        .offset(offset)
    ).all()

    return FeatureList(
        total=total,
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
                area_m2=row[11],
                run_id=row[12],
                run_name=row[13],
                domain=_domain_of(row[1]),
                label_en=_labels_of(row[1])[0],
                label_fa=_labels_of(row[1])[1],
                created_at=row[14],
            )
            for row in rows
        ],
    )


@all_features.get("/facets", response_model=FeatureFacets)
def feature_facets(
    class_name: list[str] | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    run_id: uuid.UUID | None = Query(default=None),
    detector: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    max_confidence: float | None = Query(default=None, ge=0, le=1),
    q: str | None = Query(default=None, max_length=200),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FeatureFacets:
    """What is actually in the inventory right now, by class, run and model.

    Deliberately ignores the class filter when counting classes: a facet list
    that hid every option you had not already chosen would make it impossible
    to widen a search.
    """
    params = {
        "needs_review": needs_review,
        "run_id": run_id,
        "detector": detector,
        "min_confidence": min_confidence,
        "max_confidence": max_confidence,
        "q": q,
    }
    scoped = _filtered(user, params).subquery()

    def counts(column):
        return [
            FacetCount(key=str(key), count=count)
            for key, count in session.execute(
                select(column, func.count())
                .select_from(scoped)
                .group_by(column)
                .order_by(func.count().desc())
            ).all()
            if key is not None
        ]

    classes = [
        FacetCount(
            key=item.key,
            count=item.count,
            domain=_domain_of(item.key),
            label=_labels_of(item.key)[0],
            label_fa=_labels_of(item.key)[1],
        )
        for item in counts(scoped.c.class_name)
    ]
    domains: dict[str, int] = {}
    for item in classes:
        domain = _domain_of(item.key) or "other"
        domains[domain] = domains.get(domain, 0) + item.count

    runs = [
        FacetCount(key=str(run_id), label=name or None, count=count)
        for run_id, name, count in session.execute(
            select(scoped.c.run_id, Run.name, func.count())
            .select_from(scoped)
            .join(Run, Run.id == scoped.c.run_id)
            .group_by(scoped.c.run_id, Run.name)
            .order_by(func.count().desc())
        ).all()
    ]

    detectors = [
        FacetCount(key=str(key), count=count)
        for key, count in session.execute(
            select(Run.detector, func.count())
            .select_from(scoped)
            .join(Run, Run.id == scoped.c.run_id)
            .group_by(Run.detector)
            .order_by(func.count().desc())
        ).all()
        if key is not None
    ]

    total = session.scalar(select(func.count()).select_from(scoped)) or 0
    unsure = session.scalar(
        select(func.count()).select_from(scoped).where(scoped.c.needs_review.is_(True))
    ) or 0

    return FeatureFacets(
        classes=classes,
        domains=[FacetCount(key=k, count=v) for k, v in sorted(domains.items(), key=lambda kv: -kv[1])],
        runs=runs,
        detectors=detectors,
        total=total,
        needs_review=unsure,
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
        ST_X(ST_Centroid(Feature.geom)),
        ST_Y(ST_Centroid(Feature.geom)),
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


@all_features.get("/export.csv")
def export_inventory_csv(
    class_name: list[str] | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    run_id: uuid.UUID | None = Query(default=None),
    detector: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    max_confidence: float | None = Query(default=None, ge=0, le=1),
    q: str | None = Query(default=None, max_length=200),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> StreamingResponse:
    """The filtered inventory as CSV — what is on screen, not the whole table.

    An export that ignores the filters is a different dataset from the one the
    operator was looking at when they pressed the button, and they will not
    notice until it is in a report.
    """
    import csv
    import io

    params = {
        "class_name": class_name,
        "needs_review": needs_review,
        "run_id": run_id,
        "detector": detector,
        "min_confidence": min_confidence,
        "max_confidence": max_confidence,
        "q": q,
    }
    scoped = _filtered(user, params).subquery()

    rows = session.execute(
        select(
            scoped.c.id,
            scoped.c.class_name,
            scoped.c.confidence,
            ST_Y(ST_Centroid(scoped.c.geom)),
            ST_X(ST_Centroid(scoped.c.geom)),
            scoped.c.area_m2,
            scoped.c.needs_review,
            scoped.c.model_version,
            Run.name,
            scoped.c.created_at,
        )
        .select_from(scoped)
        .join(Run, Run.id == scoped.c.run_id)
        .order_by(scoped.c.created_at.desc())
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "class",
            "domain",
            "confidence",
            "lat",
            "lon",
            "area_m2",
            "needs_review",
            "model_version",
            "run",
            "detected_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                str(row[0]),
                row[1],
                _domain_of(row[1]) or "",
                f"{row[2]:.4f}",
                f"{row[3]:.6f}",
                f"{row[4]:.6f}",
                "" if row[5] is None else f"{row[5]:.1f}",
                "yes" if row[6] else "no",
                row[7] or "",
                row[8] or "",
                row[9].isoformat() if row[9] else "",
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mithra-inventory.csv"'},
    )
