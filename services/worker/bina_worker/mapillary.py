"""HTTP access to the Mapillary graph API.

Knows about auth, proxying, and retry. Knows nothing about signs, jobs, or
the database — callers interpret the payloads.
"""

import os
import time
from typing import Any

import httpx

from bina_worker.tiler import Bbox

GRAPH = "https://graph.mapillary.com"

FEATURE_FIELDS = "id,object_value,object_type,geometry,images,first_seen_at,last_seen_at"
DETECTION_FIELDS = "id,geometry,value"
IMAGE_FIELDS = "id,width,height,thumb_2048_url,captured_at,geometry"

RETRY_STATUSES = {429, 500, 502, 503, 504}


class MapillaryError(Exception):
    """Base for all Mapillary transport failures."""


class MapillaryAuthError(MapillaryError):
    """Credentials rejected. Never retried."""


class MapillaryRateLimited(MapillaryError):
    """Rate limited beyond the retry budget."""


class MapillaryClient:
    def __init__(
        self,
        token: str,
        *,
        max_retries: int = 4,
        backoff_base: float = 1.0,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._client = httpx.Client(
            headers={"Authorization": f"OAuth {token}"},
            timeout=timeout,
            proxy=proxy if proxy is not None else os.environ.get("HTTPS_PROXY"),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MapillaryClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        last_status = None
        for attempt in range(self._max_retries):
            response = self._client.get(f"{GRAPH}{path}", params=params)
            if response.status_code in (401, 403):
                # Deliberately does not echo the response body, which can
                # contain the submitted token.
                raise MapillaryAuthError(
                    f"Mapillary rejected credentials (HTTP {response.status_code}) for {path}"
                )
            if response.status_code in RETRY_STATUSES:
                last_status = response.status_code
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2**attempt))
                continue
            response.raise_for_status()
            return response.json()
        raise MapillaryRateLimited(
            f"Mapillary returned {last_status} for {path} after {self._max_retries} attempts"
        )

    def get_sign_features(self, bbox: Bbox, limit: int = 2000) -> list[dict]:
        west, south, east, north = bbox
        payload = self._get(
            "/map_features",
            {
                "bbox": f"{west},{south},{east},{north}",
                "object_types": "trafficsign",
                "fields": FEATURE_FIELDS,
                "limit": limit,
            },
        )
        return payload.get("data", [])

    def get_detections(self, image_id: str) -> list[dict]:
        payload = self._get(f"/{image_id}/detections", {"fields": DETECTION_FIELDS})
        return payload.get("data", [])

    def get_image_meta(self, image_id: str) -> dict:
        return self._get(f"/{image_id}", {"fields": IMAGE_FIELDS})

    def download(self, url: str) -> bytes:
        response = self._client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content
