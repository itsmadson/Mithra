from PIL import Image

from mithra_ml import UNKNOWN, Prediction
from mithra_ml.registry import get_classifier, register_classifier, reset_registry


class FakeClassifier:
    version = "fake-v1"

    def predict(self, image):
        return Prediction(
            class_name="street_name", confidence=0.9, model_version=self.version
        )


def test_registry_returns_the_registered_classifier():
    reset_registry()
    register_classifier(FakeClassifier())
    assert get_classifier().version == "fake-v1"


def test_registry_returns_the_same_instance_each_call():
    reset_registry()
    register_classifier(FakeClassifier())
    assert get_classifier() is get_classifier()


def test_prediction_carries_the_model_version():
    reset_registry()
    register_classifier(FakeClassifier())
    prediction = get_classifier().predict(Image.new("RGB", (32, 32)))
    assert prediction.model_version == "fake-v1"
    assert prediction.class_name != UNKNOWN


def test_a_configured_probe_is_served_instead_of_zero_shot(tmp_path, monkeypatch):
    """Promotion is a deployment decision: point the variable at a file."""
    import numpy as np

    from mithra_ml import SIGN_CLASSES
    from mithra_ml.probe import ProbeWeights, save
    from mithra_ml.registry import get_classifier, reset_registry

    weights = ProbeWeights(
        weight=np.zeros((len(SIGN_CLASSES), 512), dtype=np.float32),
        bias=np.zeros(len(SIGN_CLASSES), dtype=np.float32),
        classes=list(SIGN_CLASSES),
        label_count=120,
    )
    path = tmp_path / "probe.npz"
    save(weights, path)

    reset_registry()
    monkeypatch.setenv("MITHRA_PROBE_PATH", str(path))
    try:
        assert get_classifier().version == weights.version
    finally:
        reset_registry()


def test_an_unloadable_probe_falls_back_rather_than_failing(tmp_path, monkeypatch, capsys):
    """A worker that refuses to start finds no features at all — worse than old ones."""
    from mithra_ml.registry import get_classifier, reset_registry

    broken = tmp_path / "broken.npz"
    broken.write_bytes(b"not a model")

    reset_registry()
    monkeypatch.setenv("MITHRA_PROBE_PATH", str(broken))
    try:
        assert "zeroshot" in get_classifier().version
        assert "could not be loaded" in capsys.readouterr().err
    finally:
        reset_registry()
