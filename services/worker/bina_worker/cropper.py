"""Cut a detected sign out of its source image.

Padding matters: a sign cropped exactly to its detection outline loses the
border and backing plate, which are strong signals for distinguishing a
street-name plate from a direction sign.
"""

import io

from PIL import Image, UnidentifiedImageError

from bina_worker.geometry import GeometryDecodeError, decode_detection_geometry


class CropError(Exception):
    """The detection could not be cropped out of its source image."""


def crop_detection(
    image_bytes: bytes,
    encoded_geometry: str,
    image_width: int,
    image_height: int,
    padding: float = 0.10,
) -> Image.Image:
    try:
        left, top, right, bottom = decode_detection_geometry(
            encoded_geometry, image_width, image_height
        )
    except GeometryDecodeError as exc:
        raise CropError(str(exc)) from exc

    pad_x = int((right - left) * padding)
    pad_y = int((bottom - top) * padding)
    box = (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(image_width, right + pad_x),
        min(image_height, bottom + pad_y),
    )

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CropError(f"could not open source image: {exc}") from exc

    return image.convert("RGB").crop(box)
