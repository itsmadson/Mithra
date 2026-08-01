"""System-wide totals for the dashboard.

Deliberately computed in SQL rather than by walking surveys in Python: the
numbers must stay correct as the survey count grows, and a dashboard that gets
slower the more work you have done is a dashboard people stop opening.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bina_api.auth import current_user
from bina_api.db import get_session
from bina_api.models import Job, JobStatus, Label, Sign, SignReason

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats(
    session: Session = Depends(get_session), _user=Depends(current_user)
) -> dict:
    counts = dict(
        session.execute(select(Sign.sign_class, func.count()).group_by(Sign.sign_class)).all()
    )
    by_status = dict(
        session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )

    model_versions = [
        row[0]
        for row in session.execute(
            select(Sign.model_version, func.count())
            .group_by(Sign.model_version)
            .order_by(func.count().desc())
        ).all()
        if row[0]
    ]

    return {
        "surveys": {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "running": by_status.get(JobStatus.RUNNING, 0)
            + by_status.get(JobStatus.QUEUED, 0),
        },
        "signs": {
            "total": sum(counts.values()),
            "by_class": counts,
            "needs_review": session.scalar(
                select(func.count()).select_from(Sign).where(Sign.needs_review.is_(True))
            )
            or 0,
            "unclassified": session.scalar(
                select(func.count())
                .select_from(Sign)
                .where(Sign.reason != SignReason.OK)
            )
            or 0,
        },
        "labels": {
            "total": session.scalar(select(func.count()).select_from(Label)) or 0
        },
        "models": model_versions,
    }
