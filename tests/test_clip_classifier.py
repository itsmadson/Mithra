import pytest
from PIL import Image

from mithra_ml import SIGN_CLASSES, UNKNOWN
from mithra_ml.clip_classifier import PROMPTS, ClipZeroShotClassifier

torch = pytest.importorskip("torch")


def test_every_class_has_prompts_in_both_languages():
    for class_name in SIGN_CLASSES:
        assert class_name in PROMPTS
        prompts = PROMPTS[class_name]
        assert len(prompts) >= 2
        assert any(any("؀" <= ch <= "ۿ" for ch in p) for p in prompts), (
            f"{class_name} has no Persian prompt"
        )


def test_predict_returns_a_known_class_and_bounded_confidence():
    classifier = ClipZeroShotClassifier()
    prediction = classifier.predict(Image.new("RGB", (224, 224), (120, 140, 160)))
    assert prediction.class_name in (*SIGN_CLASSES, UNKNOWN)
    assert 0.0 <= prediction.confidence <= 1.0


def test_low_confidence_predictions_become_unknown():
    classifier = ClipZeroShotClassifier(threshold=1.1)  # nothing can clear this
    prediction = classifier.predict(Image.new("RGB", (224, 224)))
    assert prediction.class_name == UNKNOWN


def test_version_string_identifies_the_model():
    classifier = ClipZeroShotClassifier()
    assert "clip" in classifier.version.lower()
    assert classifier.predict(Image.new("RGB", (224, 224))).model_version == classifier.version


def test_grayscale_input_is_accepted():
    classifier = ClipZeroShotClassifier()
    assert classifier.predict(Image.new("L", (224, 224))).confidence >= 0.0
