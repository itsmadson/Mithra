import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org
from mithra_api.db import get_session
from mithra_api.models import Sign, User

router = APIRouter(prefix="/api/crops", tags=["crops"])


@router.get("/{sign_id}")
def get_crop(
    sign_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> FileResponse:
    sign = session.get(Sign, sign_id)
    # A crop from another organisation is treated as missing, not forbidden.
    if sign is not None and not same_org(user, sign.job):
        sign = None
    if sign is None or not sign.crop_path or not Path(sign.crop_path).exists():
        raise HTTPException(status_code=404, detail="crop not found")
    return FileResponse(sign.crop_path, media_type="image/jpeg")
