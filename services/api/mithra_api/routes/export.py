import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
# A detection may be a polygon now, and ST_X only accepts points. The
# list needs one location to show; the centroid is it. The map layer
# keeps the real outline, through the GeoJSON route.
from geoalchemy2.functions import ST_Centroid, ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.orm import Session

from mithra_api.auth import current_user, same_org
from mithra_api.db import get_session
from mithra_api.models import Run, Feature, User

router = APIRouter(prefix="/api/runs", tags=["export"])

COLUMNS = [
    "id",
    "class_name",
    "confidence",
    "lon",
    "lat",
    "source_value",
    "needs_review",
]


def _rows(session: Session, run_id: uuid.UUID, user: User):
    job = session.get(Run, run_id)
    if job is None or not same_org(user, job):
        raise HTTPException(status_code=404, detail="job not found")
    return session.execute(
        select(
            Feature.id,
            Feature.class_name,
            Feature.confidence,
            ST_X(ST_Centroid(Feature.geom)),
            ST_Y(ST_Centroid(Feature.geom)),
            Feature.source_value,
            Feature.needs_review,
        ).where(Feature.run_id == run_id)
    ).all()


@router.get("/{run_id}/export.csv")
def export_csv(
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> StreamingResponse:
    rows = _rows(session, run_id, user)
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
        headers={"Content-Disposition": f'attachment; filename="mithra-{run_id}.csv"'},
    )


@router.get("/{run_id}/export.geojson")
def export_geojson(
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> JSONResponse:
    rows = _rows(session, run_id, user)
    return JSONResponse(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [row[3], row[4]]},
                    "properties": {
                        "id": str(row[0]),
                        "class_name": row[1],
                        "confidence": row[2],
                        "source_value": row[5],
                        "needs_review": row[6],
                    },
                }
                for row in rows
            ],
        },
        headers={"Content-Disposition": f'attachment; filename="mithra-{run_id}.geojson"'},
    )
