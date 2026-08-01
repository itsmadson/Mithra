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

from bina_api.auth import current_user, visible_jobs
from bina_api.db import get_session
from bina_api.models import Job, JobStatus, Label, Sign, SignReason, User

router = APIRouter(prefix="/api/overview", tags=["overview"])

# Confidence below this is what "needs review" means to the pipeline. Repeated
# here so the histogram's threshold marker matches the queue the operator sees.
REVIEW_THRESHOLD = 0.55

# Imported rather than restated: if training's minimum moves, the progress the
# dashboard reports moves with it.
try:
    from bina_ml import SIGN_CLASSES as TRAINABLE_CLASSES
    from bina_ml.probe import MIN_PER_CLASS
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
            select(Sign.sign_class, func.count())
            .where(Sign.job_id.in_(mine))
            .group_by(Sign.sign_class)
        ).all()
    )
    by_status = dict(
        session.execute(
            select(Job.status, func.count()).where(Job.id.in_(mine)).group_by(Job.status)
        ).all()
    )

    total_signs = sum(by_class.values())
    needs_review = (
        session.scalar(
            select(func.count())
            .select_from(Sign)
            .where(Sign.job_id.in_(mine), Sign.needs_review.is_(True))
        )
        or 0
    )

    # Signs found per day. The pipeline's output over time is the one number
    # that says whether the tool is being used.
    signs_per_day = _day_series(
        session.execute(
            select(func.date(Sign.created_at), func.count())
            .where(Sign.job_id.in_(mine), Sign.created_at >= since)
            .group_by(func.date(Sign.created_at))
            .order_by(func.date(Sign.created_at))
        ).all(),
        days,
    )
    labels_per_day = _day_series(
        session.execute(
            select(func.date(Label.created_at), func.count())
            .join(Sign, Sign.id == Label.sign_id)
            .where(Sign.job_id.in_(mine), Label.created_at >= since)
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
    bucket = func.width_bucket(cast(Sign.confidence, Float), 0.0, 1.0, 10).label("bucket")
    confidence = dict(
        session.execute(
            select(bucket, func.count())
            .where(Sign.job_id.in_(mine))
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
                Job.id,
                Job.name,
                func.count(Sign.id),
                func.count(case((Sign.needs_review.is_(True), 1))),
                Job.status,
            )
            .join(Sign, Sign.job_id == Job.id)
            .where(Job.id.in_(mine))
            .group_by(Job.id, Job.name, Job.status)
            .order_by(func.count(Sign.id).desc())
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
                Job.id,
                Job.name,
                Job.status,
                Job.reason,
                Job.kind,
                Job.created_at,
                func.count(Sign.id),
            )
            .outerjoin(Sign, Sign.job_id == Job.id)
            .where(Job.id.in_(mine))
            .group_by(Job.id)
            .order_by(Job.created_at.desc())
            .limit(6)
        ).all()
    ]

    failed_signs = (
        session.scalar(
            select(func.count())
            .select_from(Sign)
            .where(Sign.job_id.in_(mine), Sign.reason != SignReason.OK)
        )
        or 0
    )
    # Labels per class, against what training needs. A queue that fills without
    # ever reaching a trainable set is a treadmill, and the operator doing the
    # labelling is the person who deserves to see the distance left.
    labels_by_class = dict(
        session.execute(
            select(Label.sign_class, func.count())
            .join(Sign, Sign.id == Label.sign_id)
            .where(Sign.job_id.in_(mine))
            .group_by(Label.sign_class)
        ).all()
    )

    labels_total = (
        session.scalar(
            select(func.count())
            .select_from(Label)
            .join(Sign, Sign.id == Label.sign_id)
            .where(Sign.job_id.in_(mine))
        )
        or 0
    )

    return {
        "org": {"id": str(user.org_id) if user.org_id else None},
        "signs": {
            "total": total_signs,
            "by_class": by_class,
            "needs_review": needs_review,
            "failed": failed_signs,
            # Share of signs the pipeline was confident enough to keep. This is
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
            "running": by_status.get(JobStatus.RUNNING, 0) + by_status.get(JobStatus.QUEUED, 0),
            "failed": by_status.get(JobStatus.FAILED, 0),
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
        "activity": {"signs_per_day": signs_per_day, "days": days},
        "confidence": {"buckets": confidence_buckets, "threshold": REVIEW_THRESHOLD},
        "top_surveys": top_surveys,
        "recent": recent,
    }
