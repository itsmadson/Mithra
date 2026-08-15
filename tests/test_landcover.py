"""Land cover from spectral indices.

Synthetic scenes, so the thresholds are tested rather than the physics. The
classes must partition: a pixel that is both green and built has to land in
exactly one of them, or the areas sum to more than the ground.
"""

import numpy as np
import pytest

from mithra_ml.landcover import LandCoverDetector
from mithra_worker.imagery import Chip


def scene(kind: str, size: int = 60) -> Chip:
    """A uniform scene of one cover type, in (red, nir, swir) order."""
    if kind == "forest":
        red, nir, swir = 400, 4000, 1200      # NDVI ~0.82, NDBI negative
    elif kind == "crop":
        red, nir, swir = 900, 1800, 1400      # NDVI ~0.33
    elif kind == "built":
        red, nir, swir = 2000, 2200, 3200     # NDBI positive, NDVI low
    else:
        red, nir, swir = 1500, 1500, 1500     # bare: nothing stands out
    bands = [np.full((size, size), v, dtype="uint16") for v in (red, nir, swir)]
    return Chip(data=np.stack(bands), bounds=(59.60, 36.29, 59.61, 36.30), gsd_m=10.0)


def classes_found(chip, targets=("forest_cover", "cropland", "built_up")):
    found = LandCoverDetector().detect(chip, list(targets))
    return {d.class_name for d in found}


def test_forest_is_recognised():
    assert classes_found(scene("forest")) == {"forest_cover"}


def test_cropland_is_recognised():
    assert classes_found(scene("crop")) == {"cropland"}


def test_built_up_is_recognised():
    assert classes_found(scene("built")) == {"built_up"}


def test_bare_ground_is_no_class_at_all():
    """Not everything is one of three things, and saying so is the point."""
    assert classes_found(scene("bare")) == set()


def test_the_classes_do_not_overlap():
    """A pixel in two classes would make the areas sum past the ground."""
    for kind in ("forest", "crop", "built", "bare"):
        found = LandCoverDetector().detect(
            scene(kind), ["forest_cover", "cropland", "built_up"]
        )
        total = sum(d.area_m2 or 0 for d in found)
        ground = 60 * 60 * 100  # 3600 pixels at 10 m
        assert total <= ground * 1.05, f"{kind} reports more cover than ground"


def test_only_the_asked_class_is_returned():
    found = LandCoverDetector().detect(scene("forest"), ["cropland"])
    assert found == []


def test_nodata_is_not_land_cover():
    blank = Chip(
        data=np.zeros((3, 60, 60), dtype="uint16"),
        bounds=(59.60, 36.29, 59.61, 36.30),
        gsd_m=10.0,
    )
    assert LandCoverDetector().detect(blank, ["forest_cover", "built_up"]) == []


def test_a_chip_without_the_bands_it_needs_says_so():
    two_band = Chip(
        data=np.zeros((2, 60, 60), dtype="uint16"),
        bounds=(59.60, 36.29, 59.61, 36.30),
        gsd_m=10.0,
    )
    with pytest.raises(ValueError, match="short-wave infrared"):
        LandCoverDetector().detect(two_band, ["forest_cover"])


def test_area_follows_resolution():
    coarse = LandCoverDetector().detect(scene("forest"), ["forest_cover"])[0]
    fine_chip = scene("forest")
    fine = LandCoverDetector().detect(
        Chip(data=fine_chip.data, bounds=fine_chip.bounds, gsd_m=1.0), ["forest_cover"]
    )[0]
    assert coarse.area_m2 == pytest.approx((fine.area_m2 or 0) * 100, rel=0.05)
