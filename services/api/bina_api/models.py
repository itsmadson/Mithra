import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bina_api.db import Base


class Organisation(Base):
    """A municipality, a contractor, a department.

    Surveys belong to an organisation rather than to the person who ran them,
    because the work outlives the employee: staff change, and the inventory a
    city paid for must not leave with them.
    """

    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="organisation")


class UserRole:
    """Two roles is all the product distinguishes today.

    An operator runs surveys and labels signs. An admin additionally manages
    accounts. Anything finer would be invented rather than observed.
    """

    ADMIN = "admin"
    OPERATOR = "operator"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=UserRole.OPERATOR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    organisation: Mapped[Organisation | None] = relationship(back_populates="users")


class Session(Base):
    """A logged-in browser.

    Only the hash of the token is stored, so a database dump does not hand over
    live sessions, and deleting the row genuinely ends the session — which is
    the property a signed stateless token cannot offer.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class JobKind:
    """How the surveyed area was chosen."""

    BBOX = "bbox"
    STREET = "street"


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class SignReason:
    OK = "ok"
    CROP_FAILED = "crop_failed"
    NO_DETECTION = "no_detection"
    CLASSIFY_FAILED = "classify_failed"


class JobReason:
    NO_IMAGERY = "no_imagery"
    AUTH_FAILED = "auth_failed"
    ENQUEUE_FAILED = "enqueue_failed"
    WORKER_ERROR = "worker_error"
    STREET_NOT_FOUND = "street_not_found"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # A survey has a name because a list of UUIDs is not a dashboard. For a
    # street survey this is the street; for a bbox it is generated from the
    # coordinates.
    name: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(16), default=JobKind.BBOX, index=True)

    # Nullable because surveys created before accounts existed have no owner.
    # Backfilling them to an arbitrary account would be a lie about who ran them.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Who the survey belongs to. This is the tenancy boundary: every read is
    # filtered by it, so one organisation never sees another's inventory.
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # The bbox is always populated, including for street surveys, where it is
    # the extent of the buffered corridor. It is what the map frames on.
    bbox_west: Mapped[float] = mapped_column(Float)
    bbox_south: Mapped[float] = mapped_column(Float)
    bbox_east: Mapped[float] = mapped_column(Float)
    bbox_north: Mapped[float] = mapped_column(Float)

    # Street surveys keep the centreline they followed and how wide a corridor
    # counted as "on this street", so a count can be re-checked against the
    # exact geometry that produced it.
    osm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    buffer_m: Mapped[int] = mapped_column(Integer, default=25)
    geom: Mapped[str | None] = mapped_column(
        Geometry("MULTILINESTRING", srid=4326), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, index=True)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tile_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_tile_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    signs: Mapped[list["Sign"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    tiles: Mapped[list["JobTile"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobTile(Base):
    __tablename__ = "job_tiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    west: Mapped[float] = mapped_column(Float)
    south: Mapped[float] = mapped_column(Float)
    east: Mapped[float] = mapped_column(Float)
    north: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    job: Mapped[Job] = relationship(back_populates="tiles")


class Sign(Base):
    __tablename__ = "signs"
    __table_args__ = (
        UniqueConstraint("job_id", "mapillary_feature_id", name="uq_sign_per_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    mapillary_feature_id: Mapped[str] = mapped_column(String(64), index=True)
    image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geom: Mapped[str] = mapped_column(Geometry("POINT", srid=4326))
    sign_class: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(80))
    mapillary_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    crop_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(32), default=SignReason.OK)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="signs")


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signs.id", ondelete="CASCADE"), index=True
    )
    # Who judged it. Training data without provenance cannot be audited when a
    # model trained on it turns out to be biased towards one labeller's habits.
    labelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sign_class: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
