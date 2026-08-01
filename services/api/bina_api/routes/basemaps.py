"""Tile sources an organisation has added.

A sign inventory is read against a map, and the map a municipality trusts is
often its own: a cadastral layer, an aerial survey, a plan that was never
published to the world. This lets them point the console at it.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from bina_api.auth import current_admin, current_user
from bina_api.db import get_session
from bina_api.models import Basemap, User

router = APIRouter(prefix="/api/basemaps", tags=["basemaps"])

# An XYZ template must place all three coordinates, or every tile request
# resolves to the same image and the map silently repeats one square.
REQUIRED_PLACEHOLDERS = ("{z}", "{x}", "{y}")


class BasemapIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url_template: str = Field(min_length=10, max_length=600)
    attribution: str = Field(default="", max_length=300)
    tint: bool = False
    is_default: bool = False


class BasemapOut(BaseModel):
    id: uuid.UUID
    name: str
    url_template: str
    attribution: str
    tint: bool
    is_default: bool


def _out(row: Basemap) -> BasemapOut:
    return BasemapOut(
        id=row.id,
        name=row.name,
        url_template=row.url_template,
        attribution=row.attribution,
        tint=row.tint,
        is_default=row.is_default,
    )


def _validate(url: str) -> None:
    missing = [p for p in REQUIRED_PLACEHOLDERS if p not in url]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"tile URL must contain {', '.join(missing)}",
        )
    if not re.match(r"^https?://", url):
        raise HTTPException(status_code=422, detail="tile URL must start with http:// or https://")


@router.get("")
def list_basemaps(
    session: Session = Depends(get_session), user: User = Depends(current_user)
) -> dict:
    rows = session.scalars(
        select(Basemap).where(Basemap.org_id == user.org_id).order_by(Basemap.created_at)
    ).all()
    return {"items": [_out(r) for r in rows]}


@router.post("", status_code=201)
def create_basemap(
    payload: BasemapIn,
    session: Session = Depends(get_session),
    admin: User = Depends(current_admin),
) -> BasemapOut:
    """Adding a basemap changes what every operator sees, so it is an admin action."""
    _validate(payload.url_template)

    row = Basemap(
        org_id=admin.org_id,
        name=payload.name,
        url_template=payload.url_template,
        attribution=payload.attribution,
        tint=payload.tint,
        is_default=payload.is_default,
    )
    session.add(row)
    session.flush()
    if payload.is_default:
        _clear_other_defaults(session, admin, row.id)
    session.commit()
    return _out(row)


def _clear_other_defaults(session: Session, user: User, keep: uuid.UUID) -> None:
    """Exactly one default per organisation, or the map has to guess."""
    session.execute(
        update(Basemap)
        .where(Basemap.org_id == user.org_id, Basemap.id != keep)
        .values(is_default=False)
    )


class BasemapUpdate(BaseModel):
    is_default: bool | None = None
    name: str | None = Field(default=None, max_length=120)
    tint: bool | None = None


@router.patch("/{basemap_id}")
def update_basemap(
    basemap_id: uuid.UUID,
    payload: BasemapUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(current_admin),
) -> BasemapOut:
    row = session.get(Basemap, basemap_id)
    if row is None or row.org_id != admin.org_id:
        raise HTTPException(status_code=404, detail="basemap not found")

    if payload.name is not None:
        row.name = payload.name
    if payload.tint is not None:
        row.tint = payload.tint
    if payload.is_default is not None:
        row.is_default = payload.is_default
        if payload.is_default:
            _clear_other_defaults(session, admin, row.id)

    session.commit()
    return _out(row)


@router.delete("/{basemap_id}", status_code=204)
def delete_basemap(
    basemap_id: uuid.UUID,
    session: Session = Depends(get_session),
    admin: User = Depends(current_admin),
) -> None:
    row = session.get(Basemap, basemap_id)
    if row is None or row.org_id != admin.org_id:
        raise HTTPException(status_code=404, detail="basemap not found")
    # Nothing to reassign: the built-in OpenStreetMap basemap is always
    # available and is what the map falls back to.
    session.delete(row)
    session.commit()
