import pytest

from mithra_worker.corridor import (
    corridor_bbox,
    corridor_geojson,
    corridor_tiles,
    within_corridor,
)

# A short east-west street in central Mashhad, roughly 900 m long.
STREET = [[(59.600, 36.2970), (59.605, 36.2971), (59.610, 36.2972)]]

# Two parallel streets one block apart, the case that matters most: a survey of
# one must not silently count the other's features.
TWO_STREETS = [
    [(59.600, 36.2970), (59.610, 36.2970)],
    [(59.600, 36.3000), (59.610, 36.3000)],
]


def test_bbox_contains_the_street_plus_the_buffer():
    west, south, east, north = corridor_bbox(STREET, buffer_m=25)
    assert west < 59.600 and east > 59.610
    assert south < 36.2970 and north > 36.2972


def test_every_tile_is_mapillary_legal():
    for w, s, e, n in corridor_tiles(STREET, buffer_m=25):
        assert e - w < 0.01
        assert n - s < 0.01


def test_tiles_cover_the_street():
    tiles = corridor_tiles(STREET, buffer_m=25)
    assert tiles
    for lon in (59.6005, 59.6050, 59.6095):
        assert any(w <= lon <= e and s <= 36.2971 <= n for w, s, e, n in tiles), lon


def test_a_point_on_the_street_is_inside_the_corridor():
    assert within_corridor(STREET, 25, 59.6050, 36.29710)


def test_a_point_a_block_away_is_outside_the_corridor():
    # ~330 m north of the street.
    assert not within_corridor(STREET, 25, 59.6050, 36.3000)


def test_buffer_width_is_metric_and_symmetric():
    # 30 m north of the centreline: outside a 25 m buffer, inside a 60 m one.
    lat = 36.2971 + 30 / 111_320
    assert not within_corridor(STREET, 25, 59.6050, lat)
    assert within_corridor(STREET, 60, 59.6050, lat)


def test_corridor_of_one_street_excludes_the_parallel_street():
    first, second = [TWO_STREETS[0]], [TWO_STREETS[1]]
    midpoint_of_second = (59.605, 36.3000)
    assert not within_corridor(first, 25, *midpoint_of_second)
    assert within_corridor(second, 25, *midpoint_of_second)


def test_tiles_skip_empty_space_between_disjoint_segments():
    """A street split far apart must not drag in every tile between the parts."""
    far_apart = [
        [(59.600, 36.2970), (59.602, 36.2970)],
        [(59.640, 36.2970), (59.642, 36.2970)],
    ]
    covering = corridor_tiles(far_apart, buffer_m=25)
    whole_bbox_tiles = corridor_tiles([[(59.600, 36.2970), (59.642, 36.2970)]], 25)
    assert len(covering) < len(whole_bbox_tiles)


def test_geojson_is_a_multilinestring():
    geo = corridor_geojson(STREET)
    assert geo["type"] == "MultiLineString"
    assert geo["coordinates"][0][0] == pytest.approx([59.600, 36.2970])


def test_street_with_no_usable_segment_raises():
    with pytest.raises(ValueError):
        corridor_bbox([[(59.6, 36.3)]], buffer_m=25)
