"""The CLIP image encoder, loaded once and shared.

Both the zero-shot classifier and the trained probe read the same frozen
features. Loading CLIP twice would double the memory of a worker that already
holds a model, and — worse — a probe trained on one encoder's features and
served by another would be silently wrong, so there is exactly one.
"""

import functools

import numpy as np
import torch
from PIL.Image import Image

MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"

# Identifies which features a set of probe weights was trained on. A probe is
# only valid against the encoder that produced its training features, so this
# is stored with the weights and checked on load.
ENCODER_VERSION = f"clip-{MODEL_NAME}-{PRETRAINED}"


@functools.cache
def _loaded():
    import open_clip

    model, _, preprocess = open_clip.create_model_and_transforms(
        MODEL_NAME, pretrained=PRETRAINED
    )
    model.eval()
    tokenizer = open_clip.get_tokenizer(MODEL_NAME)
    return model, preprocess, tokenizer


def embedding_dim() -> int:
    return 512


def encode_image(image: Image) -> np.ndarray:
    """One L2-normalised feature vector for one crop."""
    model, preprocess, _ = _loaded()
    tensor = preprocess(image.convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        features = model.encode_image(tensor)
        features = features / features.norm(dim=-1, keepdim=True)
    return features[0].cpu().numpy().astype(np.float32)


def encode_images(images: list[Image]) -> np.ndarray:
    """A batch, for training. Same normalisation as the single-image path."""
    model, preprocess, _ = _loaded()
    if not images:
        return np.zeros((0, embedding_dim()), dtype=np.float32)
    batch = torch.stack([preprocess(image.convert("RGB")) for image in images])
    with torch.no_grad():
        features = model.encode_image(batch)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype(np.float32)


def encode_texts(prompts: list[str]) -> torch.Tensor:
    """Averaged, normalised text embedding for a list of prompts for one class."""
    model, _, tokenizer = _loaded()
    with torch.no_grad():
        features = model.encode_text(tokenizer(prompts))
        features = features / features.norm(dim=-1, keepdim=True)
        averaged = features.mean(dim=0)
    return averaged / averaged.norm()
