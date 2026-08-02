"""Turn a street centreline into something the scanner can query.

Mapillary is queried by bbox, so a street survey still ends in rectangles — but
the rectangles should follow the road rather than enclose the whole city block
grid around it, and a sign three streets away that happens to fall inside a
tile must not be counted as belonging to this street.

Distances are computed in a local equirectangular projection, metres on both
axes, which is accurate well past city scale and avoids a projection dependency.
"""

import math

from shapely.geometry import LineString, MultiLineString, Point, mapping
from shapely.ops import unary_union

from mithra_worker.tiler import Bbox, split_bbox

EARTH_M_PER_DEG = 111_320.0

Segment = list[tuple[float, float]]


def _projector(lat0: float):
    """Local metric projection about lat0: degrees in, metres out."""
    k = math.cos(math.radians(lat0))

    def to_m(lon: float, lat: float) -> tuple[float, float]:
        return (lon * k * EARTH_M_PER_DEG, lat * EARTH_M_PER_DEG)

    return to_m


def centreline(segments: list[Segment]) -> MultiLineString:
    lines = [LineString(s) for s in segments if len(s) >= 2]
    if not lines:
        raise ValueError("street has no usable segments")
    return MultiLineString(lines)


def corridor_bbox(segments: list[Segment], buffer_m: float) -> Bbox:
    """The smallest bbox containing the street plus its buffer."""
    line = centreline(segments)
    west, south, east, north = line.bounds
    lat0 = (south + north) / 2
    pad_lat = buffer_m / EARTH_M_PER_DEG
    pad_lon = buffer_m / (EARTH_M_PER_DEG * max(math.cos(math.radians(lat0)), 1e-6))
    return (west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat)


def corridor_tiles(segments: list[Segment], buffer_m: float) -> list[Bbox]:
    """Mapillary-legal tiles that intersect the buffered street.

    Tiles that touch no part of the corridor are dropped, which is the whole
    point: a long street produces a wide bounding box that is mostly not the
    street, and querying all of it would be slow and would pull in signs that
    belong to other roads.
    """
    line = centreline(segments)
    lat0 = (line.bounds[1] + line.bounds[3]) / 2
    to_m = _projector(lat0)

    projected = unary_union(
        [LineString([to_m(x, y) for x, y in seg.coords]) for seg in line.geoms]
    )
    buffered = projected.buffer(buffer_m)

    kept: list[Bbox] = []
    for tile in split_bbox(corridor_bbox(segments, buffer_m)):
        w, s, e, n = tile
        corners = [to_m(w, s), to_m(e, s), to_m(e, n), to_m(w, n)]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        box = LineString(
            [
                (min(xs), min(ys)),
                (max(xs), min(ys)),
                (max(xs), max(ys)),
                (min(xs), max(ys)),
                (min(xs), min(ys)),
            ]
        ).envelope
        if buffered.intersects(box):
            kept.append(tile)
    return kept


def within_corridor(
    segments: list[Segment], buffer_m: float, lon: float, lat: float
) -> bool:
    """Is this sign close enough to the street to belong to it?"""
    line = centreline(segments)
    lat0 = (line.bounds[1] + line.bounds[3]) / 2
    to_m = _projector(lat0)
    projected = unary_union(
        [LineString([to_m(x, y) for x, y in seg.coords]) for seg in line.geoms]
    )
    return projected.distance(Point(*to_m(lon, lat))) <= buffer_m


def corridor_geojson(segments: list[Segment]) -> dict:
    """The centreline as GeoJSON, for storage and for drawing on the map."""
    return mapping(centreline(segments))
