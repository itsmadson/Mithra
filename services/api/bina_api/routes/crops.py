import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from bina_api.auth import current_user
from bina_api.db import get_session
from bina_api.models import Sign

router = APIRouter(prefix="/api/crops", tags=["crops"])


@router.get("/{sign_id}")
def get_crop(
    sign_id: uuid.UUID, session: Session = Depends(get_session)
) -> FileResponse:
    sign = session.get(Sign, sign_id)
    if sign is None or not sign.crop_path or not Path(sign.crop_path).exists():
        raise HTTPException(status_code=404, detail="crop not found")
    return FileResponse(sign.crop_path, media_type="image/jpeg")
