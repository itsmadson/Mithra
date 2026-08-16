"""Reading the audit log.

Administrators only, and only their own organisation's events. Read-only by
construction: there is no route here that writes, updates or deletes, because a
log the people it describes can edit answers a different question than the one
it is kept for.
"""


from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from mithra_api.auth import current_admin
from mithra_api.db import get_session
from mithra_api.models import AuditEvent, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_events(
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    admin: User = Depends(current_admin),
) -> dict:
    """The log, newest first.

    Scoped to the administrator's own organisation. Events recorded before
    organisations existed, or by an anonymous caller, have no org and are not
    shown to anyone — they belong to the deployment, not to a tenant.
    """
    statement = select(AuditEvent).where(AuditEvent.org_id == admin.org_id)

    if action:
        statement = statement.where(AuditEvent.action == action)
    if actor:
        statement = statement.where(AuditEvent.actor_email == actor)
    if q:
        like = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                AuditEvent.actor_email.ilike(like),
                AuditEvent.action.ilike(like),
                AuditEvent.subject_id.ilike(like),
            )
        )

    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(
        statement.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    ).all()

    return {
        "total": total,
        "items": [
            {
                "id": str(row.id),
                "action": row.action,
                "actor_email": row.actor_email,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "detail": row.detail,
                "ip": row.ip,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/actions")
def actions(
    session: Session = Depends(get_session),
    admin: User = Depends(current_admin),
) -> dict:
    """Which actions actually occur here, with counts.

    The filter offers what the log contains rather than every verb the code can
    emit, so an empty option is never offered.
    """
    rows = session.execute(
        select(AuditEvent.action, func.count())
        .where(AuditEvent.org_id == admin.org_id)
        .group_by(AuditEvent.action)
        .order_by(func.count().desc())
    ).all()
    actors = session.execute(
        select(AuditEvent.actor_email, func.count())
        .where(AuditEvent.org_id == admin.org_id)
        .group_by(AuditEvent.actor_email)
        .order_by(func.count().desc())
    ).all()
    return {
        "actions": [{"key": key, "count": count} for key, count in rows],
        "actors": [{"key": key, "count": count} for key, count in actors],
    }
