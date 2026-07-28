"""Resolves which classifier the pipeline uses.

Every prediction records its model version, so swapping the registered
classifier changes future results without rewriting past ones.
"""

from bina_ml import Classifier

_classifier: Classifier | None = None


def register_classifier(classifier: Classifier) -> None:
    global _classifier
    _classifier = classifier


def reset_registry() -> None:
    global _classifier
    _classifier = None


def get_classifier() -> Classifier:
    global _classifier
    if _classifier is None:
        from bina_ml.clip_classifier import ClipZeroShotClassifier

        _classifier = ClipZeroShotClassifier()
    return _classifier
