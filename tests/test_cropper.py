import base64
import io

import mapbox_vector_tile
import pytest
from PIL import Image

from mithra_worker.cropper import CropError, crop_detection

EXTENT = 4096


def encode_box(x0: int, y0: int, x1: int, y1: int) -> str:
    tile = mapbox_vector_tile.encode(
        {
            "name": "mpy-or",
            "features": [
                {
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]],
                    },
                    "properties": {},
                }
            ],
        },
        default_options={"extents": EXTENT},
    )
    return base64.b64encode(tile).decode()


def make_image(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_returns_a_cropped_image():
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    crop = crop_detection(
        make_image(800, 600),
        encode_box(quarter, quarter, three_quarters, three_quarters),
        800,
        600,
        padding=0.0,
    )
    assert isinstance(crop, Image.Image)
    assert crop.width == pytest.approx(400, abs=4)
    assert crop.height == pytest.approx(300, abs=4)


def test_padding_expands_the_crop():
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode_box(quarter, quarter, three_quarters, three_quarters)
    tight = crop_detection(make_image(800, 600), encoded, 800, 600, padding=0.0)
    padded = crop_detection(make_image(800, 600), encoded, 800, 600, padding=0.25)
    assert padded.width > tight.width


def test_padding_is_clamped_at_the_image_edge():
    crop = crop_detection(
        make_image(800, 600), encode_box(0, 0, EXTENT, EXTENT), 800, 600, padding=0.5
    )
    assert crop.width <= 800
    assert crop.height <= 600


def test_crop_uses_the_downloaded_image_size_not_the_reported_one():
    """Mapillary's metadata width/height describe the ORIGINAL capture.

    We download thumb_2048_url, which is a scaled-down copy. Decoding the
    detection geometry against the original dimensions put the box outside the
    thumbnail, and PIL pads out-of-bounds crops with black rather than failing.
    That silently produced blank crops for 53 of 76 features in a real Mashhad
    run, and the classifier dutifully classified black rectangles.
    """
    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode_box(quarter, quarter, three_quarters, three_quarters)

    # The downloaded bytes are a 400x300 thumbnail of a 4000x3000 original.
    thumbnail = make_image(400, 300)
    crop = crop_detection(thumbnail, encoded, 4000, 3000, padding=0.0)

    assert crop.width <= 400
    assert crop.height <= 300
    assert crop.width == pytest.approx(200, abs=4)
    assert crop.height == pytest.approx(150, abs=4)


def test_crop_of_a_uniform_image_is_not_blank_padding():
    """A crop inside the image must carry the image's pixels, not black padding."""
    from PIL import ImageStat

    quarter, three_quarters = EXTENT // 4, EXTENT * 3 // 4
    encoded = encode_box(quarter, quarter, three_quarters, three_quarters)
    crop = crop_detection(make_image(400, 300), encoded, 4000, 3000, padding=0.0)
    # make_image paints a uniform (10, 20, 30); black padding would read 0.
    assert ImageStat.Stat(crop.convert("L")).mean[0] > 5


def test_corrupt_image_bytes_raise_crop_error():
    with pytest.raises(CropError):
        crop_detection(b"not an image", encode_box(100, 100, 300, 300), 800, 600)


def test_undecodable_geometry_raises_crop_error():
    with pytest.raises(CropError):
        crop_detection(make_image(800, 600), "not-base64!!", 800, 600)
