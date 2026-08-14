"""The raster path: refuse first, then fetch, then detect.

The refusal tests need no network and are the ones that matter most — they are
what stops the product from spending an hour to return a misleading empty
layer.
"""

import numpy as np
import pytest

from mithra_worker.imagery import Chip, ImageryError
from mithra_worker.raster_pipeline import (
    RunRefused,
    check_targets,
    detect_over_area,
    detector_for,
    fetch_chip,
)


# --- refusals ----------------------------------------------------------------


def test_trees_on_sentinel_2_are_refused_before_any_work():
    with pytest.raises(RunRefused, match="1 m/pixel or sharper"):
        check_targets("sentinel2", ["tree"], None)


def test_the_refusal_names_the_question_that_can_be_answered():
    with pytest.raises(RunRefused, match="try forest_cover instead"):
        check_targets("sentinel2", ["tree"], None)


def test_water_on_sentinel_2_is_allowed():
    check_targets("sentinel2", ["water"], None)  # does not raise


def test_land_cover_from_street_imagery_is_refused():
    with pytest.raises(RunRefused, match="not visible from street"):
        check_targets("mapillary", ["water"], None)


def test_one_impossible_target_refuses_the_whole_run():
    """Half an answer to a two-part question is worse than a clear refusal."""
    with pytest.raises(RunRefused):
        check_targets("sentinel2", ["water", "car"], None)


def test_an_unknown_source_is_refused():
    with pytest.raises(RunRefused, match="unknown imagery source"):
        check_targets("telescope", ["water"], None)


def test_an_upload_can_do_what_its_resolution_allows():
    """Nothing until the file reports itself; then judged on that."""
    with pytest.raises(RunRefused):
        check_targets("upload", ["tree"], None)
    check_targets("upload", ["tree"], 0.3)


# --- detectors ---------------------------------------------------------------


def test_the_water_detector_is_available():
    detector = detector_for("ndwi-water")
    assert "water" in detector.targets


def test_a_declared_but_unbuilt_detector_says_so_plainly():
    """The catalogue lists SAM 3; this build does not ship it, and admits it."""
    with pytest.raises(RunRefused, match="not implemented in this build"):
        detector_for("sam3")


# --- fetching ----------------------------------------------------------------


def test_a_cog_source_needs_a_url():
    with pytest.raises(ImageryError, match="needs a url"):
        fetch_chip("cog", {}, (0, 0, 0.01, 0.01))


def test_an_upload_source_needs_a_path():
    with pytest.raises(ImageryError, match="needs a stored path"):
        fetch_chip("upload", {}, (0, 0, 0.01, 0.01))


def test_street_imagery_is_not_a_raster_source():
    with pytest.raises(ImageryError, match="cannot be read as a raster"):
        fetch_chip("mapillary", {}, (0, 0, 0.01, 0.01))


def test_a_cloudless_window_with_no_scenes_is_reported_not_guessed(monkeypatch):
    """An empty search is a fact about the sky, and has to be said out loud."""
    monkeypatch.setattr("mithra_worker.raster_pipeline.search_stac", lambda *a, **k: [])
    with pytest.raises(ImageryError, match="no sentinel2 scene under"):
        fetch_chip("sentinel2", {"max_cloud": 5}, (59.6, 36.29, 59.61, 36.30))


# --- the whole path, with the network stubbed --------------------------------


def _fake_chip(mask_value: bool = True) -> Chip:
    mask = np.zeros((80, 80), dtype=bool)
    if mask_value:
        mask[10:60, 10:60] = True
    green = np.where(mask, 3000, 1000).astype("uint16")
    nir = np.where(mask, 300, 4000).astype("uint16")
    return Chip(data=np.stack([green, nir]), bounds=(49.40, 37.40, 49.41, 37.41), gsd_m=10.0)


def test_a_run_returns_detections_and_the_provenance_of_the_imagery(monkeypatch):
    monkeypatch.setattr(
        "mithra_worker.raster_pipeline.fetch_chip",
        lambda *a, **k: (_fake_chip(), {"scene_id": "S2_TEST", "captured": "2026-07-03"}),
    )
    found, provenance = detect_over_area(
        "sentinel2", {}, (49.40, 37.40, 49.41, 37.41), ["water"], "ndwi-water"
    )

    assert found and found[0].class_name == "water"
    # A count that cannot name the image it came from is not auditable.
    assert provenance["scene_id"] == "S2_TEST"
    assert provenance["gsd_m"] == 10.0
    assert provenance["pixels"] == [80, 80]


def test_an_area_with_no_water_returns_nothing_rather_than_failing(monkeypatch):
    monkeypatch.setattr(
        "mithra_worker.raster_pipeline.fetch_chip",
        lambda *a, **k: (_fake_chip(mask_value=False), {"scene_id": "S2_DRY"}),
    )
    found, provenance = detect_over_area(
        "sentinel2", {}, (49.40, 37.40, 49.41, 37.41), ["water"], "ndwi-water"
    )
    assert found == []
    assert provenance["scene_id"] == "S2_DRY"
