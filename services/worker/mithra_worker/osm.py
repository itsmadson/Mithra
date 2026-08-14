"""Street lookup and geometry from OpenStreetMap.

A survey area is a street (معبر), not an abstract rectangle. That means two
lookups: Nominatim to turn what the operator typed into a candidate list, and
Overpass to fetch the actual centreline geometry of the chosen way so the scan
follows the road instead of a box around it.

Both are public, rate-limited services. Nominatim's policy requires a real
User-Agent and at most one request per second; Overpass rejects unbounded
queries. Both are honoured here.
"""

import time
from typing import Any

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"

USER_AGENT = "mithra/0.1 (urban feature survey; contact: operator)"

# Mashhad, as a viewbox to bias search results without hard-excluding others.
MASHHAD_VIEWBOX = "59.30,36.45,59.90,36.10"


class OsmError(Exception):
    """OpenStreetMap lookup failed."""


class StreetNotFound(OsmError):
    """The chosen way has no usable centreline geometry."""


def _client(timeout: float = 30.0, proxy: str | None = None) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, proxy=proxy)


def search_streets(
    query: str, limit: int = 8, proxy: str | None = None
) -> list[dict[str, Any]]:
    """Return candidate streets for a free-text query, Persian or Latin.

    Restricted to ways: a survey follows a centreline, and a Nominatim node or
    relation has none. `namedetails` is requested so the Persian name can be
    shown even when the display name comes back transliterated.
    """
    with _client(proxy=proxy) as client:
        response = client.get(
            NOMINATIM,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": limit * 3,
                "addressdetails": 1,
                "namedetails": 1,
                "viewbox": MASHHAD_VIEWBOX,
                "bounded": 0,
            },
        )
    if response.status_code != 200:
        raise OsmError(f"Nominatim returned HTTP {response.status_code}")

    results = []
    for item in response.json():
        if item.get("osm_type") != "way":
            continue
        names = item.get("namedetails") or {}
        results.append(
            {
                "osm_id": int(item["osm_id"]),
                "osm_type": item["osm_type"],
                "display_name": item.get("display_name", ""),
                "name": names.get("name") or item.get("name") or "",
                "name_fa": names.get("name:fa") or "",
                "name_en": names.get("name:en") or "",
                "category": item.get("category", ""),
                "type": item.get("type", ""),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "boundingbox": [float(v) for v in item.get("boundingbox", [])],
            }
        )
        if len(results) >= limit:
            break
    return results


def fetch_way_geometry(
    osm_id: int, proxy: str | None = None, retries: int = 3
) -> list[tuple[float, float]]:
    """Return the centreline of one OSM way as [(lon, lat), ...].

    Overpass is frequently busy and answers 429 or 504 rather than failing
    outright, so a short backoff is part of normal operation here.
    """
    query = f"[out:json][timeout:60];way({osm_id});out geom;"
    last = ""
    for attempt in range(retries):
        with _client(timeout=90.0, proxy=proxy) as client:
            response = client.post(OVERPASS, data={"data": query})
        if response.status_code == 200:
            elements = response.json().get("elements", [])
            for element in elements:
                geometry = element.get("geometry")
                if geometry:
                    return [(float(p["lon"]), float(p["lat"])) for p in geometry]
            raise StreetNotFound(f"way {osm_id} returned no geometry")
        last = f"HTTP {response.status_code}"
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))
    raise OsmError(f"Overpass failed for way {osm_id}: {last}")


def fetch_named_street_geometry(
    name: str, around_lat: float, around_lon: float, radius_m: int = 1500,
    proxy: str | None = None,
) -> list[list[tuple[float, float]]]:
    """Return every way segment carrying `name` near a point.

    A named street in OSM is almost never one way — it is split at junctions,
    bridges and surface changes. Surveying only the way Nominatim happened to
    return would cover a fraction of the street the operator meant.
    """
    escaped = name.replace('"', '\\"')
    query = (
        f'[out:json][timeout:90];'
        f'way(around:{radius_m},{around_lat},{around_lon})'
        f'["highway"]["name"="{escaped}"];out geom;'
    )
    with _client(timeout=120.0, proxy=proxy) as client:
        response = client.post(OVERPASS, data={"data": query})
    if response.status_code != 200:
        raise OsmError(f"Overpass returned HTTP {response.status_code}")

    segments = []
    for element in response.json().get("elements", []):
        geometry = element.get("geometry")
        if geometry:
            segments.append([(float(p["lon"]), float(p["lat"])) for p in geometry])
    if not segments:
        raise StreetNotFound(f"no ways named {name!r} within {radius_m} m")
    return segments
