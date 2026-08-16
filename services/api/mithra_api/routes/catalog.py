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
                "imagery_kind": s.imagery_kind,
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
                "runtime": d.runtime.value,
                "vram_gb": d.vram_gb,
                "implemented": d.implemented,
                # The evidence travels with the claim, so a chosen detector can
                # be justified rather than merely named.
                "benchmark": (
                    {
                        "metric": d.best_benchmark().metric,
                        "value": d.best_benchmark().value,
                        "dataset": d.best_benchmark().dataset,
                        "source": d.best_benchmark().source,
                    }
                    if d.best_benchmark()
                    else None
                ),
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


@router.get("/plan/{target_key}")
def plan_for_target(target_key: str, _user=Depends(current_user)) -> dict:
    """How this target would be detected here: sources, models, evidence.

    Answers the question a user actually has when they pick something from the
    list — from what imagery, by which model, and how well — before committing
    an hour of compute to finding out.
    """
    from mithra_ml.hardware import detection_plan

    plan = detection_plan(target_key)
    if not plan.get("known"):
        raise HTTPException(status_code=404, detail="unknown target")
    return plan


@router.get("/domains")
def domains(_user=Depends(current_user)) -> dict:
    """The taxonomy, grouped the way a person asks for it.

    Seventy targets as a flat list is a wall of nouns; grouped by the question
    they answer — cover, use, buildings, transport, condition — it is a menu.
    """
    from collections import defaultdict

    grouped: dict[str, list] = defaultdict(list)
    for target in TARGETS:
        grouped[target.domain.value if target.domain else "other"].append(
            {
                "key": target.key,
                "label_en": target.label_en,
                "label_fa": target.label_fa,
                "geometry": target.geometry.value,
                "min_gsd_m": target.min_gsd_m,
                "viewpoints": sorted(target.viewpoints),
            }
        )
    return {"domains": [{"key": k, "targets": v} for k, v in sorted(grouped.items())]}
