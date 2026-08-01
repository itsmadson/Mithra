"""Street lookup for the survey composer.

Proxied through the API rather than called from the browser: Nominatim's usage
policy requires an identifying User-Agent and rate limiting, neither of which a
browser client can be trusted to honour, and the browser would leak the
operator's IP to a third party on every keystroke.
"""

from fastapi import APIRouter, HTTPException, Query

from bina_worker.osm import OsmError, search_streets

router = APIRouter(prefix="/api/streets", tags=["streets"])


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
) -> dict:
    try:
        results = search_streets(q, limit=limit)
    except OsmError as exc:
        raise HTTPException(status_code=502, detail=f"street lookup failed: {exc}") from exc
    return {"items": results}
