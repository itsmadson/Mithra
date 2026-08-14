import base64

import mapbox_vector_tile
import pytest

from mithra_worker.geometry import GeometryDecodeError, decode_detection_geometry

EXTENT = 4096


def encode(coords: list[tuple[int, int]]) -> str:
    """Build a base64 MVT payload the way Mapillary does."""
    tile = mapbox_vector_tile.encode(
        {
            "name": "mpy-or",
            "features": [
                {
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {},
                }
            ],
        },
        default_options={"extents": EXTENT},
    )
    return base64.b64encode(tile).decode()


def test_decodes_a_centered_square_to_pixel_bbox():
    # A square covering the middle half of the tile, in MVT units.
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode(
        [
            (quarter, quarter),
            (three_quarters, quarter),
            (three_quarters, three_quarters),
            (quarter, three_quarters),
            (quarter, quarter),
        ]
    )
    left, top, right, bottom = decode_detection_geometry(encoded, 4000, 2000)
    assert (right - left) == pytest.approx(2000, abs=8)
    assert (bottom - top) == pytest.approx(1000, abs=8)


def test_scales_with_image_dimensions():
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode(
        [
            (quarter, quarter),
            (three_quarters, quarter),
            (three_quarters, three_quarters),
            (quarter, three_quarters),
            (quarter, quarter),
        ]
    )
    small = decode_detection_geometry(encoded, 1000, 500)
    large = decode_detection_geometry(encoded, 2000, 1000)
    assert (large[2] - large[0]) == pytest.approx(2 * (small[2] - small[0]), abs=8)


def test_result_is_clamped_inside_the_image():
    encoded = encode([(0, 0), (EXTENT, 0), (EXTENT, EXTENT), (0, EXTENT), (0, 0)])
    left, top, right, bottom = decode_detection_geometry(encoded, 800, 600)
    assert left >= 0 and top >= 0
    assert right <= 800 and bottom <= 600


def test_returns_integers():
    encoded = encode([(100, 100), (300, 100), (300, 300), (100, 300), (100, 100)])
    assert all(isinstance(v, int) for v in decode_detection_geometry(encoded, 1024, 768))


def test_bbox_is_ordered_left_top_right_bottom():
    encoded = encode([(100, 100), (300, 100), (300, 300), (100, 300), (100, 100)])
    left, top, right, bottom = decode_detection_geometry(encoded, 1024, 768)
    assert left < right and top < bottom


def test_tile_y_axis_is_flipped_into_image_space():
    """Mapbox vector tile y increases upward; image y increases downward.

    Verified against a real Mapillary detection: a no-stopping feature whose tile
    geometry spans y 1849..1911 sits at image y 614..632 in a 1152px-tall
    image, which is (extent - y) scaled, not y scaled. Without the flip the
    crop landed on foliage and road surface, and the classifier scored those
    as traffic features.
    """
    # A box low in TILE space must land high in IMAGE space (near the bottom).
    encoded = encode([(100, 0), (300, 0), (300, 100), (100, 100), (100, 0)])
    _, top, _, bottom = decode_detection_geometry(encoded, 1000, 1000)
    assert top > 800, f"expected near the image bottom, got top={top}"
    assert bottom > top


def test_flip_matches_the_observed_real_detection():
    """The exact numbers from the live Mapillary detection used to diagnose this."""
    encoded = encode(
        [(2003, 1849), (2032, 1849), (2032, 1911), (2003, 1911), (2003, 1849)]
    )
    left, top, right, bottom = decode_detection_geometry(encoded, 2048, 1152)
    assert left == pytest.approx(1001, abs=2)
    assert right == pytest.approx(1017, abs=2)
    assert top == pytest.approx(614, abs=2)
    assert bottom == pytest.approx(632, abs=2)


def test_garbage_base64_raises_decode_error():
    with pytest.raises(GeometryDecodeError):
        decode_detection_geometry("not-valid-base64!!", 1024, 768)


def test_empty_geometry_raises_decode_error():
    encoded = base64.b64encode(
        mapbox_vector_tile.encode({"name": "mpy-or", "features": []})
    ).decode()
    with pytest.raises(GeometryDecodeError):
        decode_detection_geometry(encoded, 1024, 768)
