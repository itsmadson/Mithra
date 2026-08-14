"""Everything the dashboard needs, in one scoped request.

One endpoint rather than six: the dashboard is a single view of a single
moment, and six independent requests would let its panels disagree with each
other while they land. Every figure is computed in SQL and filtered to the
caller's organisation.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, visible_jobs
from mithra_api.db import get_session
from geoalchemy2 import Geography

from mithra_api.models import Run, RunStatus, Label, Feature, FeatureReason, User

router = APIRouter(prefix="/api/overview", tags=["overview"])

# Confidence below this is what "needs review" means to the pipeline. Repeated
# here so the histogram's threshold marker matches the queue the operator sees.
REVIEW_THRESHOLD = 0.55

# Imported rather than restated: if training's minimum moves, the progress the
# dashboard reports moves with it.
try:
    from mithra_ml import SIGN_CLASSES as TRAINABLE_CLASSES
    from mithra_ml.probe import MIN_PER_CLASS
except ImportError:  # pragma: no cover - the API can run without the ml package
    TRAINABLE_CLASSES = ("direction_guide", "street_name", "city_entry", "informational")
    MIN_PER_CLASS = 25


def _day_series(rows: Sequence, days: int) -> list[dict]:
    """Fill the gaps.

    A day with no surveys must appear as zero rather than be missing, or the
    chart draws a straight line through a quiet week and hides it.
    """
    found = {row[0]: row[1] for row in rows}
    today = datetime.now(UTC).date()
    return [
        {
            "date": (day := today - timedelta(days=offset)).isoformat(),
            "count": found.get(day, 0),
        }
        for offset in range(days - 1, -1, -1)
    ]


@router.get("")
def overview(
    days: int = Query(default=30, ge=7, le=180),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict:
    mine = visible_jobs(user)
    since = datetime.now(UTC) - timedelta(days=days)

    by_class = dict(
        session.execute(
            select(Feature.class_name, func.count())
            .where(Feature.run_id.in_(mine))
            .group_by(Feature.class_name)
        ).all()
    )
    by_status = dict(
        session.execute(
            select(Run.status, func.count()).where(Run.id.in_(mine)).group_by(Run.status)
        ).all()
    )

    total_signs = sum(by_class.values())
    needs_review = (
        session.scalar(
            select(func.count())
            .select_from(Feature)
            .where(Feature.run_id.in_(mine), Feature.needs_review.is_(True))
        )
        or 0
    )

    # Signs found per day. The pipeline's output over time is the one number
    # that says whether the tool is being used.
    features_per_day = _day_series(
        session.execute(
            select(func.date(Feature.created_at), func.count())
            .where(Feature.run_id.in_(mine), Feature.created_at >= since)
            .group_by(func.date(Feature.created_at))
            .order_by(func.date(Feature.created_at))
        ).all(),
        days,
    )
    labels_per_day = _day_series(
        session.execute(
            select(func.date(Label.created_at), func.count())
            .join(Feature, Feature.id == Label.feature_id)
            .where(Feature.run_id.in_(mine), Label.created_at >= since)
            .group_by(func.date(Label.created_at))
            .order_by(func.date(Label.created_at))
        ).all(),
        days,
    )

    # Confidence distribution in ten buckets. This is the classifier's own
    # report card: a pile against the low end means the model is guessing, and
    # that is a decision to retrain, not a number to celebrate.
    # Labelled once and grouped by the label: Postgres will not group by a
    # repeated expression, and repeating it would risk the two drifting apart.
    bucket = func.width_bucket(cast(Feature.confidence, Float), 0.0, 1.0, 10).label("bucket")
    confidence = dict(
        session.execute(
            select(bucket, func.count())
            .where(Feature.run_id.in_(mine))
            .group_by(bucket)
        ).all()
    )
    confidence_buckets = [
        {
            "from": round(i / 10, 1),
            "to": round((i + 1) / 10, 1),
            # width_bucket is 1-indexed; bucket 11 is exactly 1.0, which belongs
            # in the top bucket rather than in one of its own.
            "count": confidence.get(i + 1, 0) + (confidence.get(11, 0) if i == 9 else 0),
        }
        for i in range(10)
    ]

    # The surveys that found the most, so an operator can see which streets are
    # carrying the inventory and which produced nothing.
    top_surveys = [
        {
            "id": str(row[0]),
            "name": row[1],
            "total": row[2],
            "needs_review": row[3],
            "status": row[4],
        }
        for row in session.execute(
            select(
                Run.id,
                Run.name,
                func.count(Feature.id),
                func.count(case((Feature.needs_review.is_(True), 1))),
                Run.status,
            )
            .join(Feature, Feature.run_id == Run.id)
            .where(Run.id.in_(mine))
            .group_by(Run.id, Run.name, Run.status)
            .order_by(func.count(Feature.id).desc())
            .limit(8)
        ).all()
    ]

    recent = [
        {
            "id": str(row[0]),
            "name": row[1],
            "status": row[2],
            "reason": row[3],
            "kind": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "total": row[6],
        }
        for row in session.execute(
            select(
                Run.id,
                Run.name,
                Run.status,
                Run.reason,
                Run.kind,
                Run.created_at,
                func.count(Feature.id),
            )
            .outerjoin(Feature, Feature.run_id == Run.id)
            .where(Run.id.in_(mine))
            .group_by(Run.id)
            .order_by(Run.created_at.desc())
            .limit(6)
        ).all()
    ]

    # What the runs covered, and what they read. At one survey these are
    # trivia; at a thousand they are the first questions asked — comparing two
    # runs by raw count says nothing unless they covered comparable ground.
    by_source = dict(
        session.execute(
            select(Run.source_kind, func.count())
            .where(Run.id.in_(mine))
            .group_by(Run.source_kind)
        ).all()
    )
    by_detector = dict(
        session.execute(
            select(Run.detector, func.count()).where(Run.id.in_(mine)).group_by(Run.detector)
        ).all()
    )
    # Area covered, computed on the geography type so it comes back in metres
    # on the ellipsoid — degrees squared is not an area.
    area_m2 = (
        session.scalar(
            select(
                func.sum(
                    func.ST_Area(
                        func.ST_MakeEnvelope(
                            Run.bbox_west, Run.bbox_south, Run.bbox_east, Run.bbox_north, 4326
                        ).cast(Geography)
                    )
                )
            ).where(Run.id.in_(mine))
        )
        or 0.0
    )
    # Mapped extent of everything with an outline: the answer for a water or
    # canopy run, where "how many" is the wrong question.
    mapped_m2 = (
        session.scalar(select(func.sum(Feature.area_m2)).where(Feature.run_id.in_(mine)))
        or 0.0
    )

    failed_signs = (
        session.scalar(
            select(func.count())
            .select_from(Feature)
            .where(Feature.run_id.in_(mine), Feature.reason != FeatureReason.OK)
        )
        or 0
    )
    # Labels per class, against what training needs. A queue that fills without
    # ever reaching a trainable set is a treadmill, and the operator doing the
    # labelling is the person who deserves to see the distance left.
    labels_by_class = dict(
        session.execute(
            select(Label.class_name, func.count())
            .join(Feature, Feature.id == Label.feature_id)
            .where(Feature.run_id.in_(mine))
            .group_by(Label.class_name)
        ).all()
    )

    labels_total = (
        session.scalar(
            select(func.count())
            .select_from(Label)
            .join(Feature, Feature.id == Label.feature_id)
            .where(Feature.run_id.in_(mine))
        )
        or 0
    )

    return {
        "org": {"id": str(user.org_id) if user.org_id else None},
        "features": {
            "total": total_signs,
            "by_class": by_class,
            "needs_review": needs_review,
            "failed": failed_signs,
            # Share of features the pipeline was confident enough to keep. This is
            # the headline quality number, and it is deliberately not rounded up.
            "confident_share": (
                round((total_signs - needs_review) / total_signs * 100, 1)
                if total_signs
                else 0.0
            ),
        },
        "surveys": {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "running": by_status.get(RunStatus.RUNNING, 0) + by_status.get(RunStatus.QUEUED, 0),
            "failed": by_status.get(RunStatus.FAILED, 0),
        },
        "labels": {
            "total": labels_total,
            "per_day": labels_per_day,
            "by_class": labels_by_class,
            "needed_per_class": MIN_PER_CLASS,
            # The classes still short of a trainable count, and by how much.
            "short_by": {
                cls: MIN_PER_CLASS - labels_by_class.get(cls, 0)
                for cls in TRAINABLE_CLASSES
                if labels_by_class.get(cls, 0) < MIN_PER_CLASS
            },
        },
        "coverage": {
            "area_km2": round(area_m2 / 1_000_000, 2),
            "mapped_km2": round(mapped_m2 / 1_000_000, 4),
            "per_km2": (
                round(total_signs / (area_m2 / 1_000_000), 1) if area_m2 else 0.0
            ),
        },
        "sources": by_source,
        "detectors": by_detector,
        "activity": {"features_per_day": features_per_day, "days": days},
        "confidence": {"buckets": confidence_buckets, "threshold": REVIEW_THRESHOLD},
        "top_surveys": top_surveys,
        "recent": recent,
    }
