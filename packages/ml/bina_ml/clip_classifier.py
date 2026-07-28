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

from bina_ml import SIGN_CLASSES, UNKNOWN, Prediction

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
    def _loaded(self):
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            self._model_name, pretrained=self._pretrained
        )
        model.eval()
        tokenizer = open_clip.get_tokenizer(self._model_name)

        # One averaged text embedding per class, computed once.
        with torch.no_grad():
            class_embeddings = []
            for sign_class in SIGN_CLASSES:
                tokens = tokenizer(PROMPTS[sign_class])
                features = model.encode_text(tokens)
                features = features / features.norm(dim=-1, keepdim=True)
                averaged = features.mean(dim=0)
                class_embeddings.append(averaged / averaged.norm())
            text_matrix = torch.stack(class_embeddings)
        return model, preprocess, text_matrix

    def predict(self, image: Image) -> Prediction:
        model, preprocess, text_matrix = self._loaded
        tensor = preprocess(image.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            features = model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
            probabilities = (100.0 * features @ text_matrix.T).softmax(dim=-1)[0]

        best = int(probabilities.argmax())
        confidence = float(probabilities[best])
        if confidence < self._threshold:
            return Prediction(UNKNOWN, confidence, self.version)
        return Prediction(SIGN_CLASSES[best], confidence, self.version)
