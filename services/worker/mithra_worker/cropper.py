"""Cut a detected feature out of its source image.

Padding matters: a feature cropped exactly to its detection outline loses the
border and backing plate, which are strong signals for distinguishing a
street-name plate from a direction feature.
"""

import io

from PIL import Image, UnidentifiedImageError

from mithra_worker.geometry import GeometryDecodeError, decode_detection_geometry


class CropError(Exception):
    """The detection could not be cropped out of its source image."""


def crop_detection(
    image_bytes: bytes,
    encoded_geometry: str,
    image_width: int | None = None,
    image_height: int | None = None,
    padding: float = 0.10,
) -> Image.Image:
    """Crop a detection out of image_bytes.

    image_width and image_height are accepted for call-site clarity but are
    deliberately NOT used to place the box. Detection geometry is normalised
    against the tile extent, so it must be scaled by the dimensions of the image
    actually being cropped. Mapillary's reported width/height describe the
    original capture, while we download a scaled thumbnail; using the reported
    values put every box outside the thumbnail, and PIL pads out-of-bounds
    crops with black instead of raising. The result was blank crops that the
    classifier then confidently classified.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CropError(f"could not open source image: {exc}") from exc

    actual_width, actual_height = image.size

    try:
        left, top, right, bottom = decode_detection_geometry(
            encoded_geometry, actual_width, actual_height
        )
    except GeometryDecodeError as exc:
        raise CropError(str(exc)) from exc

    pad_x = int((right - left) * padding)
    pad_y = int((bottom - top) * padding)
    box = (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(actual_width, right + pad_x),
        min(actual_height, bottom + pad_y),
    )

    return image.convert("RGB").crop(box)
