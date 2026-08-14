"""Water from the spectrum, not from a neural network.

At Sentinel-2's ten metres there is no instance to segment — a lake is a region
of the image, not an object with an outline a detector could recognise. What
there is, is physics: water absorbs near-infrared strongly and reflects green,
so the normalised difference between those two bands separates it from
everything else more reliably than a model trained on RGB tiles.

This is McFeeters' NDWI (1996), and it is the standard method for exactly this
resolution. Using it rather than a foundation model here is not a compromise:
it is faster, it needs no weights, it works on the free imagery, and it is
explainable to somebody who has to defend the number.
"""

from __future__ import annotations

from mithra_ml.detect import Detection

# Above this, a pixel is water. McFeeters proposed zero; real scenes carry
# shadow and wet soil near it, so a slightly positive cut trades a little
# recall for a lot less false shoreline.
NDWI_THRESHOLD = 0.05

# Below this many pixels, a "lake" is noise — a wet roof, a shadow, one bad
# pixel. At 10 m, 20 pixels is 2000 m², about half a football pitch.
MIN_PIXELS = 20


class NdwiWaterDetector:
    key = "ndwi-water"
    version = "ndwi-mcfeeters-1996"
    targets = frozenset({"water"})

    def __init__(self, threshold: float = NDWI_THRESHOLD, min_pixels: int = MIN_PIXELS) -> None:
        self._threshold = threshold
        self._min_pixels = min_pixels

    def detect(self, chip, targets: list[str]) -> list[Detection]:
        """Find water in a chip whose bands are (green, nir, ...).

        Returns one detection per connected region, with its area — because
        "how much water" is the question, and a count of lakes is not.
        """
        if "water" not in targets:
            return []

        import numpy as np
        from rasterio.features import shapes
        from rasterio.transform import from_bounds

        data = np.asarray(chip.data)
        if data.ndim != 3 or data.shape[0] < 2:
            raise ValueError("NDWI needs at least a green and a near-infrared band")

        green = data[0].astype("float32")
        nir = data[1].astype("float32")
        denominator = green + nir
        # A zero denominator is a pixel with no signal at all — nodata, or the
        # edge of a scene. It is not water; saying so explicitly keeps the
        # division from inventing a shoreline there.
        with np.errstate(divide="ignore", invalid="ignore"):
            ndwi = np.where(denominator == 0, -1.0, (green - nir) / denominator)

        mask = (ndwi > self._threshold).astype("uint8")
        if mask.sum() == 0:
            return []

        west, south, east, north = chip.bounds
        transform = from_bounds(west, south, east, north, mask.shape[1], mask.shape[0])
        pixel_area_m2 = chip.gsd_m * chip.gsd_m

        detections: list[Detection] = []
        for geometry, value in shapes(mask, mask=mask.astype(bool), transform=transform):
            if value != 1:
                continue
            pixels = _ring_pixel_count(geometry, chip, mask)
            if pixels < self._min_pixels:
                continue
            area = pixels * pixel_area_m2
            detections.append(
                Detection(
                    class_name="water",
                    geometry=geometry,
                    # Mean NDWI over the region, rescaled to 0-1: how strongly
                    # the spectrum says water, which is the honest confidence
                    # for a physical index rather than a made-up probability.
                    confidence=_region_confidence(ndwi, mask),
                    area_m2=round(area, 1),
                    properties={"method": "ndwi", "threshold": self._threshold},
                )
            )

        detections.sort(key=lambda d: d.area_m2 or 0, reverse=True)
        return detections


def _ring_pixel_count(geometry: dict, chip, mask) -> int:
    """Approximate a polygon's pixel count from its geographic area."""
    from shapely.geometry import shape

    polygon = shape(geometry)
    west, south, east, north = chip.bounds
    lat_span = max(north - south, 1e-9)
    lon_span = max(east - west, 1e-9)
    degrees_per_pixel = (lon_span / mask.shape[1]) * (lat_span / mask.shape[0])
    # Rounded, not truncated: the area of a 20-pixel region computes to
    # 19.9999 as often as to 20.0, and truncating drops it below a threshold it
    # actually meets.
    return round(polygon.area / degrees_per_pixel) if degrees_per_pixel else 0


def _region_confidence(ndwi, mask) -> float:
    import numpy as np

    values = ndwi[mask.astype(bool)]
    if values.size == 0:
        return 0.0
    # NDWI runs -1..1; water sits well above zero. Map the mean onto 0..1 so it
    # reads like every other confidence in the product.
    return float(min(1.0, max(0.0, (values.mean() + 1.0) / 2.0)))
