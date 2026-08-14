"""What can be detected, and on what imagery.

The catalogue exists because detection has a physical floor that no model
clears: an object smaller than a few pixels is not in the image to be found.
A tree crown is roughly 6 m across, so on Sentinel-2's 10 m pixels it is one
pixel — no detector, at any accuracy, can outline it there.

So the question "what can I detect?" has no fixed answer. It depends on the
imagery, and the honest interface refuses the impossible combination up front
with the reason and an alternative, rather than running for an hour and
returning an empty layer that reads as "there are no trees here".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Viewpoint(str, Enum):
    """Where the camera is.

    Resolution alone does not decide detectability. Street-level panoramas are
    sharp — centimetres per pixel — and still cannot see a lake's extent or a
    field boundary, because those are answered from above. Overhead imagery is
    the reverse: it never sees the face of a road sign, at any resolution.
    """

    OVERHEAD = "overhead"
    STREET = "street"


class Geometry(str, Enum):
    """What shape a detection of this target takes."""

    POINT = "point"
    POLYGON = "polygon"


@dataclass(frozen=True)
class Target:
    """Something a user can ask to find.

    `min_gsd_m` is the coarsest ground sample distance at which this target is
    still individually detectable — the largest metres-per-pixel that leaves
    enough pixels on the object to outline it. Smaller number, sharper imagery
    required.
    """

    key: str
    label_en: str
    label_fa: str
    geometry: Geometry
    min_gsd_m: float
    # Which camera positions can see this at all.
    viewpoints: frozenset[str] = frozenset({Viewpoint.OVERHEAD.value})
    # What to offer instead when the imagery is too coarse. A user who wants
    # "trees" on Sentinel-2 usually still has a question worth answering, and
    # "forest cover" answers it at that resolution.
    coarser_alternative: str | None = None
    notes_en: str = ""


# Ordered roughly by how sharp the imagery has to be.
TARGETS: tuple[Target, ...] = (
    Target(
        key="car",
        label_en="Vehicle",
        label_fa="خودرو",
        geometry=Geometry.POINT,
        min_gsd_m=0.3,
        viewpoints=frozenset({Viewpoint.OVERHEAD.value, Viewpoint.STREET.value}),
        notes_en="A car is about 4 m long; below 0.3 m/px counting degrades quickly.",
    ),
    Target(
        key="solar_panel",
        label_en="Solar panel",
        label_fa="پنل خورشیدی",
        geometry=Geometry.POLYGON,
        min_gsd_m=0.3,
    ),
    Target(
        key="sign",
        label_en="Road sign",
        label_fa="تابلوی راه",
        geometry=Geometry.POINT,
        min_gsd_m=0.1,
        viewpoints=frozenset({Viewpoint.STREET.value}),
        notes_en="A sign face is invisible from above, at any resolution.",
    ),
    Target(
        key="tree",
        label_en="Tree",
        label_fa="درخت",
        geometry=Geometry.POLYGON,
        min_gsd_m=1.0,
        viewpoints=frozenset({Viewpoint.OVERHEAD.value, Viewpoint.STREET.value}),
        coarser_alternative="forest_cover",
        notes_en="Individual crowns. Needs aerial or very-high-resolution satellite imagery.",
    ),
    Target(
        key="building",
        label_en="Building",
        label_fa="ساختمان",
        geometry=Geometry.POLYGON,
        min_gsd_m=1.0,
        viewpoints=frozenset({Viewpoint.OVERHEAD.value, Viewpoint.STREET.value}),
        coarser_alternative="built_up",
    ),
    Target(
        key="ship",
        label_en="Ship",
        label_fa="شناور",
        geometry=Geometry.POINT,
        min_gsd_m=1.0,
    ),
    Target(
        key="road",
        label_en="Road",
        label_fa="راه",
        geometry=Geometry.POLYGON,
        min_gsd_m=2.0,
    ),
    Target(
        key="built_up",
        label_en="Built-up area",
        label_fa="محدودهٔ ساخته‌شده",
        geometry=Geometry.POLYGON,
        min_gsd_m=10.0,
        notes_en="Where settlement is, not which buildings.",
    ),
    Target(
        key="forest_cover",
        label_en="Forest cover",
        label_fa="پوشش جنگلی",
        geometry=Geometry.POLYGON,
        min_gsd_m=10.0,
        notes_en="Canopy extent rather than individual trees.",
    ),
    Target(
        key="water",
        label_en="Water",
        label_fa="پهنهٔ آبی",
        geometry=Geometry.POLYGON,
        min_gsd_m=10.0,
        notes_en="Lakes, rivers, coastline, flood extent.",
    ),
    Target(
        key="cropland",
        label_en="Cropland",
        label_fa="زمین کشاورزی",
        geometry=Geometry.POLYGON,
        min_gsd_m=10.0,
    ),
)

TARGETS_BY_KEY: dict[str, Target] = {t.key: t for t in TARGETS}


@dataclass(frozen=True)
class Detector:
    """A model that can find some of the targets.

    Declaring the supported set per detector is what lets the product answer
    "can you find X here" without running anything, and what keeps an accuracy
    claim attached to the model that earned it rather than to the product.
    """

    key: str
    label: str
    targets: frozenset[str]
    # Some detectors are open-vocabulary: they accept a text prompt for a
    # target nobody enumerated. That is a capability, not a guarantee, so it is
    # declared rather than assumed.
    open_vocabulary: bool = False
    needs_gpu: bool = False
    # Where the weights come from, so a deployment can audit its licences.
    weights: str = ""
    notes: str = ""


DETECTORS: tuple[Detector, ...] = (
    Detector(
        key="clip-zeroshot",
        label="CLIP zero-shot (street-level signs)",
        targets=frozenset({"sign"}),
        weights="laion2b ViT-B-32",
        notes="The classifier the product started with. Street imagery only.",
    ),
    Detector(
        key="sam3",
        label="SAM 3 (open vocabulary)",
        targets=frozenset(
            {"tree", "building", "water", "road", "car", "ship", "solar_panel",
             "forest_cover", "built_up", "cropland"}
        ),
        open_vocabulary=True,
        needs_gpu=True,
        weights="Meta SAM 3",
        notes="Text prompt in, polygons out, no training. 86.9 IoU buildings on WHU-Aerial.",
    ),
    Detector(
        key="deepforest",
        label="DeepForest (tree crowns)",
        targets=frozenset({"tree"}),
        weights="DeepForest NEON release",
        notes="Purpose-trained on crowns; ~64-70% on the NEON benchmark.",
    ),
    Detector(
        key="omniwatermask",
        label="OmniWaterMask (water and flood)",
        targets=frozenset({"water"}),
        notes="Works at Sentinel-2 resolution, unlike most instance detectors.",
    ),
)

DETECTORS_BY_KEY: dict[str, Detector] = {d.key: d for d in DETECTORS}


@dataclass(frozen=True)
class Availability:
    """Whether one target can be detected on one source, and why not."""

    target: str
    available: bool
    reason: str = ""
    alternative: str | None = None
    detectors: tuple[str, ...] = field(default_factory=tuple)


def detectors_for(target_key: str) -> tuple[str, ...]:
    return tuple(d.key for d in DETECTORS if target_key in d.targets)


def availability(
    target_key: str,
    gsd_m: float | None,
    viewpoint: str = Viewpoint.OVERHEAD.value,
) -> Availability:
    """Can this target be found on this imagery?

    Three independent gates, in the order a person would ask them: is the
    camera in a position to see it at all, is there a model for it, and are
    there enough pixels on it.

    An unknown GSD is treated as unknown rather than as permission: a source
    that cannot say how sharp it is cannot be used to promise a detection.
    """
    target = TARGETS_BY_KEY.get(target_key)
    if target is None:
        return Availability(target_key, False, reason="unknown target")

    if viewpoint not in target.viewpoints:
        seen_from = " and ".join(sorted(target.viewpoints))
        return Availability(
            target_key,
            False,
            reason=f"not visible from {viewpoint} imagery; this is seen from {seen_from}",
        )

    detectors = detectors_for(target_key)
    if not detectors:
        return Availability(target_key, False, reason="no detector supports this target")

    if gsd_m is None:
        return Availability(
            target_key,
            False,
            reason="this imagery does not report its resolution",
            detectors=detectors,
        )

    if gsd_m > target.min_gsd_m:
        alternative = target.coarser_alternative
        reason = (
            f"needs imagery of {target.min_gsd_m:g} m/pixel or sharper; "
            f"this source is {gsd_m:g} m/pixel"
        )
        return Availability(target_key, False, reason=reason, alternative=alternative,
                            detectors=detectors)

    return Availability(target_key, True, detectors=detectors)


def catalogue_for(
    gsd_m: float | None, viewpoint: str = Viewpoint.OVERHEAD.value
) -> list[Availability]:
    """Every target, with a verdict, for one imagery source."""
    return [availability(t.key, gsd_m, viewpoint) for t in TARGETS]
