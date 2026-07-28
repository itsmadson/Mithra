import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.orm import Session

from bina_api.db import get_session
from bina_api.models import Job, Sign

router = APIRouter(prefix="/api/jobs", tags=["export"])

COLUMNS = [
    "id",
    "sign_class",
    "confidence",
    "lon",
    "lat",
    "mapillary_value",
    "needs_review",
]


def _rows(session: Session, job_id: uuid.UUID):
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return session.execute(
        select(
            Sign.id,
            Sign.sign_class,
            Sign.confidence,
            ST_X(Sign.geom),
            ST_Y(Sign.geom),
            Sign.mapillary_value,
            Sign.needs_review,
        ).where(Sign.job_id == job_id)
    ).all()


@router.get("/{job_id}/export.csv")
def export_csv(
    job_id: uuid.UUID, session: Session = Depends(get_session)
) -> StreamingResponse:
    rows = _rows(session, job_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [str(row[0]), row[1], f"{row[2]:.4f}", row[3], row[4], row[5] or "", row[6]]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="bina-{job_id}.csv"'},
    )


@router.get("/{job_id}/export.geojson")
def export_geojson(
    job_id: uuid.UUID, session: Session = Depends(get_session)
) -> JSONResponse:
    rows = _rows(session, job_id)
    return JSONResponse(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [row[3], row[4]]},
                    "properties": {
                        "id": str(row[0]),
                        "sign_class": row[1],
                        "confidence": row[2],
                        "mapillary_value": row[5],
                        "needs_review": row[6],
                    },
                }
                for row in rows
            ],
        },
        headers={"Content-Disposition": f'attachment; filename="bina-{job_id}.geojson"'},
    )
