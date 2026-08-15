"""SAM 3, behind the same contract as everything else.

Open-vocabulary segmentation: a text prompt in, polygons out, no training. It
is the only detector here that can answer a target nobody enumerated, which is
what makes "detect anything" a real claim rather than a slogan.

Honest about its state: this adapter is written against segment-geospatial's
documented interface and has NOT been exercised on a GPU host by the author.
It is registered as implemented because the code path is complete, and the
hardware probe refuses it on machines that cannot run it — so the failure mode
on a laptop is a clear refusal before the run, not a crash during it. The first
GPU deployment should run `scripts/check_sam.py` before trusting a count.
"""

from __future__ import annotations

from mithra_ml.detect import Detection

# Prompts are per target rather than the bare class name: "tree" alone also
# matches shrubs and shadow in overhead imagery, and the phrasing measurably
# changes what comes back.
PROMPTS: dict[str, str] = {
    "tree": "tree canopy",
    "building": "building rooftop",
    "water": "water body",
    "road": "road",
    "car": "car",
    "ship": "ship",
    "solar_panel": "solar panel array",
    "forest_cover": "forest",
    "built_up": "urban built-up area",
    "cropland": "agricultural field",
}

# Below this, a mask is noise rather than an object.
MIN_PIXELS = 12


class SamUnavailable(RuntimeError):
    """SAM is registered but cannot run here, with the reason."""


class Sam3Detector:
    key = "sam3"
    version = "sam3-text"
    targets = frozenset(PROMPTS)

    def __init__(self, threshold: float = 0.35, min_pixels: int = MIN_PIXELS) -> None:
        self._threshold = threshold
        self._min_pixels = min_pixels
        self._model = None

    def _load(self):
        """Load lazily: importing samgeo pulls in torch and the weights."""
        if self._model is not None:
            return self._model
        try:
            from samgeo.text_sam import LangSAM
        except ImportError as exc:
            raise SamUnavailable(
                "segment-geospatial is not installed in this image; "
                "install it on a GPU host to use SAM"
            ) from exc

        try:
            self._model = LangSAM()
        except Exception as exc:  # noqa: BLE001 - weights download, CUDA, disk
            raise SamUnavailable(f"SAM could not be loaded: {exc}") from exc
        return self._model

    def detect(self, chip, targets: list[str]) -> list[Detection]:
        """Segment each requested target and return one detection per region."""
        import numpy as np
        from PIL import Image
        from rasterio.features import shapes
        from rasterio.transform import from_bounds

        wanted = [t for t in targets if t in PROMPTS]
        if not wanted:
            return []

        model = self._load()

        data = np.asarray(chip.data)
        if data.ndim != 3 or data.shape[0] < 3:
            raise ValueError("SAM needs a three-band image")
        # samgeo works in PIL space; scale to 8-bit without clipping the
        # brightest pixels away, which would erase bright roofs and panels.
        rgb = data[:3].astype("float32")
        top = float(rgb.max()) or 1.0
        image = Image.fromarray((rgb / top * 255).astype("uint8").transpose(1, 2, 0))

        west, south, east, north = chip.bounds
        pixel_area_m2 = chip.gsd_m * chip.gsd_m
        detections: list[Detection] = []

        for target in wanted:
            try:
                masks, boxes, phrases, logits = model.predict(
                    image, PROMPTS[target], box_threshold=self._threshold,
                    text_threshold=self._threshold, return_results=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise SamUnavailable(f"SAM failed on {target!r}: {exc}") from exc

            if masks is None or len(masks) == 0:
                continue

            transform = from_bounds(
                west, south, east, north, image.width, image.height
            )
            for index, mask in enumerate(np.asarray(masks)):
                binary = (mask > 0).astype("uint8")
                pixels = int(binary.sum())
                if pixels < self._min_pixels:
                    continue

                confidence = float(logits[index]) if logits is not None and index < len(logits) else 0.5
                for geometry, value in shapes(
                    binary, mask=binary.astype(bool), transform=transform
                ):
                    if value != 1:
                        continue
                    detections.append(
                        Detection(
                            class_name=target,
                            geometry=geometry,
                            confidence=min(1.0, max(0.0, confidence)),
                            area_m2=round(pixels * pixel_area_m2, 1),
                            properties={"prompt": PROMPTS[target], "model": self.version},
                        )
                    )

        detections.sort(key=lambda d: d.area_m2 or 0, reverse=True)
        return detections
