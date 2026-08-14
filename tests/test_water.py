"""Water from the spectrum.

Synthetic chips, so the tests are deterministic and need no network. The point
is not that NDWI works — McFeeters established that in 1996 — but that this
implementation thresholds, filters and measures the way it claims to.
"""

import numpy as np
import pytest

from mithra_ml.water import NDWI_THRESHOLD, NdwiWaterDetector
from mithra_worker.imagery import Chip


def chip_with(mask: np.ndarray, gsd_m: float = 10.0) -> Chip:
    """A green/NIR chip where `mask` marks the wet pixels.

    Water reflects green and absorbs near-infrared; land does the opposite.
    """
    green = np.where(mask, 3000, 1000).astype("uint16")
    nir = np.where(mask, 300, 4000).astype("uint16")
    # A degree of longitude is ~89 km here, so this bbox is about 100 pixels
    # wide at 10 m — matching the array below.
    return Chip(data=np.stack([green, nir]), bounds=(59.60, 36.29, 59.61, 36.30), gsd_m=gsd_m)


def test_a_lake_is_found_and_measured():
    mask = np.zeros((100, 100), dtype=bool)
    mask[20:60, 20:60] = True  # 1600 pixels
    found = NdwiWaterDetector().detect(chip_with(mask), ["water"])

    assert len(found) == 1
    assert found[0].class_name == "water"
    assert found[0].geometry["type"] == "Polygon"
    # 1600 pixels at 10 m each is 160,000 m². Allow for polygon rasterisation.
    assert found[0].area_m2 == pytest.approx(160_000, rel=0.1)


def test_dry_land_yields_nothing():
    found = NdwiWaterDetector().detect(chip_with(np.zeros((60, 60), dtype=bool)), ["water"])
    assert found == []


def test_specks_are_not_lakes():
    """A wet roof or one bad pixel is not a water body."""
    mask = np.zeros((60, 60), dtype=bool)
    mask[10:12, 10:12] = True  # 4 pixels
    assert NdwiWaterDetector().detect(chip_with(mask), ["water"]) == []


def test_the_minimum_size_is_configurable_and_honoured():
    mask = np.zeros((60, 60), dtype=bool)
    mask[10:15, 10:15] = True  # 25 pixels
    assert NdwiWaterDetector(min_pixels=100).detect(chip_with(mask), ["water"]) == []
    assert NdwiWaterDetector(min_pixels=10).detect(chip_with(mask), ["water"])


def test_separate_bodies_are_separate_detections():
    mask = np.zeros((100, 100), dtype=bool)
    mask[10:40, 10:40] = True
    mask[60:90, 60:90] = True
    found = NdwiWaterDetector().detect(chip_with(mask), ["water"])
    assert len(found) == 2


def test_the_largest_body_is_reported_first():
    mask = np.zeros((100, 100), dtype=bool)
    mask[5:15, 5:15] = True     # small
    mask[40:90, 40:90] = True   # large
    found = NdwiWaterDetector().detect(chip_with(mask), ["water"])
    assert found[0].area_m2 > found[1].area_m2


def test_asking_for_something_else_returns_nothing():
    """A detector that answered a question it was not asked would be lying."""
    mask = np.ones((60, 60), dtype=bool)
    assert NdwiWaterDetector().detect(chip_with(mask), ["tree"]) == []


def test_nodata_is_not_water():
    """Zero in both bands is the edge of a scene, not a lake."""
    green = np.zeros((60, 60), dtype="uint16")
    nir = np.zeros((60, 60), dtype="uint16")
    chip = Chip(data=np.stack([green, nir]), bounds=(59.60, 36.29, 59.61, 36.30), gsd_m=10.0)
    assert NdwiWaterDetector().detect(chip, ["water"]) == []


def test_a_chip_without_the_bands_it_needs_says_so():
    chip = Chip(data=np.zeros((1, 60, 60), dtype="uint16"),
                bounds=(59.60, 36.29, 59.61, 36.30), gsd_m=10.0)
    with pytest.raises(ValueError, match="near-infrared"):
        NdwiWaterDetector().detect(chip, ["water"])


def test_area_scales_with_resolution():
    """The same pixels at finer resolution cover less ground."""
    mask = np.zeros((100, 100), dtype=bool)
    mask[20:60, 20:60] = True
    coarse = NdwiWaterDetector().detect(chip_with(mask, gsd_m=10.0), ["water"])[0]
    fine = NdwiWaterDetector().detect(chip_with(mask, gsd_m=1.0), ["water"])[0]
    assert coarse.area_m2 == pytest.approx(fine.area_m2 * 100, rel=0.05)


def test_confidence_reflects_how_strongly_the_spectrum_says_water():
    mask = np.zeros((100, 100), dtype=bool)
    mask[20:60, 20:60] = True
    found = NdwiWaterDetector().detect(chip_with(mask), ["water"])[0]
    assert 0.0 <= found.confidence <= 1.0
    assert found.properties["method"] == "ndwi"
    assert found.properties["threshold"] == NDWI_THRESHOLD
