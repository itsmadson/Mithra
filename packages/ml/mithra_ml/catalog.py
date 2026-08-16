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
    domain: "Domain" = None  # type: ignore[assignment]
    # Which camera positions can see this at all.
    viewpoints: frozenset[str] = frozenset({Viewpoint.OVERHEAD.value})
    # What to offer instead when the imagery is too coarse. A user who wants
    # "trees" on Sentinel-2 usually still has a question worth answering, and
    # "forest cover" answers it at that resolution.
    coarser_alternative: str | None = None
    notes_en: str = ""


class Domain(str, Enum):
    """What kind of question a target answers.

    A municipality does not ask "detect objects". It asks how much of the city
    is built, which roofs carry solar, what condition the asphalt is in, where
    the informal settlements are. Grouping by that question is what lets a
    console offer sixty targets without becoming a wall of nouns.
    """

    LAND_COVER = "land_cover"      # what physically covers the ground
    LAND_USE = "land_use"          # what people do there
    BUILDING = "building"          # structures, and what kind
    TRANSPORT = "transport"        # the network and its surfaces
    STREET = "street"              # what stands beside a road
    CONDITION = "condition"        # the state of a thing, not its presence
    WATER = "water"
    ENERGY = "energy"
    AGRICULTURE = "agriculture"
    VEHICLE = "vehicle"


def _t(key, en, fa, geometry, gsd, domain, viewpoints=("overhead",),
       alternative=None, notes=""):
    """Shorthand: this file is a table, and reads better as one."""
    return Target(
        key=key, label_en=en, label_fa=fa, geometry=geometry, min_gsd_m=gsd,
        domain=domain, viewpoints=frozenset(viewpoints),
        coarser_alternative=alternative, notes_en=notes,
    )


_OVERHEAD = ("overhead",)
_STREET = ("street",)
_BOTH = ("overhead", "street")
_POLY = Geometry.POLYGON
_POINT = Geometry.POINT

# The catalogue. Ordered by domain, then by how sharp the imagery must be.
TARGETS: tuple[Target, ...] = (
    # --- land cover: what covers the ground -------------------------------
    _t("water", "Water", "پهنهٔ آبی", _POLY, 10.0, Domain.WATER,
       notes="Lakes, rivers, coastline, flood extent."),
    _t("river", "River", "رودخانه", _POLY, 10.0, Domain.WATER, alternative="water"),
    _t("reservoir", "Reservoir", "سد و مخزن", _POLY, 10.0, Domain.WATER, alternative="water"),
    _t("wetland", "Wetland", "تالاب", _POLY, 10.0, Domain.LAND_COVER, alternative="water"),
    _t("snow_ice", "Snow and ice", "برف و یخ", _POLY, 10.0, Domain.LAND_COVER),
    _t("forest_cover", "Forest cover", "پوشش جنگلی", _POLY, 10.0, Domain.LAND_COVER,
       notes="Canopy extent rather than individual trees."),
    _t("shrubland", "Shrubland", "بوته‌زار", _POLY, 10.0, Domain.LAND_COVER,
       alternative="forest_cover"),
    _t("grassland", "Grassland", "مرتع", _POLY, 10.0, Domain.LAND_COVER),
    _t("bare_ground", "Bare ground", "زمین بایر", _POLY, 10.0, Domain.LAND_COVER),
    _t("built_up", "Built-up area", "محدودهٔ ساخته‌شده", _POLY, 10.0, Domain.LAND_COVER,
       notes="Where settlement is, not which buildings."),

    # --- land use: what people do there -----------------------------------
    _t("residential_area", "Residential area", "منطقهٔ مسکونی", _POLY, 5.0, Domain.LAND_USE,
       alternative="built_up"),
    _t("commercial_area", "Commercial area", "منطقهٔ تجاری", _POLY, 5.0, Domain.LAND_USE,
       alternative="built_up"),
    _t("industrial_area", "Industrial area", "منطقهٔ صنعتی", _POLY, 5.0, Domain.LAND_USE,
       alternative="built_up"),
    _t("informal_settlement", "Informal settlement", "سکونتگاه غیررسمی", _POLY, 1.0,
       Domain.LAND_USE, alternative="built_up",
       notes="Dense small roofs and irregular street pattern; needs sub-metre imagery."),
    _t("construction_site", "Construction site", "کارگاه ساختمانی", _POLY, 1.0, Domain.LAND_USE),
    _t("quarry", "Quarry or mine", "معدن", _POLY, 5.0, Domain.LAND_USE),
    _t("landfill", "Landfill", "محل دفن زباله", _POLY, 5.0, Domain.LAND_USE),
    _t("cemetery", "Cemetery", "قبرستان", _POLY, 1.0, Domain.LAND_USE),
    _t("park", "Park or green space", "پارک", _POLY, 2.0, Domain.LAND_USE),
    _t("sports_pitch", "Sports pitch", "زمین ورزشی", _POLY, 1.0, Domain.LAND_USE),

    # --- buildings, and what kind -----------------------------------------
    _t("building", "Building", "ساختمان", _POLY, 1.0, Domain.BUILDING, _BOTH,
       alternative="built_up"),
    _t("building_residential", "Residential building", "ساختمان مسکونی", _POLY, 0.5,
       Domain.BUILDING, _BOTH, alternative="building"),
    _t("building_apartment", "Apartment block", "مجتمع مسکونی", _POLY, 0.5,
       Domain.BUILDING, _BOTH, alternative="building"),
    _t("building_commercial", "Commercial building", "ساختمان تجاری", _POLY, 0.5,
       Domain.BUILDING, _BOTH, alternative="building"),
    _t("building_industrial", "Industrial building", "ساختمان صنعتی", _POLY, 1.0,
       Domain.BUILDING, _BOTH, alternative="building"),
    _t("warehouse", "Warehouse", "انبار", _POLY, 1.0, Domain.BUILDING, alternative="building"),
    _t("greenhouse", "Greenhouse", "گلخانه", _POLY, 1.0, Domain.BUILDING),
    _t("school", "School", "مدرسه", _POLY, 0.5, Domain.BUILDING, _BOTH, alternative="building"),
    _t("hospital", "Hospital", "بیمارستان", _POLY, 0.5, Domain.BUILDING, _BOTH,
       alternative="building"),
    _t("religious_building", "Mosque or religious building", "مسجد و بنای مذهبی", _POLY, 0.5,
       Domain.BUILDING, _BOTH, alternative="building"),
    _t("building_under_construction", "Building under construction", "ساختمان در حال ساخت",
       _POLY, 0.5, Domain.BUILDING, _BOTH, alternative="construction_site"),
    _t("roof_material", "Roof material", "جنس بام", _POLY, 0.3, Domain.BUILDING,
       notes="Metal, tile, concrete, asbestos. Needs very high resolution."),

    # --- transport and its surfaces ---------------------------------------
    _t("road", "Road", "راه", _POLY, 2.0, Domain.TRANSPORT, _BOTH),
    _t("road_surface", "Road surface type", "نوع روسازی", _POLY, 0.1, Domain.TRANSPORT, _STREET,
       notes="Asphalt, concrete, gravel, dirt — read from the street, not from above."),
    _t("sidewalk", "Sidewalk", "پیاده‌رو", _POLY, 0.3, Domain.TRANSPORT, _BOTH),
    _t("crosswalk", "Crosswalk", "خط عابر", _POLY, 0.15, Domain.TRANSPORT, _BOTH),
    _t("parking", "Parking area", "پارکینگ", _POLY, 0.5, Domain.TRANSPORT),
    _t("bridge", "Bridge", "پل", _POLY, 1.0, Domain.TRANSPORT, _BOTH),
    _t("railway", "Railway", "راه‌آهن", _POLY, 2.0, Domain.TRANSPORT),
    _t("runway", "Runway", "باند فرودگاه", _POLY, 5.0, Domain.TRANSPORT),

    # --- condition: the state of a thing, not its presence -----------------
    _t("pavement_distress", "Pavement distress", "خرابی آسفالت", _POLY, 0.05,
       Domain.CONDITION, _STREET,
       notes="Cracking, potholes, patching. ASTM D6433 categories, from street imagery."),
    _t("pothole", "Pothole", "چاله", _POINT, 0.05, Domain.CONDITION, _STREET,
       alternative="pavement_distress"),
    _t("road_marking_wear", "Faded road marking", "کم‌رنگی خط‌کشی", _POLY, 0.05,
       Domain.CONDITION, _STREET),
    _t("facade_condition", "Facade condition", "وضعیت نما", _POLY, 0.05, Domain.CONDITION,
       _STREET),
    _t("graffiti", "Graffiti", "دیوارنویسی", _POLY, 0.05, Domain.CONDITION, _STREET),
    _t("litter", "Litter and dumping", "زباله رهاشده", _POINT, 0.05, Domain.CONDITION, _STREET),

    # --- street furniture --------------------------------------------------
    _t("sign", "Road sign", "تابلوی راه", _POINT, 0.1, Domain.STREET, _STREET,
       notes="A sign face is invisible from above, at any resolution."),
    _t("traffic_light", "Traffic light", "چراغ راهنما", _POINT, 0.05, Domain.STREET, _STREET),
    _t("street_light", "Street light", "روشنایی معبر", _POINT, 0.05, Domain.STREET, _BOTH),
    _t("utility_pole", "Utility pole", "تیر برق", _POINT, 0.05, Domain.STREET, _STREET),
    _t("manhole", "Manhole", "دریچهٔ منهول", _POINT, 0.05, Domain.STREET, _STREET),
    _t("bus_stop", "Bus stop", "ایستگاه اتوبوس", _POINT, 0.05, Domain.STREET, _STREET),
    _t("bench", "Bench", "نیمکت", _POINT, 0.05, Domain.STREET, _STREET),
    _t("waste_bin", "Waste bin", "سطل زباله", _POINT, 0.05, Domain.STREET, _STREET),
    _t("guardrail", "Guardrail", "حفاظ کنار جاده", _POLY, 0.05, Domain.STREET, _STREET),
    _t("fire_hydrant", "Fire hydrant", "شیر آتش‌نشانی", _POINT, 0.05, Domain.STREET, _STREET),
    _t("tree", "Tree", "درخت", _POLY, 1.0, Domain.LAND_COVER, _BOTH,
       alternative="forest_cover",
       notes="Individual crowns. Needs aerial or very-high-resolution satellite imagery."),

    # --- energy ------------------------------------------------------------
    _t("solar_panel", "Solar panel", "پنل خورشیدی", _POLY, 0.3, Domain.ENERGY),
    _t("wind_turbine", "Wind turbine", "توربین بادی", _POINT, 1.0, Domain.ENERGY),
    _t("power_line", "Power line", "خط انتقال برق", _POLY, 0.5, Domain.ENERGY, _BOTH),
    _t("substation", "Substation", "پست برق", _POLY, 1.0, Domain.ENERGY),
    _t("storage_tank", "Storage tank", "مخزن", _POLY, 1.0, Domain.ENERGY),

    # --- agriculture -------------------------------------------------------
    _t("cropland", "Cropland", "زمین کشاورزی", _POLY, 10.0, Domain.AGRICULTURE),
    _t("field_boundary", "Field boundary", "مرز قطعات زراعی", _POLY, 3.0, Domain.AGRICULTURE,
       alternative="cropland"),
    _t("orchard", "Orchard", "باغ", _POLY, 1.0, Domain.AGRICULTURE, alternative="cropland"),
    _t("irrigation_pivot", "Irrigation pivot", "آبیاری دورانی", _POLY, 10.0,
       Domain.AGRICULTURE),

    # --- vehicles and vessels ---------------------------------------------
    _t("car", "Vehicle", "خودرو", _POINT, 0.3, Domain.VEHICLE, _BOTH,
       notes="A car is about 4 m long; below 0.3 m/px counting degrades quickly."),
    _t("truck", "Truck", "کامیون", _POINT, 0.5, Domain.VEHICLE, _BOTH),
    _t("bus", "Bus", "اتوبوس", _POINT, 0.5, Domain.VEHICLE, _BOTH),
    _t("ship", "Ship", "شناور", _POINT, 1.0, Domain.VEHICLE),
    _t("aircraft", "Aircraft", "هواپیما", _POINT, 1.0, Domain.VEHICLE),
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
        key="spectral-landcover",
        label="Spectral land cover (NDVI / NDBI)",
        targets=frozenset({"forest_cover", "cropland", "built_up"}),
        runtime=Runtime.CPU,
        ram_gb=2.0,
        weights="none - spectral indices",
        licence="public method",
        benchmarks=(
            Benchmark("accuracy", 0.70, "typical for index-based cover at 10 m",
                      "index thresholds, not a trained model"),
        ),
        implemented=True,
        notes="Red, near-infrared and short-wave infrared. Coarse by design: where cover is, not whose field it is.",
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
        # Open vocabulary: any target whose shape is visible. Enumerated from
        # the taxonomy rather than hand-listed so a new target is offered the
        # moment it is declared.
        targets=frozenset(
            t.key for t in TARGETS
            if t.geometry is Geometry.POLYGON or t.domain is Domain.VEHICLE
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
        implemented=True,
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
        targets=frozenset({"car", "truck", "bus", "ship", "aircraft", "wind_turbine",
                           "storage_tank"}),
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
        key="eurosat-lulc",
        label="EuroSAT land use / land cover",
        targets=frozenset({
            "forest_cover", "cropland", "built_up", "water", "river",
            "grassland", "shrubland", "bare_ground", "residential_area",
            "industrial_area", "irrigation_pivot",
        }),
        runtime=Runtime.CPU_SLOW,
        ram_gb=4.0,
        weights="ResNet-50 / EfficientNet on EuroSAT",
        licence="MIT (dataset CC BY)",
        benchmarks=(
            Benchmark("accuracy", 0.988, "EuroSAT 10-class", "EfficientNet, 2025"),
            Benchmark("accuracy", 0.970, "EuroSAT 10-class", "ResNet-50 transfer"),
        ),
        notes="Patch classification on Sentinel-2. Ten classes, very high accuracy, coarse polygons.",
    ),
    Detector(
        key="bigearthnet",
        label="BigEarthNet multi-label cover",
        targets=frozenset({
            "forest_cover", "cropland", "wetland", "water", "grassland",
            "shrubland", "bare_ground", "built_up", "orchard", "snow_ice",
        }),
        runtime=Runtime.GPU,
        vram_gb=6.0,
        ram_gb=12.0,
        weights="Sentinel-1/2 multi-label model",
        benchmarks=(
            Benchmark("F1", 0.75, "BigEarthNet-19 multi-label", "BigEarthNet-MM"),
        ),
        notes="Several covers can be true of one patch at once, which is what mixed landscapes actually look like.",
    ),
    Detector(
        key="vistas-street",
        label="Mapillary Vistas street segmentation",
        targets=frozenset({
            "road", "road_surface", "sidewalk", "crosswalk", "sign",
            "traffic_light", "street_light", "utility_pole", "manhole",
            "bench", "waste_bin", "guardrail", "bus_stop", "fire_hydrant", "litter",
            "building", "tree", "car", "truck", "bus", "power_line",
        }),
        runtime=Runtime.GPU,
        vram_gb=8.0,
        ram_gb=16.0,
        weights="Vistas-trained segmentation backbone",
        licence="research licence — check before commercial use",
        benchmarks=(
            Benchmark("mIoU", 0.61, "Mapillary Vistas (66 classes)", "Vistas benchmark"),
        ),
        notes="The street-level counterpart to SAM: 66 to 150 classes of everything beside a road.",
    ),
    Detector(
        key="pavement-distress",
        label="Pavement distress (ASTM D6433)",
        targets=frozenset({
            "pavement_distress", "pothole", "road_marking_wear", "road_surface",
        }),
        runtime=Runtime.GPU,
        vram_gb=6.0,
        ram_gb=12.0,
        weights="Mask R-CNN / YOLO on street-level pavement datasets",
        benchmarks=(
            Benchmark("mAP", 0.72, "UWGB-STREETCRACK / UAV-PDD2023",
                      "instance segmentation of cracks and potholes"),
        ),
        notes="Longitudinal, transverse and alligator cracking, patching, potholes — the asphalt question, answered from the street.",
    ),
    Detector(
        key="building-type-fusion",
        label="Building type from aerial + street",
        targets=frozenset({
            "building_residential", "building_apartment", "building_commercial",
            "building_industrial", "school", "hospital", "religious_building",
            "warehouse", "building_under_construction",
        }),
        runtime=Runtime.GPU,
        vram_gb=8.0,
        ram_gb=16.0,
        weights="aerial + street-view fusion classifier",
        benchmarks=(
            Benchmark("accuracy", 0.80, "transnational building type/function",
                      "arXiv 2409.09692"),
        ),
        notes="A roof says a building exists; the facade says what it is. Needs both viewpoints for the same footprint.",
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
    # The same refusal, in a form a console can phrase in its own language.
    # The English sentence above stays for API consumers and logs; a Persian
    # operator should not be told "needs imagery of 0.5 m/pixel or sharper" in
    # English on a screen that is otherwise entirely in Persian.
    reason_code: str = ""
    reason_values: dict = field(default_factory=dict)


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
        return Availability(target_key, False, reason="unknown target",
                            reason_code="unknown_target")

    if viewpoint not in target.viewpoints:
        seen_from = " and ".join(sorted(target.viewpoints))
        return Availability(
            target_key,
            False,
            reason=f"not visible from {viewpoint} imagery; this is seen from {seen_from}",
            reason_code="wrong_viewpoint",
            reason_values={"viewpoint": viewpoint, "seen_from": seen_from},
        )

    detectors = detectors_for(target_key)
    if not detectors:
        return Availability(target_key, False, reason="no detector supports this target",
                            reason_code="no_detector")

    if gsd_m is None:
        return Availability(
            target_key,
            False,
            reason="this imagery does not report its resolution",
            reason_code="unknown_resolution",
            detectors=detectors,
        )

    if gsd_m > target.min_gsd_m:
        alternative = target.coarser_alternative
        reason = (
            f"needs imagery of {target.min_gsd_m:g} m/pixel or sharper; "
            f"this source is {gsd_m:g} m/pixel"
        )
        return Availability(
            target_key,
            False,
            reason=reason,
            reason_code="too_coarse",
            reason_values={"needs": target.min_gsd_m, "has": gsd_m},
            alternative=alternative,
            detectors=detectors,
        )

    return Availability(target_key, True, detectors=detectors)


def catalogue_for(
    gsd_m: float | None, viewpoint: str = Viewpoint.OVERHEAD.value
) -> list[Availability]:
    """Every target, with a verdict, for one imagery source."""
    return [availability(t.key, gsd_m, viewpoint) for t in TARGETS]
