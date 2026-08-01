"""The probe must refuse to be worse than what it replaces.

These tests use synthetic feature vectors rather than real crops: the question
here is whether the training, evaluation and refusal logic is right, and that
does not need CLIP to be loaded.
"""

import numpy as np
import pytest

from bina_ml import SIGN_CLASSES, UNKNOWN
from bina_ml.probe import (
    MIN_PER_CLASS,
    NotEnoughLabels,
    ProbeWeights,
    evaluate,
    load,
    save,
    train,
)


def separable_dataset(per_class: int = 40, dim: int = 512, noise: float = 0.15):
    """Features that genuinely carry the class, plus noise.

    Each class sits near its own random direction, which is what a useful
    embedding space looks like: learnable, not trivially separable.
    """
    rng = np.random.default_rng(7)
    centres = rng.normal(size=(len(SIGN_CLASSES), dim)).astype(np.float32)
    features, labels = [], []
    for index, name in enumerate(SIGN_CLASSES):
        for _ in range(per_class):
            point = centres[index] + rng.normal(scale=noise, size=dim).astype(np.float32)
            features.append(point / np.linalg.norm(point))
            labels.append(name)
    return np.stack(features), labels


def test_a_probe_learns_a_separable_signal():
    features, labels = separable_dataset()
    _, result = train(features, labels)
    assert result.accuracy > 0.9


def test_the_reported_accuracy_is_held_out_not_training():
    """Noise-only features carry nothing, so an honest score is near chance.

    A probe fitted to random vectors scores perfectly on its own training data.
    If this test ever reports a high number, the evaluation is reading the
    answers it was given.
    """
    rng = np.random.default_rng(3)
    features = rng.normal(size=(4 * MIN_PER_CLASS + 40, 512)).astype(np.float32)
    labels = [SIGN_CLASSES[i % len(SIGN_CLASSES)] for i in range(len(features))]
    _, result = train(features, labels)
    assert result.accuracy < 0.45  # chance is 0.25 for four classes


def test_training_is_refused_below_the_minimum_per_class():
    features, labels = separable_dataset(per_class=MIN_PER_CLASS)
    # Strip one class down to a handful.
    keep = [i for i, name in enumerate(labels) if name != SIGN_CLASSES[0]][:]
    keep += [i for i, name in enumerate(labels) if name == SIGN_CLASSES[0]][:3]
    with pytest.raises(NotEnoughLabels):
        train(features[keep], [labels[i] for i in keep])


def test_the_refusal_says_which_class_is_short():
    features, labels = separable_dataset(per_class=MIN_PER_CLASS)
    keep = [i for i, name in enumerate(labels) if name != SIGN_CLASSES[1]]
    keep += [i for i, name in enumerate(labels) if name == SIGN_CLASSES[1]][:2]
    with pytest.raises(NotEnoughLabels) as raised:
        train(features[keep], [labels[i] for i in keep])
    assert SIGN_CLASSES[1] in str(raised.value)


def test_exactly_the_minimum_is_enough():
    features, labels = separable_dataset(per_class=MIN_PER_CLASS)
    weights, _ = train(features, labels)
    assert weights.label_count == MIN_PER_CLASS * len(SIGN_CLASSES)


def test_every_class_gets_a_score_and_a_support_count():
    features, labels = separable_dataset()
    _, result = train(features, labels)
    assert set(result.per_class) == set(SIGN_CLASSES)
    assert all(result.support[name] == 40 for name in SIGN_CLASSES)


def test_the_baseline_is_scored_on_the_same_examples():
    """A comparison against the model in service, not against an assumption."""
    features, labels = separable_dataset()
    # A baseline that answers "unknown" everywhere scores zero, because
    # declining to answer is not the same as being right.
    weights, result = train(features, labels, baseline=[UNKNOWN] * len(labels))
    assert result.baseline_accuracy == 0.0
    assert result.beats_baseline
    assert weights.evaluation["beats_baseline"] is True


def test_a_baseline_that_is_already_perfect_is_not_beaten():
    features, labels = separable_dataset()
    _, result = train(features, labels, baseline=list(labels))
    assert result.baseline_accuracy == 1.0
    assert not result.beats_baseline


def test_the_version_records_the_encoder_and_the_label_count():
    features, labels = separable_dataset()
    weights, _ = train(features, labels)
    assert "probe-" in weights.version
    assert f"n{weights.label_count}" in weights.version


def test_weights_survive_a_round_trip(tmp_path):
    features, labels = separable_dataset()
    weights, _ = train(features, labels)
    path = tmp_path / "probe.npz"
    save(weights, path)
    loaded = load(path)

    assert loaded.classes == weights.classes
    assert loaded.label_count == weights.label_count
    assert np.allclose(loaded.weight, weights.weight)
    assert loaded.version == weights.version


def test_a_probe_from_a_different_encoder_is_refused(tmp_path):
    """Weights from another feature space would still multiply, and be noise."""
    features, labels = separable_dataset()
    weights, _ = train(features, labels)
    weights.encoder_version = "clip-some-other-build"
    path = tmp_path / "probe.npz"
    save(weights, path)

    with pytest.raises(ValueError, match="trained on"):
        load(path)


def test_an_unsure_prediction_becomes_unknown(monkeypatch):
    """The probe keeps the zero-shot contract: unsure means the review queue."""
    from bina_ml.probe import LinearProbeClassifier

    weights = ProbeWeights(
        weight=np.zeros((len(SIGN_CLASSES), 512), dtype=np.float32),
        bias=np.zeros(len(SIGN_CLASSES), dtype=np.float32),
        classes=list(SIGN_CLASSES),
    )
    classifier = LinearProbeClassifier(weights, threshold=0.55)
    # Zero weights give a uniform 0.25 across four classes, which is below any
    # sane threshold.
    monkeypatch.setattr(
        "bina_ml.probe.encode_image", lambda image: np.zeros(512, dtype=np.float32)
    )

    prediction = classifier.predict(object())
    assert prediction.sign_class == UNKNOWN
    assert prediction.confidence == pytest.approx(0.25)


def test_a_confident_prediction_names_its_class(monkeypatch):
    from bina_ml.probe import LinearProbeClassifier

    weight = np.zeros((len(SIGN_CLASSES), 512), dtype=np.float32)
    weight[2, 0] = 40.0  # a strong response for the third class on the first axis
    weights = ProbeWeights(
        weight=weight,
        bias=np.zeros(len(SIGN_CLASSES), dtype=np.float32),
        classes=list(SIGN_CLASSES),
    )
    classifier = LinearProbeClassifier(weights, threshold=0.55)

    features = np.zeros(512, dtype=np.float32)
    features[0] = 1.0
    monkeypatch.setattr("bina_ml.probe.encode_image", lambda image: features)

    prediction = classifier.predict(object())
    assert prediction.sign_class == SIGN_CLASSES[2]
    assert prediction.confidence > 0.9


def test_the_prediction_carries_the_probe_version(monkeypatch):
    from bina_ml.probe import LinearProbeClassifier

    weights = ProbeWeights(
        weight=np.zeros((len(SIGN_CLASSES), 512), dtype=np.float32),
        bias=np.zeros(len(SIGN_CLASSES), dtype=np.float32),
        classes=list(SIGN_CLASSES),
        label_count=200,
    )
    classifier = LinearProbeClassifier(weights)
    monkeypatch.setattr(
        "bina_ml.probe.encode_image", lambda image: np.zeros(512, dtype=np.float32)
    )
    assert classifier.predict(object()).model_version == weights.version


def test_folds_keep_every_class_represented():
    """A fold missing a class would report an accuracy it never measured."""
    from bina_ml.probe import FOLDS, _stratified_folds

    targets = np.array([0] * 30 + [1] * 30 + [2] * 27 + [3] * 26)
    folds = _stratified_folds(targets, FOLDS)
    for held_out in folds:
        assert len(np.unique(targets[held_out])) == 4


def test_evaluate_handles_a_class_with_no_examples():
    """Reported as zero rather than crashing or being quietly dropped."""
    features = np.zeros((8, 512), dtype=np.float32)
    targets = np.zeros(8, dtype=np.int64)
    result = evaluate(features, targets, list(SIGN_CLASSES))
    assert result.support[SIGN_CLASSES[1]] == 0
    assert result.per_class[SIGN_CLASSES[1]] == 0.0
