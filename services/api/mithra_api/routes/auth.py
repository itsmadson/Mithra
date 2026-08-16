"""Feature-up, feature-in, feature-out, and account administration."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from mithra_api.auth import (
    current_admin,
    current_user,
    current_user_optional,
    end_session,
    has_any_user,
    start_session,
)
from mithra_api.audit import Action, record
from mithra_api.db import get_session
from mithra_api.models import Organisation, User, UserRole
from mithra_api.security import (
    WeakPassword,
    hash_password,
    needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class Registration(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=120)
    # Only meaningful on the very first registration, which creates the
    # organisation everyone else then joins.
    org_name: str = Field(default="", max_length=160)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    org_id: uuid.UUID | None
    org_name: str | None


def _out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        org_id=user.org_id,
        org_name=user.organisation.name if user.organisation else None,
    )


@router.get("/setup")
def setup_state(db: DbSession = Depends(get_session)) -> dict:
    """Whether the instance still needs its first account.

    The feature-in screen asks this so a fresh deployment offers to create the
    first administrator instead of showing a login nobody can pass.
    """
    return {"needs_setup": not has_any_user(db)}


@router.post("/register", status_code=201)
def register(
    payload: Registration,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_session),
) -> UserOut:
    """Create an account.

    Open only while no account exists — that first one becomes the
    administrator and is signed in immediately. Afterwards accounts are created
    by an administrator, because an internally-deployed survey tool with open
    registration is an unlocked door.
    """
    first_account = not has_any_user(db)
    admin = None
    org_id = None
    if first_account:
        # The first account brings its organisation into being. Everything
        # created afterwards belongs to it.
        org = Organisation(name=payload.org_name or payload.name or "Mithra")
        db.add(org)
        db.flush()
        org_id = org.id
    else:
        admin = current_admin(current_user(current_user_optional(request, db)))
        # An administrator can only add people to their own organisation.
        org_id = admin.org_id

    try:
        password_hash = hash_password(payload.password)
    except WeakPassword as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = User(
        email=payload.email.lower(),
        name=payload.name,
        password_hash=password_hash,
        role=UserRole.ADMIN if first_account else UserRole.OPERATOR,
        org_id=org_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="email already registered") from exc

    if first_account:
        start_session(db, user, response, request.headers.get("user-agent"))
        record(db, action=Action.LOGIN, actor=user, request=request)

    # The new account is the subject; the actor is whoever made it. For the
    # first account those are the same person, which is exactly what the log
    # should show.
    record(
        db,
        action=Action.ACCOUNT_CREATED,
        actor=user if first_account else admin,
        org_id=org_id,
        subject_type="user",
        subject_id=user.id,
        detail={"email": user.email, "role": user.role},
        request=request,
    )
    db.commit()
    return _out(user)


@router.post("/login")
def login(
    payload: Credentials,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_session),
) -> UserOut:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))

    # One message and one code for "no such account" and "wrong password":
    # distinguishing them tells an attacker which emails are registered.
    if user is None or not verify_password(user.password_hash, payload.password):
        # Recorded with the email that was tried, which is the whole point: a
        # run of failures against one address is the signal somebody is looking
        # for, and it cannot be reconstructed later.
        record(
            db,
            action=Action.LOGIN_FAILED,
            actor=user,
            actor_email=payload.email.lower(),
            org_id=user.org_id if user else None,
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="account disabled")

    # Transparent upgrade when the hashing parameters have moved on.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    start_session(db, user, response, request.headers.get("user-agent"))
    record(db, action=Action.LOGIN, actor=user, request=request)
    db.commit()
    return _out(user)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    # Resolved before the session is deleted: afterwards there is nobody to
    # name, and signing out is exactly the event worth naming.
    actor: User | None = Depends(current_user_optional),
    db: DbSession = Depends(get_session),
) -> None:
    end_session(db, request, response)
    if actor is not None:
        record(db, action=Action.LOGOUT, actor=actor, request=request)
        db.commit()


@router.get("/me")
def me(user: User = Depends(current_user)) -> UserOut:
    return _out(user)


@router.get("/users")
def list_users(
    _: User = Depends(current_admin), db: DbSession = Depends(get_session)
) -> dict:
    """Only this organisation's people."""
    users = db.scalars(
        select(User).where(User.org_id == _.org_id).order_by(User.created_at)
    ).all()
    return {"items": [_out(u) for u in users]}


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.patch("/users/{user_id}")
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    admin: User = Depends(current_admin),
    db: DbSession = Depends(get_session),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None or user.org_id != admin.org_id:
        raise HTTPException(status_code=404, detail="user not found")

    # An administrator locking themselves out is a support call, not a feature.
    if user.id == admin.id:
        if payload.is_active is False:
            raise HTTPException(status_code=422, detail="cannot disable your own account")
        if payload.role is not None and payload.role != UserRole.ADMIN:
            raise HTTPException(status_code=422, detail="cannot demote your own account")

    # Recorded as before-and-after, because "role changed" without the values
    # answers none of the questions anyone asks a log.
    changes: dict[str, dict[str, object]] = {}
    if payload.role is not None:
        if payload.role not in (UserRole.ADMIN, UserRole.OPERATOR):
            raise HTTPException(status_code=422, detail="unknown role")
        if payload.role != user.role:
            changes["role"] = {"from": user.role, "to": payload.role}
        user.role = payload.role
    if payload.is_active is not None:
        if payload.is_active != user.is_active:
            changes["is_active"] = {"from": user.is_active, "to": payload.is_active}
        user.is_active = payload.is_active

    if changes:
        record(
            db,
            action=Action.ACCOUNT_UPDATED,
            actor=admin,
            subject_type="user",
            subject_id=user.id,
            detail={"email": user.email, "changes": changes},
            request=request,
        )
    db.commit()
    return _out(user)
