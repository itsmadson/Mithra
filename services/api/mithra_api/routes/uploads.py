"""Rasters an operator brings themselves.

Drone imagery, an orthophoto, a scene bought from a provider. The file decides
what can be detected on it, so it is read on arrival rather than trusted: its
resolution comes from the header, not from a form field, because a claimed
resolution would let a user unlock targets the pixels cannot support.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from mithra_api.auth import current_user
from mithra_api.config import get_settings
from mithra_api.db import get_session
from mithra_api.models import User

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

# Rasters are large, but not unbounded: a request that streams forever is a
# denial of service, and 2 GB already covers a city-sized orthophoto.
MAX_BYTES = 2 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024

ALLOWED_SUFFIXES = {".tif", ".tiff", ".jp2", ".png", ".jpg", ".jpeg"}


def upload_dir() -> Path:
    """Where uploads live: beside the crops, never inside the web root."""
    base = Path(get_settings().crop_dir).parent / "uploads"
    base.mkdir(parents=True, exist_ok=True)
    return base


@router.post("", status_code=201)
async def upload_raster(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict:
    """Store a raster and report what it can be used for.

    The response carries the file's own resolution and extent so the console
    can ask the catalogue what is detectable on it — the same question it asks
    of Sentinel-2, answered from the header instead of a registry.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported file type {suffix or '(none)'}; expected a GeoTIFF or JPEG2000",
        )

    # Namespaced by organisation: an upload is imagery someone paid for, and it
    # must not be readable across the tenancy boundary.
    target_dir = upload_dir() / str(user.org_id or "unscoped")
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = target_dir / f"{uuid.uuid4()}{suffix}"

    written = 0
    try:
        with stored.open("wb") as out:
            while chunk := await file.read(CHUNK):
                written += len(chunk)
                if written > MAX_BYTES:
                    raise HTTPException(status_code=413, detail="raster exceeds 2 GB")
                out.write(chunk)
    except HTTPException:
        stored.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"could not store upload: {exc}") from exc

    try:
        from rio_tiler.io import Reader

        with Reader(str(stored)) as image:
            info = image.info()
            bounds = list(info.bounds)
            # Ground resolution from the header. A file that cannot say is not
            # rejected — it simply unlocks nothing until someone tells us.
            width = info.width or 1
            from mithra_worker.imagery import metres_per_degree_lon

            mid_lat = (bounds[1] + bounds[3]) / 2
            width_m = (bounds[2] - bounds[0]) * metres_per_degree_lon(mid_lat)
            gsd_m = round(width_m / width, 3) if width else None
    except Exception as exc:  # noqa: BLE001
        stored.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=f"the file is not a readable georeferenced raster: {exc}",
        ) from exc

    return {
        "path": str(stored),
        "filename": file.filename,
        "bytes": written,
        "bounds": bounds,
        "gsd_m": gsd_m,
    }
