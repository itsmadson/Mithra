"""Zero-shot sign classification with CLIP.

This exists so the product works on day one, before any labels are collected.
Prompts are bilingual because the signs carry Persian text and CLIP's Persian
grounding, while weaker than its English grounding, still contributes signal.
Everything below the confidence threshold becomes `unknown` and goes to the
top of the labeling queue — that queue is how this gets replaced by a
fine-tuned head.
"""

import functools

import torch
from PIL.Image import Image

from mithra_ml import SIGN_CLASSES, UNKNOWN, Prediction

PROMPTS: dict[str, list[str]] = {
    "direction_guide": [
        "a road direction sign with arrows pointing to destinations",
        "a green or blue highway guide sign showing place names",
        "تابلو مسیرنما با فلش و نام مقصد",
    ],
    "street_name": [
        "a street name plate mounted on a wall or pole",
        "a small rectangular sign showing the name of a street or alley",
        "تابلو نام معبر یا نام خیابان",
    ],
    "city_entry": [
        "a city entrance sign showing the name of a town",
        "a place name boundary sign at the edge of a city",
        "تابلو ورودی شهر با نام شهر",
    ],
    "informational": [
        "an information sign showing a service symbol like parking, hospital or fuel",
        "a blue service information sign with a pictogram",
        "تابلو اطلاعاتی خدمات مانند پارکینگ یا بیمارستان",
    ],
}


class ClipZeroShotClassifier:
    def __init__(
        self,
        threshold: float = 0.45,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
    ) -> None:
        self._threshold = threshold
        self._model_name = model_name
        self._pretrained = pretrained
        self.version = f"clip-zeroshot-{model_name}-{pretrained}-v1"

    @functools.cached_property
    def _text_matrix(self):
        """One averaged text embedding per class, computed once."""
        from mithra_ml.encoder import encode_texts

        return torch.stack([encode_texts(PROMPTS[cls]) for cls in SIGN_CLASSES])

    def predict(self, image: Image) -> Prediction:
        from mithra_ml.encoder import encode_image

        # The same encoder the probe trains on, so the two are comparable.
        features = torch.from_numpy(encode_image(image)).unsqueeze(0)
        probabilities = (100.0 * features @ self._text_matrix.T).softmax(dim=-1)[0]

        best = int(probabilities.argmax())
        confidence = float(probabilities[best])
        if confidence < self._threshold:
            return Prediction(UNKNOWN, confidence, self.version)
        return Prediction(SIGN_CLASSES[best], confidence, self.version)
