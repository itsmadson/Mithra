import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

MAX_JOB_SIDE_DEGREES = 0.5  # ~55 km; a whole-city box, not a whole-country one
MAX_BUFFER_M = 200


class JobCreate(BaseModel):
    """A survey is defined either by a street or by a rectangle.

    The street is the primary path — an operator surveys a معبر, not an abstract
    box — but the rectangle stays supported for areas with no OSM way, such as a
    new development or a square.
    """

    name: str | None = Field(default=None, max_length=200)

    # Street survey.
    osm_id: int | None = None
    street_name: str | None = Field(default=None, max_length=200)
    lat: float | None = None
    lon: float | None = None
    buffer_m: int = Field(default=25, ge=5, le=MAX_BUFFER_M)

    # Rectangle survey.
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def _check(self) -> "JobCreate":
        is_street = self.osm_id is not None or self.street_name is not None
        if is_street == (self.bbox is not None):
            raise ValueError("provide either a street or a bbox, not both and not neither")

        if is_street:
            if self.lat is None or self.lon is None:
                raise ValueError("a street survey needs lat and lon to anchor the search")
            if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
                raise ValueError("lat/lon out of range")
            return self

        west, south, east, north = self.bbox  # type: ignore[misc]
        if not (-180 <= west < east <= 180):
            raise ValueError("longitudes must satisfy -180 <= west < east <= 180")
        if not (-90 <= south < north <= 90):
            raise ValueError("latitudes must satisfy -90 <= south < north <= 90")
        if (east - west) > MAX_JOB_SIDE_DEGREES or (north - south) > MAX_JOB_SIDE_DEGREES:
            raise ValueError(f"bbox side must not exceed {MAX_JOB_SIDE_DEGREES} degrees")
        return self


class JobCreated(BaseModel):
    id: uuid.UUID
    status: str


class JobSummary(BaseModel):
    """One row in the survey list."""

    id: uuid.UUID
    name: str
    kind: str
    status: str
    reason: str | None
    total: int
    failed_count: int
    tile_count: int
    failed_tile_count: int
    created_at: datetime
    finished_at: datetime | None


class JobList(BaseModel):
    items: list[JobSummary]
    total: int


class RunStatusOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    status: str
    reason: str | None
    # The requested area, so a client can frame the map on it without a second
    # round trip and can show what was surveyed even when nothing was found.
    bbox: list[float]
    # Street surveys also carry the centreline they followed, as GeoJSON.
    geometry: dict | None = None
    buffer_m: int
    osm_id: int | None
    tile_count: int
    failed_tile_count: int
    counts: dict[str, int]
    total: int
    failed_count: int
    created_at: datetime
    finished_at: datetime | None


class SignOut(BaseModel):
    id: uuid.UUID
    class_name: str
    confidence: float
    lon: float
    lat: float
    crop_url: str | None
    needs_review: bool
    source_value: str | None
    # Provenance: which Mapillary image this feature was cropped from, and which
    # model version produced the class. Without these a count cannot be audited.
    image_id: str | None = None
    model_version: str | None = None
    reason: str | None = None


class SignList(BaseModel):
    items: list[SignOut]
