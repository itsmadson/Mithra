"""Running a detection over satellite or aerial imagery.

The street pipeline walks a corridor and classifies crops. This one reads a
window of overhead imagery and asks a detector where things are. They share
the run record, the review queue and the audit trail; they do not share a code
path, because "walk a street" and "read a raster" are genuinely different jobs
and pretending otherwise would make both harder to follow.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from mithra_ml.catalog import availability
from mithra_worker.imagery import (
    Chip,
    ImageryError,
    read_cog,
    read_stac_scene,
    read_upload,
    search_stac,
)
from mithra_worker.sources import SOURCES_BY_KEY, resolve_gsd

# Which STAC collection each registered source reads, and the bands a detector
# needs from it. Kept here rather than in the source registry because it is
# pipeline knowledge, not a fact about the imagery.
STAC_COLLECTIONS = {"sentinel2": "sentinel-2-l2a", "naip": "naip"}
# NDWI needs green and near-infrared, in that order.
WATER_BANDS = ("green", "nir")


class RunRefused(RuntimeError):
    """The run cannot produce an honest answer, and says why before starting."""


def check_targets(source_key: str, targets: list[str], gsd_m: float | None) -> None:
    """Refuse impossible work up front.

    The catalogue already knows whether a target is findable on a source.
    Calling it here means an impossible run fails in milliseconds with a
    reason, rather than after an hour with an empty layer that reads as
    "there is none of that here".
    """
    source = SOURCES_BY_KEY.get(source_key)
    if source is None:
        raise RunRefused(f"unknown imagery source {source_key!r}")

    resolved = resolve_gsd(source_key, gsd_m)
    for target in targets:
        verdict = availability(target, resolved, source.viewpoint)
        if not verdict.available:
            hint = f"; try {verdict.alternative} instead" if verdict.alternative else ""
            raise RunRefused(f"cannot detect {target} on {source_key}: {verdict.reason}{hint}")


def fetch_chip(source_key: str, config: dict, bbox: tuple, bands: tuple[str, ...] = WATER_BANDS,
               max_size: int = 1024) -> tuple[Chip, dict]:
    """Get pixels for an area, whatever the source is.

    Returns the chip and a provenance record — which scene, which date, how
    cloudy — because a count that cannot name the image it came from is not
    auditable.
    """
    source = SOURCES_BY_KEY.get(source_key)
    if source is None:
        raise ImageryError(f"unknown imagery source {source_key!r}")

    if source.kind.value == "stac":
        collection = STAC_COLLECTIONS.get(source_key)
        if collection is None:
            raise ImageryError(f"no STAC collection registered for {source_key}")

        end = config.get("end") or datetime.now(UTC).date().isoformat()
        start = config.get("start") or (
            datetime.fromisoformat(end) - timedelta(days=60)
        ).date().isoformat()

        scenes = search_stac(
            collection, bbox, start, end,
            max_cloud=int(config.get("max_cloud", 20)),
        )
        if not scenes:
            raise ImageryError(
                f"no {source_key} scene under {config.get('max_cloud', 20)}% cloud "
                f"between {start} and {end}"
            )
        scene = scenes[0]
        chip = read_stac_scene(scene, bbox, bands=bands, max_size=max_size)
        return chip, {
            "scene_id": scene["id"],
            "captured": scene["datetime"],
            "cloud_cover": scene["cloud_cover"],
            "collection": collection,
        }

    if source.kind.value == "cog":
        url = config.get("url")
        if not url:
            raise ImageryError("a COG source needs a url")
        return read_cog(url, bbox, max_size=max_size), {"url": url}

    if source.kind.value == "upload":
        path = config.get("path")
        if not path:
            raise ImageryError("an upload source needs a stored path")
        return read_upload(path, bbox, max_size=max_size), {"path": path}

    raise ImageryError(f"{source_key} cannot be read as a raster")


def detector_for(key: str):
    """The detector a run asked for, or a reason it is not available here."""
    if key == "ndwi-water":
        from mithra_ml.water import NdwiWaterDetector

        return NdwiWaterDetector()

    raise RunRefused(
        f"detector {key!r} is declared in the catalogue but not implemented in this build"
    )


def detect_over_area(
    source_key: str, config: dict, bbox: tuple, targets: list[str], detector_key: str,
    max_size: int = 1024,
):
    """The whole raster path: refuse, fetch, detect, report.

    Returns the detections and the provenance of the imagery they came from.
    """
    check_targets(source_key, targets, config.get("gsd_m"))
    chip, provenance = fetch_chip(source_key, config, bbox, max_size=max_size)
    detections = detector_for(detector_key).detect(chip, targets)
    provenance["gsd_m"] = round(chip.gsd_m, 2)
    provenance["pixels"] = [chip.width, chip.height]
    return detections, provenance


def geometry_to_wkt_element(geometry: dict) -> str:
    """GeoJSON to something PostGIS accepts, without a shapely round trip."""
    return f"SRID=4326;{json.dumps(geometry)}"
