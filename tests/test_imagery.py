"""Reading pixels for an area.

The geometry tests matter more than they look: an area is given in degrees and
a resolution in metres, and getting the conversion wrong stretches every
detection east-west without failing anything.
"""

import math

import pytest

from mithra_worker.imagery import (
    Chip,
    ImageryError,
    metres_per_degree_lon,
    pixel_size_for,
    read_cog,
    read_upload,
    read_xyz,
    zoom_for_gsd,
)


def test_a_longitude_degree_shrinks_towards_the_poles():
    """The bug this prevents is silent: everything just comes out stretched."""
    equator = metres_per_degree_lon(0.0)
    mashhad = metres_per_degree_lon(36.3)
    assert equator == pytest.approx(111_320, rel=0.01)
    assert mashhad < equator
    assert mashhad == pytest.approx(111_320 * math.cos(math.radians(36.3)), rel=0.01)


def test_pixel_size_follows_the_resolution():
    bbox = (59.60, 36.29, 59.61, 36.30)
    sharp = pixel_size_for(bbox, 0.3)
    coarse = pixel_size_for(bbox, 10.0)
    assert sharp[0] > coarse[0] * 20
    # One hundredth of a degree at this latitude is a bit under a kilometre.
    assert 800 < coarse[0] * 10 < 1000


def test_an_area_never_rounds_down_to_nothing():
    """A tiny bbox still has to produce a readable window."""
    width, height = pixel_size_for((59.600, 36.290, 59.6001, 36.2901), 10.0)
    assert width >= 1 and height >= 1


def test_zoom_matches_the_resolution_it_is_asked_for():
    """Zoom 19 is roughly 0.3 m per pixel; each step down doubles it."""
    assert zoom_for_gsd(0.3, 36.3) == 19
    assert zoom_for_gsd(0.6, 36.3) == 18
    assert zoom_for_gsd(10.0, 36.3) == 14


def test_a_tile_template_without_coordinates_is_refused():
    """Every tile would resolve to the same image and the map would repeat."""
    with pytest.raises(ImageryError, match=r"\{z\}"):
        read_xyz("https://tiles.example.com/map.png", (0, 0, 1, 1), zoom=15)


def test_a_missing_upload_says_so():
    with pytest.raises(ImageryError, match="missing"):
        read_upload("/nonexistent/raster.tif")


def test_an_unreadable_url_is_reported_not_swallowed():
    with pytest.raises(ImageryError, match="could not read"):
        read_cog("https://example.invalid/nope.tif", (0, 0, 0.01, 0.01))


def test_a_chip_reports_its_own_dimensions():
    import numpy as np

    chip = Chip(data=np.zeros((3, 40, 60), dtype="uint16"), bounds=(0, 0, 1, 1), gsd_m=10.0)
    assert (chip.width, chip.height) == (60, 40)
