# The pipeline

What happens between naming a street and seeing signs on a map.

## 1. Street to corridor

A street name is resolved through Nominatim, then its geometry is fetched from
Overpass. The centreline is buffered — 25 m by default — into a corridor, and that
polygon is the survey area.

Both lookups are proxied through the API rather than called from the browser: the
providers' usage policies require an identifying User-Agent and rate limiting,
neither of which a browser can be trusted to honour, and a direct call would leak the
operator's IP to a third party on every keystroke.

## 2. Corridor to tiles

The corridor is decomposed into tiles sized to the imagery provider's limits. Each
tile is fetched independently, so one failure does not lose the survey — it is
recorded against that tile and the survey finishes `partial`.

## 3. Tiles to detections

For each tile, Mapillary returns street-level images and the sign detections it has
already made. Mithra uses those detections as candidate locations rather than running
its own detector: the provider has already done detection at scale, and repeating it
would be slower and worse.

## 4. Detections to crops

Each detection carries a bounding box in image space. The crop is cut from the source
image and stored, because a classification without the picture it was made from
cannot be checked by a person.

Tile coordinates run top-left down; image coordinates run bottom-left up. Getting
that inversion wrong put every crop in the wrong place — it is now covered by a test,
because the failure is silent: you get crops, they are just of the wrong thing.

## 5. Crops to classes

Each crop is embedded with CLIP and classified. Anything below the confidence
threshold becomes `unknown` and enters the review queue rather than being counted as
a guess. See [model.md](model.md).

## 6. What the operator sees

Signs appear on the map as they are written, not at the end. A long survey should
fill in while it works rather than showing an empty rectangle for ten minutes.
