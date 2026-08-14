from dataclasses import dataclass
from typing import Protocol

from PIL.Image import Image

SIGN_CLASSES: tuple[str, ...] = (
    "direction_guide",
    "street_name",
    "city_entry",
    "informational",
)
UNKNOWN = "unknown"
ALL_CLASSES: tuple[str, ...] = SIGN_CLASSES + (UNKNOWN,)


@dataclass(frozen=True)
class Prediction:
    class_name: str
    confidence: float
    model_version: str


class Classifier(Protocol):
    version: str

    def predict(self, image: Image) -> Prediction: ...
