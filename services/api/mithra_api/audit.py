"""Recording what happened, at the moment it happens.

One function, called from the routes that change something. It is deliberately
not middleware: middleware can see that a request arrived and what it returned,
but not which run it created or which class an operator overrode the model with,
and the detail is the entire value of the record.

Failures here never fail the request. An audit write that can break a survey
turns a log into an availability risk, and an organisation that cannot start a
run because the audit table is full is worse off than one with a gap in its log
— but the gap is reported to the application log, so it is not silent either.
"""

from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.orm import Session

from mithra_api.models import AuditEvent, User

log = logging.getLogger(__name__)


class Action:
    """The verbs worth recording.

    Reads are not here. Recording every list request would bury the four events
    somebody actually comes looking for under a million rows of routine traffic,
    and the questions an audit log is kept for are all about changes.
    """

    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    ACCOUNT_CREATED = "account.created"
    ACCOUNT_UPDATED = "account.updated"
    RUN_CREATED = "run.created"
    RUN_DELETED = "run.deleted"
    FEATURE_LABELLED = "feature.labelled"
    BASEMAP_CREATED = "basemap.created"
    BASEMAP_DELETED = "basemap.deleted"
    EXPORTED = "inventory.exported"


def client_ip(request: Request | None) -> str | None:
    """The caller's address, honouring one proxy hop.

    X-Forwarded-For is trivially forged by the client, so it is only trusted for
    its first entry and only because this service is expected to sit behind a
    reverse proxy that sets it. It is recorded as evidence, never used to decide
    anything.
    """
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host[:45] if request.client else None


def record(
    session: Session,
    *,
    action: str,
    actor: User | None = None,
    actor_email: str | None = None,
    org_id=None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    detail: dict | None = None,
    request: Request | None = None,
) -> None:
    """Append one event. Never raises."""
    try:
        email = actor_email or (actor.email if actor else "anonymous")
        session.add(
            AuditEvent(
                org_id=org_id if org_id is not None else (actor.org_id if actor else None),
                actor_id=actor.id if actor else None,
                actor_email=email,
                action=action,
                subject_type=subject_type,
                subject_id=str(subject_id) if subject_id is not None else None,
                detail=detail,
                ip=client_ip(request),
            )
        )
        session.flush()
    except Exception:  # pragma: no cover - the whole point is that it cannot fail
        log.exception("could not record audit event %s", action)
