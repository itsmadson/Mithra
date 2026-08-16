"""Where the pixels come from.

Each source declares its resolution, its licence, and whether it can be used
for bulk inference — because those three facts decide, respectively, what can
be detected, whether the output can be published, and whether running the job
is allowed at all.

The registry mirrors the detector registry deliberately: a run is a pairing of
one source and one detector, and both halves have to declare what they can do
before the pairing can be judged.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceKind(str, Enum):
    MAPILLARY = "mapillary"
    XYZ = "xyz"
    COG = "cog"
    STAC = "stac"
    UPLOAD = "upload"


class ImageryKind(str, Enum):
    """Photograph, or drawing.

    The third axis, after viewpoint and resolution, and the one that is easiest
    to miss: a cartographic basemap has arbitrarily fine "resolution" and no
    information a detector can use. Running a tree model over OpenStreetMap
    tiles finds one crown in a park full of them — not because the model is
    weak, but because there are no trees in a drawing of a park, only green
    polygons.
    """

    PHOTO = "photo"
    MAP = "map"
    # A user-supplied tile service could be either, and only the operator
    # knows which.
    UNKNOWN = "unknown"


class BulkUse(str, Enum):
    """Whether the licence permits running a model over the whole area."""

    ALLOWED = "allowed"
    # The imagery may be viewed but its terms forbid systematic download or
    # derived datasets. Consumer basemaps are usually here.
    FORBIDDEN = "forbidden"
    # Depends on the operator's own contract with the provider, which this
    # software cannot know.
    CHECK_YOUR_LICENCE = "check_your_licence"


@dataclass(frozen=True)
class ImagerySource:
    key: str
    label_en: str
    label_fa: str
    kind: SourceKind
    # Nominal metres per pixel at the resolution the pipeline will request.
    # None means the source cannot say — an uploaded raster reports its own.
    gsd_m: float | None
    licence: str
    bulk_use: BulkUse
    # Overhead or street: decides what is visible at all, independent of GSD.
    viewpoint: str = "overhead"
    # Photograph or drawing: decides whether there is anything to detect.
    imagery_kind: str = ImageryKind.PHOTO.value
    needs_credentials: bool = False
    notes_en: str = ""
    # The console is Persian-first. A source that explains itself only in
    # English explains itself to half the people using it.
    notes_fa: str = ""


SOURCES: tuple[ImagerySource, ...] = (
    ImagerySource(
        key="mapillary",
        label_en="Mapillary street-level",
        label_fa="تصاویر خیابانی Mapillary",
        kind=SourceKind.MAPILLARY,
        gsd_m=0.05,
        licence="CC BY-SA (contributor imagery)",
        bulk_use=BulkUse.ALLOWED,
        viewpoint="street",
        needs_credentials=True,
        notes_en="Panoramas from the street, not from above. The only source that sees a feature face.",
        notes_fa="پانوراما از سطح خیابان، نه از بالا. تنها منبعی که نمای روبه‌روی عارضه را می‌بیند.",
    ),
    ImagerySource(
        key="sentinel2",
        label_en="Sentinel-2 (ESA, free)",
        label_fa="سنتینل-۲",
        kind=SourceKind.STAC,
        gsd_m=10.0,
        licence="Copernicus open data",
        bulk_use=BulkUse.ALLOWED,
        notes_en="Global, revisits every five days, free to redistribute. Coarse: 10 m per pixel.",
        notes_fa="پوشش جهانی، بازدید هر پنج روز، بازنشر آزاد. درشت‌دانه: ۱۰ متر بر پیکسل.",
    ),
    ImagerySource(
        key="naip",
        label_en="NAIP aerial (US)",
        label_fa="تصاویر هوایی NAIP",
        kind=SourceKind.STAC,
        gsd_m=0.6,
        licence="US public domain",
        bulk_use=BulkUse.ALLOWED,
        notes_en="United States only.",
        notes_fa="فقط ایالات متحده.",
    ),
    ImagerySource(
        key="xyz",
        label_en="Custom tile service",
        label_fa="سرویس کاشی دلخواه",
        kind=SourceKind.XYZ,
        gsd_m=0.3,
        imagery_kind=ImageryKind.UNKNOWN.value,
        licence="whatever the operator's endpoint carries",
        bulk_use=BulkUse.CHECK_YOUR_LICENCE,
        notes_en=(
            "Any {z}/{x}/{y} endpoint. Say whether it serves photographs or a "
            "drawn map — a detector finds nothing in cartography. Consumer "
            "basemaps generally forbid bulk inference too; use imagery you are "
            "licensed for."
        ),
        notes_fa=(
            "هر نشانی {z}/{x}/{y}. مشخص کنید تصویر هوایی می‌دهد یا نقشهٔ ترسیمی — "
            "مدل در نقشه چیزی نمی‌یابد. نقشه‌های پایهٔ عمومی هم معمولاً پردازش انبوه "
            "را منع می‌کنند؛ از تصویری استفاده کنید که پروانهٔ آن را دارید."
        ),
    ),
    ImagerySource(
        key="cog",
        label_en="Cloud-optimised GeoTIFF (URL)",
        label_fa="گئوتیف ابری (نشانی)",
        kind=SourceKind.COG,
        gsd_m=None,
        licence="the operator's own",
        bulk_use=BulkUse.CHECK_YOUR_LICENCE,
        notes_en="Resolution is read from the file header.",
        notes_fa="تفکیک‌پذیری از سرایند فایل خوانده می‌شود.",
    ),
    ImagerySource(
        key="upload",
        label_en="Uploaded raster",
        label_fa="راستر بارگذاری‌شده",
        kind=SourceKind.UPLOAD,
        gsd_m=None,
        licence="the operator's own",
        bulk_use=BulkUse.ALLOWED,
        notes_en="Drone or aerial imagery you own. Resolution is read from the file.",
        notes_fa="تصویر پهپادی یا هوایی متعلق به خودتان. تفکیک‌پذیری از فایل خوانده می‌شود.",
    ),
)

SOURCES_BY_KEY: dict[str, ImagerySource] = {s.key: s for s in SOURCES}


def resolve_gsd(source_key: str, declared_gsd_m: float | None = None) -> float | None:
    """The resolution a run will actually work at.

    A source whose registry entry has no GSD (an upload, a COG) takes it from
    the file itself; the caller passes what the header reported. A source that
    declares one keeps it, because a Sentinel-2 scene is 10 m no matter what a
    request claims.
    """
    source = SOURCES_BY_KEY.get(source_key)
    if source is None:
        return None
    if source.gsd_m is not None:
        return source.gsd_m
    return declared_gsd_m
