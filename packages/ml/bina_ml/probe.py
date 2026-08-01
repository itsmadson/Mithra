"""A linear probe over frozen CLIP features, trained from operator labels.

Why a linear head and not fine-tuning: with a few hundred labels, fine-tuning a
ViT overfits them and does worse on the next street than the zero-shot model it
replaced. A linear probe on frozen features is the standard few-shot approach,
trains in seconds on a CPU, and cannot destroy what CLIP already knows.

The point of this module is not that it trains — anything trains. It is that it
refuses to hand back a model that has not been shown to beat the one already in
service, measured on data it did not learn from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from PIL.Image import Image

from bina_ml import SIGN_CLASSES, UNKNOWN, Prediction
from bina_ml.encoder import ENCODER_VERSION, embedding_dim, encode_image

# Below this many examples of a class, a probe has not seen that class — it has
# memorised a handful of crops. Training is refused rather than producing a
# model that is confidently wrong about a whole category.
MIN_PER_CLASS = 25

# Folds for the held-out estimate. Five keeps 80% of a small set in training
# while still giving every example a turn at being unseen.
FOLDS = 5


class NotEnoughLabels(ValueError):
    """Raised rather than training something that cannot be evaluated."""

    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        missing = {c: counts.get(c, 0) for c in SIGN_CLASSES if counts.get(c, 0) < MIN_PER_CLASS}
        super().__init__(
            f"need at least {MIN_PER_CLASS} labels per class; short on: {missing}"
        )


@dataclass
class Evaluation:
    """What the probe scored on data it did not train on."""

    accuracy: float
    baseline_accuracy: float
    per_class: dict[str, float]
    support: dict[str, int]
    folds: int = FOLDS

    @property
    def beats_baseline(self) -> bool:
        return self.accuracy > self.baseline_accuracy

    def as_dict(self) -> dict:
        return {
            "accuracy": round(self.accuracy, 4),
            "baseline_accuracy": round(self.baseline_accuracy, 4),
            "per_class": {k: round(v, 4) for k, v in self.per_class.items()},
            "support": self.support,
            "folds": self.folds,
            "beats_baseline": self.beats_baseline,
        }


@dataclass
class ProbeWeights:
    weight: np.ndarray
    bias: np.ndarray
    classes: list[str]
    encoder_version: str = ENCODER_VERSION
    trained_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    label_count: int = 0
    evaluation: dict = field(default_factory=dict)

    @property
    def version(self) -> str:
        day = self.trained_at[:10]
        return f"probe-{ENCODER_VERSION}-{day}-n{self.label_count}"


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


def _fit(features: np.ndarray, targets: np.ndarray, classes: int, epochs: int = 400):
    """Multinomial logistic regression, by gradient descent in torch.

    Weight decay rather than early stopping: the held-out score decides whether
    the result is usable, so the training loop stays deterministic and boring.
    """
    torch.manual_seed(0)
    x = torch.from_numpy(features.astype(np.float32))
    y = torch.from_numpy(targets.astype(np.int64))

    layer = torch.nn.Linear(features.shape[1], classes)
    optimiser = torch.optim.AdamW(layer.parameters(), lr=0.01, weight_decay=0.01)
    loss_fn = torch.nn.CrossEntropyLoss()

    for _ in range(epochs):
        optimiser.zero_grad()
        loss = loss_fn(layer(x), y)
        loss.backward()
        optimiser.step()

    return (
        layer.weight.detach().numpy().astype(np.float32),
        layer.bias.detach().numpy().astype(np.float32),
    )


def _stratified_folds(targets: np.ndarray, folds: int) -> list[np.ndarray]:
    """Fold assignment that keeps every class represented in every fold.

    A random split can leave a rare class out of a fold entirely, which reports
    an accuracy for a class the fold never tested.
    """
    rng = np.random.default_rng(0)
    assignment = np.zeros(len(targets), dtype=int)
    for cls in np.unique(targets):
        indices = np.flatnonzero(targets == cls)
        rng.shuffle(indices)
        assignment[indices] = np.arange(len(indices)) % folds
    return [np.flatnonzero(assignment == f) for f in range(folds)]


def evaluate(
    features: np.ndarray,
    targets: np.ndarray,
    classes: list[str],
    baseline: np.ndarray | None = None,
) -> Evaluation:
    """Cross-validated accuracy — never training accuracy.

    A probe scores near-perfectly on the examples it was fitted to, and
    reporting that number would be a lie told with real arithmetic.
    """
    folds = _stratified_folds(targets, FOLDS)
    predictions = np.zeros(len(targets), dtype=int)

    for held_out in folds:
        if len(held_out) == 0:
            continue
        mask = np.ones(len(targets), dtype=bool)
        mask[held_out] = False
        weight, bias = _fit(features[mask], targets[mask], len(classes))
        logits = features[held_out] @ weight.T + bias
        predictions[held_out] = logits.argmax(axis=1)

    per_class: dict[str, float] = {}
    support: dict[str, int] = {}
    for index, name in enumerate(classes):
        belongs = targets == index
        support[name] = int(belongs.sum())
        per_class[name] = (
            float((predictions[belongs] == index).mean()) if belongs.any() else 0.0
        )

    baseline_accuracy = (
        float((baseline == targets).mean()) if baseline is not None else 0.0
    )
    return Evaluation(
        accuracy=float((predictions == targets).mean()),
        baseline_accuracy=baseline_accuracy,
        per_class=per_class,
        support=support,
    )


def train(
    features: np.ndarray,
    labels: list[str],
    baseline: list[str] | None = None,
) -> tuple[ProbeWeights, Evaluation]:
    """Fit a probe on labelled features, and report what it scores unseen.

    `baseline` is what the model currently in service predicted for the same
    crops, so the comparison is like for like rather than against an assumed
    accuracy nobody measured.
    """
    classes = list(SIGN_CLASSES)
    counts = {name: labels.count(name) for name in classes}
    if any(counts[name] < MIN_PER_CLASS for name in classes):
        raise NotEnoughLabels(counts)

    index_of = {name: i for i, name in enumerate(classes)}
    keep = [i for i, name in enumerate(labels) if name in index_of]
    x = features[keep]
    y = np.array([index_of[labels[i]] for i in keep], dtype=np.int64)

    baseline_indices = None
    if baseline is not None:
        # An `unknown` baseline prediction is simply wrong against a real label,
        # which is the honest way to score "the model declined to answer".
        baseline_indices = np.array(
            [index_of.get(baseline[i], -1) for i in keep], dtype=np.int64
        )

    result = evaluate(x, y, classes, baseline_indices)
    weight, bias = _fit(x, y, len(classes))
    weights = ProbeWeights(
        weight=weight,
        bias=bias,
        classes=classes,
        label_count=len(keep),
        evaluation=result.as_dict(),
    )
    return weights, result


def save(weights: ProbeWeights, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        weight=weights.weight,
        bias=weights.bias,
        meta=json.dumps(
            {
                "classes": weights.classes,
                "encoder_version": weights.encoder_version,
                "trained_at": weights.trained_at,
                "label_count": weights.label_count,
                "evaluation": weights.evaluation,
            }
        ),
    )


def load(path: Path) -> ProbeWeights:
    data = np.load(path, allow_pickle=False)
    meta = json.loads(str(data["meta"]))
    if meta["encoder_version"] != ENCODER_VERSION:
        # Features from a different encoder mean different axes; the weights
        # would still multiply, and the answers would be noise.
        raise ValueError(
            f"probe was trained on {meta['encoder_version']}, "
            f"this build encodes with {ENCODER_VERSION}"
        )
    return ProbeWeights(
        weight=data["weight"],
        bias=data["bias"],
        classes=list(meta["classes"]),
        encoder_version=meta["encoder_version"],
        trained_at=meta["trained_at"],
        label_count=meta["label_count"],
        evaluation=meta["evaluation"],
    )


class LinearProbeClassifier:
    """Serves a trained probe, with the same contract as the zero-shot model."""

    def __init__(self, weights: ProbeWeights, threshold: float = 0.55) -> None:
        self._weights = weights
        self._threshold = threshold
        self.version = weights.version

    @classmethod
    def from_file(cls, path: Path, threshold: float = 0.55) -> LinearProbeClassifier:
        return cls(load(path), threshold)

    def predict(self, image: Image) -> Prediction:
        features = encode_image(image)
        logits = features @ self._weights.weight.T + self._weights.bias
        probabilities = _softmax(logits)
        best = int(probabilities.argmax())
        confidence = float(probabilities[best])

        # Same rule as zero-shot: an unsure answer is not an answer, it is a
        # row in the review queue.
        if confidence < self._threshold:
            return Prediction(UNKNOWN, confidence, self.version)
        return Prediction(self._weights.classes[best], confidence, self.version)


def features_placeholder(count: int) -> np.ndarray:
    """Zeroed features of the right shape, for tests that do not need CLIP."""
    return np.zeros((count, embedding_dim()), dtype=np.float32)
