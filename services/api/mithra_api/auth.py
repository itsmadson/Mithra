"""Who is making this request.

Every dependency here fails closed: an absent, unknown, or expired session is
anonymous, and anonymous is refused by anything that is not explicitly public.
"""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from mithra_api.db import get_session
from mithra_api.models import Run, Organisation, Session, User, UserRole
from mithra_api.security import (
    SESSION_COOKIE,
    hash_session_token,
    new_session_token,
    session_expiry,
)


def start_session(db: DbSession, user: User, response: Response, user_agent: str | None) -> str:
    """Create a session and set its cookie. Returns the raw token, once."""
    token = new_session_token()
    db.add(
        Session(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=session_expiry(),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    user.last_login_at = datetime.now(UTC)
    db.commit()

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int((session_expiry() - datetime.now(UTC)).total_seconds()),
        httponly=True,  # JavaScript must not be able to read it
        samesite="lax",  # blocks cross-site form posts while keeping normal navigation
        secure=False,  # set True behind TLS; false here so localhost works
        path="/",
    )
    return token


def end_session(db: DbSession, request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(Session).where(Session.token_hash == hash_session_token(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


def current_user_optional(
    request: Request, db: DbSession = Depends(get_session)
) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    session = db.scalar(
        select(Session).where(Session.token_hash == hash_session_token(token))
    )
    if session is None:
        return None

    # Expiry is enforced here rather than only by a cleanup job, so a stale row
    # can never authenticate anyone.
    if session.expires_at <= datetime.now(UTC):
        db.delete(session)
        db.commit()
        return None

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    return user


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="administrator role required")
    return user


def has_any_user(db: DbSession) -> bool:
    """First-run detection, so the very first account can be created unauthenticated."""
    return db.scalar(select(User.id).limit(1)) is not None


def visible_jobs(user: User):
    """The job ids this user is allowed to see, as a subquery.

    Tenancy is enforced by filtering, not by trusting the caller to pass their
    own organisation id: a request that can name another organisation's survey
    still gets nothing back.

    Surveys with no organisation predate tenancy. They stay visible to everyone
    rather than disappearing, because hiding an existing inventory behind a
    migration would look like data loss; new surveys always carry an owner.
    """
    return select(Run.id).where(
        (Run.org_id == user.org_id) | (Run.org_id.is_(None))
    )


def same_org(user: User, job: Run) -> bool:
    return job.org_id is None or job.org_id == user.org_id
