"""Individual tree crowns, from RGB imagery.

DeepForest is trained on NEON airborne imagery for exactly this: one box per
crown, from ordinary three-band imagery, on a CPU. It scores around 70% on the
NEON crowns benchmark — worse than a GPU-tuned SAM variant and far better than
a general-purpose model that was never shown a tree.

It needs photographs. Run it on a cartographic basemap and it finds nothing,
which is not a bug in the model: there are no trees in a drawing of a park,
only green polygons.
"""

from __future__ import annotations

from mithra_ml.detect import Detection

# Below this the boxes are mostly texture. DeepForest's scores on aerial
# imagery run low — a median around 0.17 on real crowns — so a threshold tuned
# for a photograph of a single tree would return nothing here.
MIN_SCORE = 0.15

# Tiles the sliding window uses. 400 px matches the training patch size; larger
# is faster and starts missing small crowns.
PATCH_SIZE = 400
PATCH_OVERLAP = 0.15


class DeepForestDetector:
    key = "deepforest"
    version = "deepforest-neon"
    targets = frozenset({"tree"})

    def __init__(self, min_score: float = MIN_SCORE) -> None:
        self._min_score = min_score
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from deepforest import main as deepforest_main
        except ImportError as exc:
            raise RuntimeError(
                "deepforest is not installed in this image; add it to run tree detection"
            ) from exc

        model = deepforest_main.deepforest()
        model.load_model("weecology/deepforest-tree")
        self._model = model
        return model

    def detect(self, chip, targets: list[str]) -> list[Detection]:
        """One detection per crown, as a polygon in EPSG:4326."""
        import numpy as np

        if "tree" not in targets:
            return []

        data = np.asarray(chip.data)
        if data.ndim != 3 or data.shape[0] < 3:
            raise ValueError("tree detection needs a three-band RGB image")

        # DeepForest wants height-width-channel uint8, which is not how a
        # raster arrives.
        image = data[:3].transpose(1, 2, 0)
        if image.dtype != np.uint8:
            top = float(image.max()) or 1.0
            image = (image / top * 255).astype("uint8")

        model = self._load()
        boxes = model.predict_tile(
            image=np.ascontiguousarray(image),
            patch_size=PATCH_SIZE,
            patch_overlap=PATCH_OVERLAP,
        )
        if boxes is None or len(boxes) == 0:
            return []

        west, south, east, north = chip.bounds
        height, width = image.shape[0], image.shape[1]
        lon_per_px = (east - west) / max(1, width)
        lat_per_px = (north - south) / max(1, height)
        pixel_area_m2 = chip.gsd_m * chip.gsd_m

        detections: list[Detection] = []
        for row in boxes.itertuples():
            score = float(getattr(row, "score", 0.0))
            if score < self._min_score:
                continue

            # Pixel rows count downwards from the north edge; latitude counts
            # upwards. Getting this backwards mirrors every crown across the
            # scene, which looks plausible until someone checks one.
            x0, y0 = float(row.xmin), float(row.ymin)
            x1, y1 = float(row.xmax), float(row.ymax)
            lon0, lon1 = west + x0 * lon_per_px, west + x1 * lon_per_px
            lat0, lat1 = north - y1 * lat_per_px, north - y0 * lat_per_px

            detections.append(
                Detection(
                    class_name="tree",
                    geometry={
                        "type": "Polygon",
                        "coordinates": [[
                            [lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0],
                        ]],
                    },
                    confidence=score,
                    area_m2=round((x1 - x0) * (y1 - y0) * pixel_area_m2, 1),
                    properties={"model": self.version},
                )
            )

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections
