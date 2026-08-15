"""Land cover from the spectrum.

The same argument as water: at ten metres a forest is not an object with an
outline to segment, it is a region whose reflectance differs from its
neighbours. Vegetation reflects near-infrared strongly and absorbs red;
built surfaces reflect short-wave infrared more than near-infrared. Those two
contrasts separate most of what a municipality asks about at this resolution,
without weights, on a CPU, at any scale.

Dynamic World answers the same question with a neural network and scores 73.8%
globally — better on mixed pixels and worse on nothing in particular, but it
needs Earth Engine to run. This is the offline answer, and it is honest about
being coarse: it reports where cover is, not which field belongs to whom.
"""

from __future__ import annotations

from mithra_ml.detect import Detection

# NDVI above this is vegetation. 0.4 separates canopy from grass and bare soil
# in most temperate and arid scenes; below 0.2 is effectively bare.
FOREST_NDVI = 0.4
CROP_NDVI = 0.2
# NDBI above this is built surface. Roofs and roads reflect short-wave infrared
# more than near-infrared; vegetation does the reverse.
BUILT_NDBI = 0.0

MIN_PIXELS = 20

# Which bands each class needs, in the order the chip provides them.
BANDS = ("red", "nir", "swir16")


class LandCoverDetector:
    """Forest, cropland and built-up extent from Sentinel-2 bands."""

    key = "spectral-landcover"
    version = "ndvi-ndbi-v1"
    targets = frozenset({"forest_cover", "cropland", "built_up"})

    def __init__(self, min_pixels: int = MIN_PIXELS) -> None:
        self._min_pixels = min_pixels

    def detect(self, chip, targets: list[str]) -> list[Detection]:
        import numpy as np
        from rasterio.features import shapes
        from rasterio.transform import from_bounds

        wanted = [t for t in targets if t in self.targets]
        if not wanted:
            return []

        data = np.asarray(chip.data).astype("float32")
        if data.ndim != 3 or data.shape[0] < 3:
            raise ValueError(
                "land cover needs red, near-infrared and short-wave infrared bands"
            )

        red, nir, swir = data[0], data[1], data[2]

        def normalised(a, b):
            total = a + b
            # No signal is not a class. Saying so keeps the division from
            # inventing forest at the edge of a scene.
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(total == 0, -1.0, (a - b) / total)

        ndvi = normalised(nir, red)
        ndbi = normalised(swir, nir)

        masks = {
            # Ordered so a pixel lands in exactly one class: dense vegetation
            # first, then anything built, then the sparser vegetation left over.
            "forest_cover": ndvi > FOREST_NDVI,
            "built_up": (ndbi > BUILT_NDBI) & (ndvi <= FOREST_NDVI),
            "cropland": (ndvi > CROP_NDVI) & (ndvi <= FOREST_NDVI) & (ndbi <= BUILT_NDBI),
        }

        west, south, east, north = chip.bounds
        height, width = ndvi.shape
        transform = from_bounds(west, south, east, north, width, height)
        pixel_area_m2 = chip.gsd_m * chip.gsd_m
        degrees_per_pixel = ((east - west) / width) * ((north - south) / height)

        detections: list[Detection] = []
        for target in wanted:
            mask = masks[target].astype("uint8")
            if mask.sum() == 0:
                continue

            index = ndvi if target != "built_up" else ndbi
            confidence = _confidence(index, mask)

            for geometry, value in shapes(
                mask, mask=mask.astype(bool), transform=transform
            ):
                if value != 1:
                    continue
                pixels = _pixels(geometry, degrees_per_pixel)
                if pixels < self._min_pixels:
                    continue
                detections.append(
                    Detection(
                        class_name=target,
                        geometry=geometry,
                        confidence=confidence,
                        area_m2=round(pixels * pixel_area_m2, 1),
                        properties={"method": self.version},
                    )
                )

        detections.sort(key=lambda d: d.area_m2 or 0, reverse=True)
        return detections


def _pixels(geometry: dict, degrees_per_pixel: float) -> int:
    from shapely.geometry import shape

    if not degrees_per_pixel:
        return 0
    return round(shape(geometry).area / degrees_per_pixel)


def _confidence(index, mask) -> float:
    import numpy as np

    values = index[mask.astype(bool)]
    if values.size == 0:
        return 0.0
    # The index runs -1..1; map its mean onto 0..1 so it reads like every other
    # confidence in the product rather than like a different scale.
    return float(min(1.0, max(0.0, (float(values.mean()) + 1.0) / 2.0)))
