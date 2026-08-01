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
    sign_class: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
