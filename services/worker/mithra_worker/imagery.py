"""Reading pixels for an area, whatever the imagery is.

One interface over four very different things: a tile service, a cloud-hosted
GeoTIFF, a STAC catalogue, and a file somebody uploaded. The pipeline should
not care which — it asks for an area at a resolution and gets an array back
with the transform that puts it on the Earth.

Everything here reads windows rather than whole scenes. A Sentinel-2 tile is
over a gigabyte; a run over one neighbourhood needs a few megabytes of it, and
the COG format exists precisely so that the difference is a range request.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

Bbox = tuple[float, float, float, float]


@dataclass
class Chip:
    """A piece of imagery, georeferenced.

    `data` is (bands, height, width) in the order the source provides. `bounds`
    is the geographic extent in EPSG:4326, so a detection's pixel coordinates
    can be turned back into a position on Earth without asking the source again.
    """

    data: object  # numpy array; typed loosely so importing this module is cheap
    bounds: Bbox
    gsd_m: float
    crs: str = "EPSG:4326"

    @property
    def width(self) -> int:
        return int(self.data.shape[-1])

    @property
    def height(self) -> int:
        return int(self.data.shape[-2])


class ImageryError(RuntimeError):
    """The imagery could not be read. Carries a reason a person can act on."""


def metres_per_degree_lon(latitude: float) -> float:
    """Longitude degrees shrink towards the poles; latitude degrees do not.

    Needed because an area is given in degrees and a resolution in metres, and
    at Mashhad's latitude a degree of longitude is about 20% shorter than at
    the equator. Ignoring this stretches every detection east-west.
    """
    return 111_320.0 * math.cos(math.radians(latitude))


def pixel_size_for(bbox: Bbox, gsd_m: float) -> tuple[int, int]:
    """How many pixels an area covers at a given resolution."""
    west, south, east, north = bbox
    mid_lat = (south + north) / 2
    width_m = (east - west) * metres_per_degree_lon(mid_lat)
    height_m = (north - south) * 110_540.0
    return max(1, round(width_m / gsd_m)), max(1, round(height_m / gsd_m))


def read_cog(
    url: str,
    bbox: Bbox,
    max_size: int = 2048,
    width: int | None = None,
    height: int | None = None,
) -> Chip:
    """Read a window from a Cloud-Optimised GeoTIFF, local or remote.

    The file reports its own resolution; nothing here may claim one on its
    behalf, because a wrong GSD silently changes what the catalogue thinks is
    detectable.
    """
    from rio_tiler.io import Reader

    try:
        with Reader(url) as image:
            # An explicit grid when the caller has one: bands of a single
            # scene must land on the same pixels to be stacked.
            if width and height:
                part = image.part(bbox, dst_crs="EPSG:4326", width=width, height=height)
            else:
                part = image.part(bbox, dst_crs="EPSG:4326", max_size=max_size)
            # Ground resolution of what actually came back, not of the source's
            # best overview: rio-tiler may have decimated to honour max_size.
            west, south, east, north = bbox
            width_m = (east - west) * metres_per_degree_lon((south + north) / 2)
            gsd = width_m / max(1, part.width)
            return Chip(data=part.data, bounds=bbox, gsd_m=gsd)
    except Exception as exc:  # noqa: BLE001 - every failure has one outcome here
        raise ImageryError(f"could not read raster at {url}: {exc}") from exc


def read_upload(path: str | Path, bbox: Bbox | None = None, max_size: int = 2048) -> Chip:
    """Read an uploaded raster, optionally cropped to an area."""
    from rio_tiler.io import Reader

    path = str(path)
    if not Path(path).exists():
        raise ImageryError(f"uploaded raster is missing: {path}")

    try:
        with Reader(path) as image:
            if bbox is None:
                info = image.info()
                bbox = tuple(info.bounds)  # type: ignore[assignment]
            part = image.part(bbox, dst_crs="EPSG:4326", max_size=max_size)
            west, south, east, north = bbox  # type: ignore[misc]
            width_m = (east - west) * metres_per_degree_lon((south + north) / 2)
            return Chip(data=part.data, bounds=bbox, gsd_m=width_m / max(1, part.width))
    except ImageryError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageryError(f"could not read uploaded raster: {exc}") from exc


def read_xyz(
    template: str,
    bbox: Bbox,
    zoom: int,
    max_tiles: int = 256,
    timeout: float = 20.0,
    user_agent: str = "mithra/0.1 (urban feature survey)",
) -> Chip:
    """Mosaic a tile service over an area.

    Written out rather than delegated: rio-tiler reads rasters, not slippy-map
    tile pyramids, and an earlier version of this function imported a reader
    that does not exist — so the source was offered in the console and failed
    at run time.

    The zoom decides the resolution; `zoom_for_gsd` picks it from the
    resolution a run needs. Tiles are capped because an area at zoom 20 can be
    tens of thousands of requests, which is both slow and rude to the server.
    """
    import httpx
    import morecantile
    import numpy as np
    from PIL import Image

    for placeholder in ("{z}", "{x}", "{y}"):
        if placeholder not in template:
            raise ImageryError("tile template must contain {z}, {x} and {y}")

    tms = morecantile.tms.get("WebMercatorQuad")
    west, south, east, north = bbox
    tiles = list(tms.tiles(west, south, east, north, [zoom]))
    if not tiles:
        raise ImageryError("no tiles cover this area at that zoom")
    if len(tiles) > max_tiles:
        raise ImageryError(
            f"{len(tiles)} tiles needed at zoom {zoom}; the limit is {max_tiles}. "
            "Use a smaller area or a coarser resolution."
        )

    xs = [t.x for t in tiles]
    ys = [t.y for t in tiles]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    tile_size = 256
    canvas = Image.new("RGB", ((max_x - min_x + 1) * tile_size, (max_y - min_y + 1) * tile_size))

    headers = {"User-Agent": user_agent}
    fetched = 0
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        for tile in tiles:
            url = template.replace("{z}", str(tile.z)).replace("{x}", str(tile.x)).replace(
                "{y}", str(tile.y)
            )
            try:
                response = client.get(url)
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content)).convert("RGB")
            except Exception:  # noqa: BLE001
                # One missing tile is a hole in the mosaic, not a failed run:
                # tile services routinely have gaps, and refusing the whole
                # area because of one 404 would be worse than a black square.
                continue
            canvas.paste(image, ((tile.x - min_x) * tile_size, (tile.y - min_y) * tile_size))
            fetched += 1

    if fetched == 0:
        raise ImageryError(f"no tiles could be fetched from {template}")

    # The mosaic covers whole tiles, so its bounds are the tile grid's bounds
    # rather than the requested box. Reporting the real extent keeps every
    # detection's coordinates honest.
    top_left = tms.bounds(morecantile.Tile(min_x, min_y, zoom))
    bottom_right = tms.bounds(morecantile.Tile(max_x, max_y, zoom))
    mosaic_bounds = (top_left.left, bottom_right.bottom, bottom_right.right, top_left.top)

    data = np.asarray(canvas).transpose(2, 0, 1)
    width_m = (mosaic_bounds[2] - mosaic_bounds[0]) * metres_per_degree_lon(
        (mosaic_bounds[1] + mosaic_bounds[3]) / 2
    )
    return Chip(data=data, bounds=mosaic_bounds, gsd_m=width_m / max(1, data.shape[-1]))


def zoom_for_gsd(gsd_m: float, latitude: float = 0.0) -> int:
    """The web-mercator zoom whose pixels are closest to a target resolution."""
    # 156543.03 m/px is zoom 0 at the equator; each zoom halves it.
    equator = 156_543.03392 * math.cos(math.radians(latitude))
    return max(0, min(22, round(math.log2(equator / gsd_m))))


def search_stac(
    collection: str,
    bbox: Bbox,
    start: str,
    end: str,
    api_url: str = "https://earth-search.aws.element84.com/v1",
    max_cloud: int = 20,
    limit: int = 12,
) -> list[dict]:
    """Find scenes covering an area in a time window.

    Returns the least cloudy first, because for a single-date detection run the
    cloudiest scene is not a fallback — it is a different answer.
    """
    from pystac_client import Client

    try:
        client = Client.open(api_url)
        search = client.search(
            collections=[collection],
            bbox=list(bbox),
            datetime=f"{start}/{end}",
            query={"eo:cloud_cover": {"lt": max_cloud}},
            max_items=limit,
        )
        items = list(search.items())
    except Exception as exc:  # noqa: BLE001
        raise ImageryError(f"STAC search failed: {exc}") from exc

    items.sort(key=lambda i: i.properties.get("eo:cloud_cover", 100))
    return [
        {
            "id": item.id,
            "datetime": str(item.properties.get("datetime")),
            "cloud_cover": item.properties.get("eo:cloud_cover"),
            "assets": {k: v.href for k, v in item.assets.items()},
        }
        for item in items
    ]


def read_stac_scene(scene: dict, bbox: Bbox, bands: tuple[str, ...] = ("red", "green", "blue"),
                    max_size: int = 2048) -> Chip:
    """Read one scene's bands over an area, onto a single grid.

    Sentinel-2 does not deliver its bands at one resolution: red and
    near-infrared are 10 m, short-wave infrared is 20 m. Read independently
    they come back different sizes and cannot be stacked — and worse, a naive
    stack that happened to work would silently misalign every pixel.

    So the first band sets the grid and the rest are resampled onto it. The
    reported resolution is the grid's, not the sharpest band's, because that is
    what the detector actually sees.
    """
    import numpy as np

    arrays = []
    grid: tuple[int, int] | None = None
    gsd = None

    for band in bands:
        href = scene["assets"].get(band)
        if href is None:
            raise ImageryError(f"scene {scene.get('id')} has no band {band!r}")

        if grid is None:
            chip = read_cog(href, bbox, max_size=max_size)
            grid = (chip.width, chip.height)
            gsd = chip.gsd_m
        else:
            chip = read_cog(href, bbox, width=grid[0], height=grid[1])

        arrays.append(chip.data[0] if chip.data.ndim == 3 else chip.data)

    return Chip(data=np.stack(arrays), bounds=bbox, gsd_m=gsd or 0.0)
