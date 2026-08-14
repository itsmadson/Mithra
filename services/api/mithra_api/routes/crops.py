import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org
from mithra_api.db import get_session
from mithra_api.models import Feature, User

router = APIRouter(prefix="/api/crops", tags=["crops"])


@router.get("/{feature_id}")
def get_crop(
    feature_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    feature = session.get(Feature, feature_id)
    # A crop from another organisation is treated as missing, not forbidden.
    if feature is not None and not same_org(user, feature.run):
        feature = None
    if feature is None or not feature.crop_path or not Path(feature.crop_path).exists():
        raise HTTPException(status_code=404, detail="crop not found")
    return FileResponse(feature.crop_path, media_type="image/jpeg")
