"""System-wide totals for the dashboard.

Deliberately computed in SQL rather than by walking surveys in Python: the
numbers must stay correct as the survey count grows, and a dashboard that gets
slower the more work you have done is a dashboard people stop opening.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user
from mithra_api.db import get_session
from mithra_api.models import Run, RunStatus, Label, Feature, FeatureReason

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats(
    session: Session = Depends(get_session), _user=Depends(current_user)
) -> dict:
    counts = dict(
        session.execute(select(Feature.class_name, func.count()).group_by(Feature.class_name)).all()
    )
    by_status = dict(
        session.execute(select(Run.status, func.count()).group_by(Run.status)).all()
    )

    model_versions = [
        row[0]
        for row in session.execute(
            select(Feature.model_version, func.count())
            .group_by(Feature.model_version)
            .order_by(func.count().desc())
        ).all()
        if row[0]
    ]

    return {
        "surveys": {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "running": by_status.get(RunStatus.RUNNING, 0)
            + by_status.get(RunStatus.QUEUED, 0),
        },
        "features": {
            "total": sum(counts.values()),
            "by_class": counts,
            "needs_review": session.scalar(
                select(func.count()).select_from(Feature).where(Feature.needs_review.is_(True))
            )
            or 0,
            "unclassified": session.scalar(
                select(func.count())
                .select_from(Feature)
                .where(Feature.reason != FeatureReason.OK)
            )
            or 0,
        },
        "labels": {
            "total": session.scalar(select(func.count()).select_from(Label)) or 0
        },
        "models": model_versions,
    }
