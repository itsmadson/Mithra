#!/usr/bin/env python
"""Train a classifier head from the labels operators have collected.

Run it, read what it says, and decide. It deliberately does not install the
result: promoting a model is a decision about what a municipality's inventory
will claim, and that belongs to a person who has seen the numbers.

    python scripts/train_probe.py                  # report only
    python scripts/train_probe.py --out models/probe.npz

The held-out accuracy is compared against what the model currently in service
predicted for the same crops. If the probe does not beat it, that is reported
plainly and the file is not written.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path[:0] = ["services/api", "services/worker", "packages/ml"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="where to write the weights if they win")
    parser.add_argument(
        "--force",
        action="store_true",
        help="write the weights even if they do not beat the model in service",
    )
    args = parser.parse_args()

    import numpy as np
    from PIL import Image
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from mithra_api.db import get_engine
    from mithra_api.models import Label, Feature
    from mithra_ml import SIGN_CLASSES
    from mithra_ml.encoder import encode_images
    from mithra_ml.probe import MIN_PER_CLASS, NotEnoughLabels, save, train

    with Session(get_engine()) as session:
        total_labels = session.scalar(select(func.count()).select_from(Label)) or 0
        rows = session.execute(
            select(Label.class_name, Feature.crop_path, Feature.class_name)
            .join(Feature, Feature.id == Label.feature_id)
            .where(Feature.crop_path.is_not(None))
            .order_by(Label.created_at)
        ).all()

    if not rows:
        # These are different problems and deserve different answers: one needs
        # labelling, the other means the crops the labels describe were never
        # saved, and no amount of labelling will fix it.
        if total_labels:
            print(
                f"{total_labels} labels exist, but none of the features they describe "
                "have a saved crop, so there is nothing to encode."
            )
        else:
            print("No labels yet. The review queue is where they come from.")
        return 1

    # A label whose crop has been deleted cannot be trained on; say so rather
    # than silently training on a smaller set than the operator was told about.
    usable = [(cls, path, was) for cls, path, was in rows if Path(path).exists()]
    missing = len(rows) - len(usable)
    if missing:
        print(f"{missing} labelled crops are no longer on disk and were skipped.")

    counts = Counter(cls for cls, _, _ in usable)
    print(f"{len(usable)} usable labels: {dict(counts)}")
    short = {c: counts.get(c, 0) for c in SIGN_CLASSES if counts.get(c, 0) < MIN_PER_CLASS}
    if short:
        print(f"Not enough yet. Need {MIN_PER_CLASS} per class; short on: {short}")
        return 1

    print("Encoding crops…")
    features_list = []
    labels: list[str] = []
    baseline: list[str] = []
    batch_size = 32
    for start in range(0, len(usable), batch_size):
        chunk = usable[start : start + batch_size]
        images = [Image.open(path) for _, path, _ in chunk]
        features_list.append(encode_images(images))
        for image in images:
            image.close()
        labels.extend(cls for cls, _, _ in chunk)
        baseline.extend(was for _, _, was in chunk)
        print(f"  {min(start + batch_size, len(usable))}/{len(usable)}", end="\r")

    features = np.concatenate(features_list)
    print()

    try:
        weights, result = train(features, labels, baseline=baseline)
    except NotEnoughLabels as exc:
        print(exc)
        return 1

    print()
    print(f"Held-out accuracy over {result.folds} folds: {result.accuracy:.1%}")
    print(f"Model currently in service, same crops:      {result.baseline_accuracy:.1%}")
    print()
    for name in SIGN_CLASSES:
        print(f"  {name:<18} {result.per_class[name]:>6.1%}  (n={result.support[name]})")
    print()

    if not result.beats_baseline:
        print("The probe does NOT beat the model in service. Collect more labels.")
        if not args.force:
            return 1
        print("Writing anyway because --force was given.")

    if args.out:
        save(weights, args.out)
        print(f"Wrote {args.out} — version {weights.version}")
        print("Nothing uses it until MITHRA_PROBE_PATH points at it.")
    else:
        print("Report only. Pass --out to write the weights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
