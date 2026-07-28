"""Decode Mapillary detection geometry into a pixel bounding box.

Mapillary encodes each detection outline as a base64 Mapbox vector tile whose
coordinates run 0..extent (4096). Normalising by the extent and multiplying by
the real image dimensions maps them back onto image pixels.
"""

import base64

import mapbox_vector_tile

DEFAULT_EXTENT = 4096


class GeometryDecodeError(Exception):
    """The detection geometry could not be decoded into a usable bbox."""


def _iter_points(geometry: dict):
    coords = geometry.get("coordinates", [])
    stack = [coords]
    while stack:
        item = stack.pop()
        if not isinstance(item, (list, tuple)) or not item:
            continue
        if len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
            yield float(item[0]), float(item[1])
        else:
            stack.extend(item)


def decode_detection_geometry(
    encoded: str, image_width: int, image_height: int
) -> tuple[int, int, int, int]:
    try:
        tile = mapbox_vector_tile.decode(base64.b64decode(encoded, validate=True))
    except Exception as exc:  # noqa: BLE001 - any malformed payload is one failure mode
        raise GeometryDecodeError(f"could not decode detection geometry: {exc}") from exc

    points: list[tuple[float, float]] = []
    extent = DEFAULT_EXTENT
    for layer in tile.values():
        extent = layer.get("extent", DEFAULT_EXTENT) or DEFAULT_EXTENT
        for feature in layer.get("features", []):
            points.extend(_iter_points(feature.get("geometry", {})))

    if not points:
        raise GeometryDecodeError("detection geometry contained no coordinates")

    xs = [p[0] / extent * image_width for p in points]
    ys = [p[1] / extent * image_height for p in points]

    left = max(0, int(min(xs)))
    top = max(0, int(min(ys)))
    right = min(image_width, int(max(xs)) + 1)
    bottom = min(image_height, int(max(ys)) + 1)

    if right <= left or bottom <= top:
        raise GeometryDecodeError("detection geometry produced an empty bbox")
    return left, top, right, bottom
