import uuid

from pydantic import BaseModel, Field, model_validator

MAX_JOB_SIDE_DEGREES = 0.5  # ~55 km; a whole-city box, not a whole-country one


class JobCreate(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _check(self) -> "JobCreate":
        west, south, east, north = self.bbox
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


class JobStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    reason: str | None
    # The requested area, so a client can frame the map on it without a second
    # round trip and can show what was surveyed even when nothing was found.
    bbox: list[float]
    tile_count: int
    failed_tile_count: int
    counts: dict[str, int]
    total: int
    failed_count: int


class SignOut(BaseModel):
    id: uuid.UUID
    sign_class: str
    confidence: float
    lon: float
    lat: float
    crop_url: str | None
    needs_review: bool
    mapillary_value: str | None
    # Provenance: which Mapillary image this sign was cropped from, and which
    # model version produced the class. Without these a count cannot be audited.
    image_id: str | None = None
    model_version: str | None = None
    reason: str | None = None


class SignList(BaseModel):
    items: list[SignOut]
