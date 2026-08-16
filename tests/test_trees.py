"""Tree crowns, and the imagery they need.

The geometry test matters most: pixel rows count down from the north edge and
latitude counts up, so getting the flip wrong mirrors every crown across the
scene — which looks entirely plausible until somebody checks one against the
photograph.
"""

import numpy as np
import pytest

from mithra_ml.trees import DeepForestDetector
from mithra_worker.imagery import Chip
from mithra_worker.raster_pipeline import RunRefused, check_imagery_kind


class FakeBoxes:
    """What DeepForest returns, without loading DeepForest."""

    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def itertuples(self):
        from collections import namedtuple

        Row = namedtuple("Row", "xmin ymin xmax ymax score")
        return (Row(*r) for r in self._rows)


def chip(width=100, height=100):
    data = np.full((3, height, width), 120, dtype="uint8")
    # One degree of longitude here is ~89 km, so this box is about 890 m wide.
    return Chip(data=data, bounds=(59.60, 36.29, 59.61, 36.30), gsd_m=1.0)


def detector_with(rows, min_score=0.15):
    d = DeepForestDetector(min_score=min_score)
    d._model = type("M", (), {"predict_tile": lambda self, **kw: FakeBoxes(rows)})()  # noqa: SLF001
    return d


def test_a_crown_becomes_a_polygon_with_an_area():
    found = detector_with([(10, 10, 30, 30, 0.4)]).detect(chip(), ["tree"])
    assert len(found) == 1
    assert found[0].class_name == "tree"
    assert found[0].geometry["type"] == "Polygon"
    # 20x20 pixels at 1 m each.
    assert found[0].area_m2 == pytest.approx(400, rel=0.01)


def test_the_north_edge_is_the_top_of_the_image():
    """A crown near the top of the picture is at the north of the area.

    Flipping this mirrors every detection across the scene and still produces a
    map that looks right at a glance.
    """
    north_box = detector_with([(10, 5, 20, 15, 0.4)]).detect(chip(), ["tree"])[0]
    south_box = detector_with([(10, 85, 20, 95, 0.4)]).detect(chip(), ["tree"])[0]

    north_lat = max(c[1] for c in north_box.geometry["coordinates"][0])
    south_lat = max(c[1] for c in south_box.geometry["coordinates"][0])
    assert north_lat > south_lat


def test_detections_stay_inside_the_area_that_was_asked_for():
    found = detector_with([(0, 0, 99, 99, 0.4)]).detect(chip(), ["tree"])[0]
    lons = [c[0] for c in found.geometry["coordinates"][0]]
    lats = [c[1] for c in found.geometry["coordinates"][0]]
    assert 59.60 <= min(lons) and max(lons) <= 59.61 + 1e-9
    assert 36.29 <= min(lats) and max(lats) <= 36.30 + 1e-9


def test_low_scoring_boxes_are_dropped():
    rows = [(10, 10, 20, 20, 0.05), (30, 30, 40, 40, 0.4)]
    assert len(detector_with(rows).detect(chip(), ["tree"])) == 1


def test_the_most_confident_crown_comes_first():
    rows = [(10, 10, 20, 20, 0.2), (30, 30, 40, 40, 0.5)]
    found = detector_with(rows).detect(chip(), ["tree"])
    assert found[0].confidence > found[1].confidence


def test_asking_for_something_else_returns_nothing():
    assert detector_with([(10, 10, 20, 20, 0.9)]).detect(chip(), ["water"]) == []


def test_an_image_without_three_bands_is_refused():
    two_band = Chip(data=np.zeros((2, 50, 50), dtype="uint8"),
                    bounds=(59.60, 36.29, 59.61, 36.30), gsd_m=1.0)
    with pytest.raises(ValueError, match="three-band"):
        detector_with([]).detect(two_band, ["tree"])


# --- photographs versus drawings ---------------------------------------------


def test_a_drawn_map_is_refused_before_any_model_runs():
    """Found by running a tree model over OpenStreetMap tiles: one crown in a
    park full of them. The model was fine; the pixels were cartography."""
    with pytest.raises(RunRefused, match="drawn map"):
        check_imagery_kind("xyz", {"imagery_kind": "map"})


def test_an_undeclared_tile_service_is_refused_until_the_operator_says():
    with pytest.raises(RunRefused, match="photographs or a drawn map"):
        check_imagery_kind("xyz", {})


def test_a_declared_photographic_service_is_allowed():
    check_imagery_kind("xyz", {"imagery_kind": "photo"})


def test_satellite_sources_are_photographs_without_being_asked():
    for source in ("sentinel2", "naip", "cog", "upload", "mapillary"):
        check_imagery_kind(source, {})
