"""Resolves which classifier the pipeline uses.

Every prediction records its model version, so swapping the registered
classifier changes future results without rewriting past ones.
"""

import os
import sys
from pathlib import Path

from bina_ml import Classifier

_classifier: Classifier | None = None


def register_classifier(classifier: Classifier) -> None:
    global _classifier
    _classifier = classifier


def reset_registry() -> None:
    global _classifier
    _classifier = None


def get_classifier() -> Classifier:
    """The classifier the pipeline should use.

    A trained probe if one is configured and loadable, the zero-shot model
    otherwise. Promotion is a deployment decision — pointing BINA_PROBE_PATH at
    a file — rather than something training does to itself, because which model
    is in service decides what a municipality's inventory claims.

    A probe that fails to load falls back rather than taking the pipeline down:
    a worker that refuses to start finds no signs at all, which is worse than
    one finding them with the older model. The failure is printed, not
    swallowed.
    """
    global _classifier
    if _classifier is not None:
        return _classifier

    probe_path = os.environ.get("BINA_PROBE_PATH")
    if probe_path:
        try:
            from bina_ml.probe import LinearProbeClassifier

            _classifier = LinearProbeClassifier.from_file(Path(probe_path))
            return _classifier
        except Exception as exc:  # noqa: BLE001 - any load failure has one outcome
            print(
                f"probe at {probe_path} could not be loaded ({exc}); "
                "falling back to zero-shot",
                file=sys.stderr,
            )

    from bina_ml.clip_classifier import ClipZeroShotClassifier

    _classifier = ClipZeroShotClassifier()
    return _classifier
