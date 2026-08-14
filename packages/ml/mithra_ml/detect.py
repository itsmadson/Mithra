"""The interface every raster detector answers.

The street-level classifier answered "what is this crop?". A raster detector
answers a different question — "where in this image is X?" — and returns
geometry rather than a label, so it needs its own contract rather than a
widening of the old one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Detection:
    """One thing found in one chip.

    `geometry` is GeoJSON in EPSG:4326 — a Polygon for anything with an
    outline, a Point for anything that is only a location. The detector decides
    which, because it is the thing that knows whether it found an extent or a
    position.
    """

    class_name: str
    geometry: dict
    confidence: float
    area_m2: float | None = None
    properties: dict = field(default_factory=dict)


class RasterDetector(Protocol):
    """A model that finds targets in overhead imagery."""

    key: str
    version: str
    targets: frozenset[str]

    def detect(self, chip, targets: list[str]) -> list[Detection]: ...
