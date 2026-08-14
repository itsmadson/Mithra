"""What this deployment can detect, and on what.

The console asks this before it offers anything, so a user is never shown a
target the chosen imagery cannot deliver. The refusals carry their reason and,
where one exists, the coarser question that can be answered instead.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from mithra_api.auth import current_user
from mithra_ml.catalog import (
    DETECTORS,
    TARGETS,
    TARGETS_BY_KEY,
    catalogue_for,
)
from mithra_worker.sources import SOURCES, SOURCES_BY_KEY, resolve_gsd

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("")
def catalog(_user=Depends(current_user)) -> dict:
    """Every imagery source and every target this build knows about."""
    return {
        "sources": [
            {
                "key": s.key,
                "label_en": s.label_en,
                "label_fa": s.label_fa,
                "kind": s.kind.value,
                "gsd_m": s.gsd_m,
                "viewpoint": s.viewpoint,
                "licence": s.licence,
                "bulk_use": s.bulk_use.value,
                "needs_credentials": s.needs_credentials,
                "notes_en": s.notes_en,
            }
            for s in SOURCES
        ],
        "targets": [
            {
                "key": t.key,
                "label_en": t.label_en,
                "label_fa": t.label_fa,
                "geometry": t.geometry.value,
                "min_gsd_m": t.min_gsd_m,
                "viewpoints": sorted(t.viewpoints),
                "coarser_alternative": t.coarser_alternative,
                "notes_en": t.notes_en,
            }
            for t in TARGETS
        ],
        "detectors": [
            {
                "key": d.key,
                "label": d.label,
                "targets": sorted(d.targets),
                "open_vocabulary": d.open_vocabulary,
                "needs_gpu": d.needs_gpu,
                "notes": d.notes,
            }
            for d in DETECTORS
        ],
    }


@router.get("/availability")
def availability_for_source(
    source: str = Query(description="an imagery source key"),
    gsd_m: float | None = Query(default=None, description="resolution, when the file reports it"),
    _user=Depends(current_user),
) -> dict:
    """What can be detected on one source, with a reason for everything that cannot.

    This is the endpoint that keeps the product honest: the console calls it
    before showing the target picker, so an impossible pairing is refused at
    the point of choosing rather than after an hour of compute.
    """
    imagery = SOURCES_BY_KEY.get(source)
    if imagery is None:
        raise HTTPException(status_code=404, detail="unknown imagery source")

    resolved = resolve_gsd(source, gsd_m)
    items = catalogue_for(resolved, imagery.viewpoint)

    return {
        "source": source,
        "gsd_m": resolved,
        "viewpoint": imagery.viewpoint,
        "bulk_use": imagery.bulk_use.value,
        "targets": [
            {
                "key": a.target,
                "label_en": TARGETS_BY_KEY[a.target].label_en,
                "label_fa": TARGETS_BY_KEY[a.target].label_fa,
                "available": a.available,
                "reason": a.reason,
                "alternative": a.alternative,
                "detectors": list(a.detectors),
            }
            for a in items
        ],
    }
