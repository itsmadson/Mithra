"""Answer the blocking question: does Mashhad have usable Mapillary feature coverage?

Usage: MAPILLARY_TOKEN=... python scripts/check_coverage.py
"""

import os
import sys
from collections import Counter

import httpx

# Central Mashhad, one Mapillary-legal tile (< 0.01 deg square).
BBOX = "59.600,36.293,59.609,36.302"
GRAPH = "https://graph.mapillary.com"


def main() -> int:
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        print("MAPILLARY_TOKEN not set", file=sys.stderr)
        return 2

    client = httpx.Client(
        headers={"Authorization": f"OAuth {token}"},
        timeout=30.0,
        proxy=os.environ.get("HTTPS_PROXY"),
    )

    imgs = client.get(
        f"{GRAPH}/images", params={"bbox": BBOX, "limit": 100, "fields": "id,captured_at"}
    )
    print(f"images: HTTP {imgs.status_code}")
    if imgs.status_code != 200:
        print(imgs.text[:500])
        return 1
    image_data = imgs.json().get("data", [])
    print(f"images found: {len(image_data)}")

    feats = client.get(
        f"{GRAPH}/map_features",
        params={
            "bbox": BBOX,
            "limit": 500,
            "object_types": "trafficsign",
            "fields": "id,object_value,geometry",
        },
    )
    print(f"map_features: HTTP {feats.status_code}")
    if feats.status_code != 200:
        print(feats.text[:500])
        return 1
    features = feats.json().get("data", [])
    print(f"feature features found: {len(features)}")

    counts = Counter(f.get("object_value", "?").split("--")[0] for f in features)
    for category, n in counts.most_common():
        print(f"  {category}: {n}")

    if not features:
        print(
            "\nVERDICT: no feature coverage in this tile. "
            "Widen the probe or reconsider imagery source."
        )
        return 1
    print("\nVERDICT: coverage exists. Proceed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
