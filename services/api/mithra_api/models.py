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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mithra_api.db import Base


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

    An operator runs surveys and labels features. An admin additionally manages
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


class Basemap(Base):
    """A tile source an organisation has added.

    Municipalities run their own tile servers — a cadastral layer, an aerial
    survey, a plan not published to the world — and a feature inventory is read
    against the map the organisation already trusts. Stored per organisation
    because a tile URL can carry an access key in its path.
    """

    __tablename__ = "basemaps"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # An XYZ template: .../{z}/{x}/{y}.png
    url_template: Mapped[str] = mapped_column(String(600))
    attribution: Mapped[str] = mapped_column(String(300), default="")
    # Whether tiles should be recoloured to match the console's theme. An
    # aerial photo must not be desaturated; a street map usually should be.
    tint: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RunKind:
    """How the area of interest was chosen."""

    BBOX = "bbox"
    STREET = "street"
    POLYGON = "polygon"


class RunStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class FeatureReason:
    OK = "ok"
    CROP_FAILED = "crop_failed"
    NO_DETECTION = "no_detection"
    CLASSIFY_FAILED = "classify_failed"


class RunReason:
    NO_IMAGERY = "no_imagery"
    AUTH_FAILED = "auth_failed"
    ENQUEUE_FAILED = "enqueue_failed"
    WORKER_ERROR = "worker_error"
    STREET_NOT_FOUND = "street_not_found"


class Run(Base):
    """One detection run: an area, an imagery source, and what to look for.

    This was a "job" that only ever meant "survey a street with Mapillary".
    It carries the source and the targets now, because the same area can be
    run against Sentinel-2 for water and against aerial imagery for trees, and
    those are different runs with different answers — not one survey.
    """

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # A survey has a name because a list of UUIDs is not a dashboard. For a
    # street survey this is the street; for a bbox it is generated from the
    # coordinates.
    name: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(16), default=RunKind.BBOX, index=True)

    # Which imagery this run read, and how to read it. The config is opaque
    # here on purpose: an XYZ template, a STAC collection and date window, or
    # an uploaded file id are different shapes, and the source adapter owns
    # their meaning.
    source_kind: Mapped[str] = mapped_column(String(24), default="mapillary", index=True)
    source_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Metres per pixel the run actually worked at. Stored rather than derived,
    # because it decides what the counts can be trusted to mean and the source
    # may change under the same key later.
    gsd_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # What was asked for, and which model answered.
    targets: Mapped[list] = mapped_column(JSONB, default=list)
    detector: Mapped[str] = mapped_column(String(40), default="clip-zeroshot")

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

    status: Mapped[str] = mapped_column(String(16), default=RunStatus.QUEUED, index=True)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tile_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_tile_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    features: Mapped[list["Feature"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    tiles: Mapped[list["RunTile"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunTile(Base):
    __tablename__ = "run_tiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    west: Mapped[float] = mapped_column(Float)
    south: Mapped[float] = mapped_column(Float)
    east: Mapped[float] = mapped_column(Float)
    north: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.QUEUED)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    run: Mapped[Run] = relationship(back_populates="tiles")


class Feature(Base):
    """One detected thing.

    Was a Feature. It holds a lake, a tree crown or a car now, so the class is
    free text from the catalogue rather than an enum, and the geometry is a
    point OR a polygon: a feature is a location, a lake is an outline, and
    forcing either into the other's shape loses the answer.
    """

    __tablename__ = "features"
    __table_args__ = (
        UniqueConstraint("run_id", "source_feature_id", name="uq_feature_per_run"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    # Whatever the source calls this detection: a Mapillary feature id, a tile
    # and instance index, a row in an uploaded raster's output. Unique per run,
    # so re-running cannot double-count.
    source_feature_id: Mapped[str] = mapped_column(String(120), index=True)
    image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # GEOMETRY rather than POINT: a detection is a location or an outline
    # depending on what was detected.
    geom: Mapped[str] = mapped_column(Geometry("GEOMETRY", srid=4326))
    class_name: Mapped[str] = mapped_column(String(64), index=True)
    # Square metres, for anything with an outline. A lake's area is the answer
    # the question was asking for; a count of lakes is not.
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(80))
    source_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    crop_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(32), default=FeatureReason.OK)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped[Run] = relationship(back_populates="features")


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), index=True
    )
    # Who judged it. Training data without provenance cannot be audited when a
    # model trained on it turns out to be biased towards one labeller's habits.
    labelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    class_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
