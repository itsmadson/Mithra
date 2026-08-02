"""The encoder both models share.

These load real CLIP weights, so they are skipped where torch is unavailable.
The property worth testing is not that CLIP works — it is that the batch path
used for training and the single-image path used for serving produce the same
vector. If they ever diverge, a probe would be trained on one feature space and
served from another, and nothing downstream would notice.
"""

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("torch")

from mithra_ml.encoder import ENCODER_VERSION, embedding_dim, encode_image, encode_images


def test_an_embedding_has_the_expected_shape_and_is_normalised():
    vector = encode_image(Image.new("RGB", (120, 80), (40, 90, 160)))
    assert vector.shape == (embedding_dim(),)
    assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-4)


def test_the_batch_path_matches_the_single_image_path():
    """Training encodes in batches; serving encodes one crop at a time."""
    images = [
        Image.new("RGB", (120, 80), (40, 90, 160)),
        Image.new("RGB", (60, 60), (200, 180, 40)),
    ]
    batch = encode_images(images)
    assert batch.shape == (2, embedding_dim())
    for index, image in enumerate(images):
        assert np.allclose(encode_image(image), batch[index], atol=1e-5)


def test_an_empty_batch_is_shaped_not_empty():
    """So a caller can concatenate without special-casing the last chunk."""
    assert encode_images([]).shape == (0, embedding_dim())


def test_different_images_get_different_embeddings():
    a = encode_image(Image.new("RGB", (100, 100), (255, 0, 0)))
    b = encode_image(Image.new("RGB", (100, 100), (0, 0, 255)))
    assert not np.allclose(a, b)


def test_the_encoder_version_names_the_weights():
    """A probe stores this and refuses to load against a different build."""
    assert "ViT-B-32" in ENCODER_VERSION
    assert "laion2b" in ENCODER_VERSION
