"""GeoJSON the map consumes directly.

The same FeatureCollection the browser renders is the one the export writes and
the one any GIS client can pull. Property names match the CSV columns, so a
sign has one description across the whole system rather than one per consumer.

This is deliberately a plain GeoJSON resource rather than a bespoke JSON shape:
it drops into QGIS, ogr2ogr, or a MapLibre source with no adapter.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.orm import Session

from bina_api.db import get_session
from bina_api.models import Job, Sign

router = APIRouter(prefix="/api/jobs", tags=["features"])


@router.get("/{job_id}/features")
def features(
    job_id: uuid.UUID,
    sign_class: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    session: Session = Depends(get_session),
) -> JSONResponse:
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    statement = select(
        Sign.id,
        ST_AsGeoJSON(Sign.geom),
        Sign.sign_class,
        Sign.confidence,
        Sign.needs_review,
        Sign.mapillary_value,
        Sign.image_id,
        Sign.model_version,
        Sign.reason,
        Sign.crop_path,
    ).where(Sign.job_id == job_id)

    if sign_class is not None:
        statement = statement.where(Sign.sign_class == sign_class)
    if needs_review is not None:
        statement = statement.where(Sign.needs_review.is_(needs_review))

    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": str(row[0]),
                "geometry": json.loads(row[1]),
                "properties": {
                    "id": str(row[0]),
                    "sign_class": row[2],
                    "confidence": round(row[3], 4),
                    "needs_review": row[4],
                    "mapillary_value": row[5],
                    "image_id": row[6],
                    "model_version": row[7],
                    "reason": row[8],
                    "crop_url": f"/api/crops/{row[0]}" if row[9] else None,
                },
            }
            for row in session.execute(statement).all()
        ],
    }
    return JSONResponse(collection, media_type="application/geo+json")
