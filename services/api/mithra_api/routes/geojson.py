"""GeoJSON the map consumes directly.

The same FeatureCollection the browser renders is the one the export writes and
the one any GIS client can pull. Property names match the CSV columns, so a
feature has one description across the whole system rather than one per consumer.

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

from mithra_api.auth import current_user, same_org
from mithra_api.db import get_session
from mithra_api.models import Run, Feature, User

router = APIRouter(prefix="/api/runs", tags=["features"])


@router.get("/{run_id}/features.geojson")
def features(
    run_id: uuid.UUID,
    class_name: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> JSONResponse:
    job = session.get(Run, run_id)
    if job is None or not same_org(user, job):
        raise HTTPException(status_code=404, detail="job not found")

    statement = select(
        Feature.id,
        ST_AsGeoJSON(Feature.geom),
        Feature.class_name,
        Feature.confidence,
        Feature.needs_review,
        Feature.source_value,
        Feature.image_id,
        Feature.model_version,
        Feature.reason,
        Feature.crop_path,
    ).where(Feature.run_id == run_id)

    if class_name is not None:
        statement = statement.where(Feature.class_name == class_name)
    if needs_review is not None:
        statement = statement.where(Feature.needs_review.is_(needs_review))

    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": str(row[0]),
                "geometry": json.loads(row[1]),
                "properties": {
                    "id": str(row[0]),
                    "class_name": row[2],
                    "confidence": round(row[3], 4),
                    "needs_review": row[4],
                    "source_value": row[5],
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
