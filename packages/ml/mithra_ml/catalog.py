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


class Runtime(str, Enum):
    """What a detector needs to run at a useful speed.

    This is not a footnote. The same product runs on a laptop and on a GPU
    server, and a detector that needs 8 GB of VRAM is not "slower" without one
    — it is unusable, and an operator who starts that run learns so an hour
    later. The registry declares it so the console can say it first.
    """

    CPU = "cpu"          # runs anywhere, seconds per tile
    CPU_SLOW = "cpu_slow"  # runs on CPU, minutes per tile — viable, not pleasant
    GPU = "gpu"          # needs a GPU to finish in reasonable time


@dataclass(frozen=True)
class Benchmark:
    """A published number, with what produced it.

    An accuracy without its dataset is marketing. Every figure here names the
    benchmark it came from so a claim can be checked, and so two detectors are
    only ever compared on the same one.
    """

    metric: str      # "IoU", "mAP", "F1", "accuracy"
    value: float     # 0-1
    dataset: str
    source: str = ""


@dataclass(frozen=True)
class Detector:
    """A model that can find some of the targets.

    Declaring the supported set, the hardware, and the evidence per detector is
    what lets the product answer "can you find X here, on this server, how
    well" without running anything — and keeps an accuracy claim attached to
    the model that earned it rather than to the product.
    """

    key: str
    label: str
    targets: frozenset[str]
    runtime: Runtime = Runtime.CPU
    # Rough working set. A model that needs more VRAM than the card has does
    # not run slower; it fails.
    vram_gb: float = 0.0
    ram_gb: float = 2.0
    open_vocabulary: bool = False
    weights: str = ""
    licence: str = ""
    benchmarks: tuple[Benchmark, ...] = ()
    implemented: bool = False
    notes: str = ""

    def best_benchmark(self) -> Benchmark | None:
        return self.benchmarks[0] if self.benchmarks else None


DETECTORS: tuple[Detector, ...] = (
    # --- implemented here ----------------------------------------------------
    Detector(
        key="ndwi-water",
        label="NDWI water index",
        targets=frozenset({"water"}),
        runtime=Runtime.CPU,
        ram_gb=1.0,
        weights="none - a spectral index, not a trained model",
        licence="public method (McFeeters 1996)",
        benchmarks=(
            Benchmark("accuracy", 0.95, "standard method for open water at 10 m",
                      "McFeeters 1996"),
        ),
        implemented=True,
        notes="Green and near-infrared bands. Works at Sentinel-2 resolution, needs no weights.",
    ),
    Detector(
        key="clip-zeroshot",
        label="CLIP zero-shot (street-level signs)",
        targets=frozenset({"sign"}),
        runtime=Runtime.CPU_SLOW,
        ram_gb=3.0,
        weights="laion2b ViT-B-32",
        licence="MIT",
        implemented=True,
        notes="The classifier this product started with. Street imagery only, and frequently wrong on regulatory signs.",
    ),
    # --- declared, and honest about needing a better server ------------------
    Detector(
        key="sam3",
        label="SAM 3 — open vocabulary",
        targets=frozenset(
            {"tree", "building", "water", "road", "car", "ship", "solar_panel",
             "forest_cover", "built_up", "cropland"}
        ),
        runtime=Runtime.GPU,
        vram_gb=8.0,
        ram_gb=16.0,
        open_vocabulary=True,
        weights="Meta SAM 3",
        licence="see Meta's SAM licence",
        implemented=True,
        benchmarks=(
            Benchmark("IoU", 0.869, "WHU-Aerial buildings", "SegEarth-OV3, arXiv 2512.08730"),
            Benchmark("IoU", 0.724, "Inria buildings", "SegEarth-OV3"),
        ),
        notes="Text prompt in, polygons out, no training. The only detector that answers a target nobody enumerated.",
    ),
    Detector(
        key="deepforest",
        label="DeepForest — tree crowns",
        targets=frozenset({"tree"}),
        runtime=Runtime.CPU_SLOW,
        ram_gb=4.0,
        weights="DeepForest NEON release",
        licence="MIT",
        benchmarks=(
            Benchmark("accuracy", 0.70, "NEON crowns", "Weinstein et al., PLOS Comp Biol"),
        ),
        notes="Purpose-trained on crowns from RGB. Needs sub-metre imagery.",
    ),
    Detector(
        key="tree-sam",
        label="Tree-SAM — crowns, cross-region",
        targets=frozenset({"tree"}),
        runtime=Runtime.GPU,
        vram_gb=6.0,
        ram_gb=12.0,
        weights="SAM backbone, tree-tuned head",
        benchmarks=(
            Benchmark("F1", 0.83, "GZ-Tree urban", "arXiv 2506.03114"),
            Benchmark("F1", 0.76, "GZ-Tree forest", "arXiv 2506.03114"),
        ),
        notes="Generalises off-nadir better than DeepForest; costs a GPU to do it.",
    ),
    Detector(
        key="omniwatermask",
        label="OmniWaterMask — water and flood",
        targets=frozenset({"water"}),
        runtime=Runtime.CPU_SLOW,
        ram_gb=6.0,
        licence="see project",
        notes="Learned water masking; more robust than an index on shadow and turbid water.",
    ),
    Detector(
        key="sam-road",
        label="SAM-Road — road graphs",
        targets=frozenset({"road"}),
        runtime=Runtime.GPU,
        vram_gb=8.0,
        ram_gb=16.0,
        weights="SAM backbone, road topology decoder",
        benchmarks=(
            Benchmark("APLS", 0.66, "City-scale / SpaceNet roads", "arXiv 2403.16051"),
        ),
        notes="Highest published APLS: clean graphs, few false connections, and it can miss thin roads.",
    ),
    Detector(
        key="dlinknet",
        label="D-LinkNet — road segmentation",
        targets=frozenset({"road"}),
        runtime=Runtime.GPU,
        vram_gb=4.0,
        ram_gb=8.0,
        weights="D-LinkNet DeepGlobe",
        licence="MIT",
        benchmarks=(
            Benchmark("IoU", 0.64, "DeepGlobe roads", "DeepGlobe challenge winner"),
        ),
        notes="The DeepGlobe champion. Pixels rather than a graph; cheaper than SAM-Road.",
    ),
    Detector(
        key="oriented-rcnn",
        label="Oriented R-CNN — vehicles, ships, aircraft",
        targets=frozenset({"car", "ship"}),
        runtime=Runtime.GPU,
        vram_gb=8.0,
        ram_gb=16.0,
        weights="DOTA-v2 / FAIR1M trained",
        benchmarks=(
            Benchmark("mAP", 0.577, "DOTA-v2.0 OBB", "DOTA benchmark, 2025 state of the art"),
        ),
        notes="Rotated boxes, which is what a ship or a parked car actually needs. Small objects demand 0.3 m imagery.",
    ),
    Detector(
        key="dynamic-world",
        label="Dynamic World — land cover",
        targets=frozenset({"forest_cover", "built_up", "cropland", "water"}),
        runtime=Runtime.CPU,
        ram_gb=4.0,
        weights="Google Dynamic World (inference on Sentinel-2)",
        licence="CC BY 4.0",
        benchmarks=(
            Benchmark("accuracy", 0.738, "global land cover validation",
                      "Brown et al., Scientific Data 2022"),
        ),
        notes="Nine classes at 10 m, near real time. Coarse by design: it answers where, not which.",
    ),
    Detector(
        key="solarnet",
        label="Rooftop solar detection",
        targets=frozenset({"solar_panel"}),
        runtime=Runtime.GPU,
        vram_gb=4.0,
        ram_gb=8.0,
        benchmarks=(
            Benchmark("F1", 0.85, "rooftop PV, aerial", "Can J Remote Sensing 2024"),
        ),
        notes="Accuracy drops sharply off the geography it was trained on; retrain before trusting a new city.",
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
