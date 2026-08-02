"""Split a user bbox into Mapillary-legal tiles.

Mapillary requires every bbox query to be strictly smaller than 0.01 degrees
square. MAX_SIDE sits just under that so floating-point addition across many
tiles can never drift over the limit.
"""

import math

Bbox = tuple[float, float, float, float]  # west, south, east, north

MAX_SIDE = 0.009


def split_bbox(bbox: Bbox, max_side: float = MAX_SIDE) -> list[Bbox]:
    west, south, east, north = bbox
    if east <= west or north <= south:
        raise ValueError(f"bbox must have positive extent, got {bbox!r}")

    cols = math.ceil((east - west) / max_side)
    rows = math.ceil((north - south) / max_side)
    col_step = (east - west) / cols
    row_step = (north - south) / rows

    tiles: list[Bbox] = []
    for r in range(rows):
        for c in range(cols):
            tiles.append(
                (
                    west + c * col_step,
                    south + r * row_step,
                    west + (c + 1) * col_step if c < cols - 1 else east,
                    south + (r + 1) * row_step if r < rows - 1 else north,
                )
            )
    return tiles
