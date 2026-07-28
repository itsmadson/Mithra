from PIL import Image

from bina_ml import UNKNOWN, Prediction
from bina_ml.registry import get_classifier, register_classifier, reset_registry


class FakeClassifier:
    version = "fake-v1"

    def predict(self, image):
        return Prediction(
            sign_class="street_name", confidence=0.9, model_version=self.version
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
    assert prediction.sign_class != UNKNOWN
