# Classification, and how it gets better

## What runs today

CLIP zero-shot, with bilingual prompts. It exists so the product works on day one,
before any labels have been collected.

**It is frequently wrong on regulatory signs.** It will call a pedestrian crossing a
guide sign, with high confidence. This is not a bug to be tuned away; it is what a
model that was never trained on Persian street signs does. The product is built
around that fact rather than hiding it:

- anything below the confidence threshold becomes `unknown` and goes to a person;
- every sign shows its confidence and the provider's own label beside ours, so
  disagreement is visible per sign rather than as a statistic;
- the dashboard plots the confidence distribution against the review threshold, so a
  model that is guessing looks like what it is.

## How it is replaced

A **linear probe over frozen CLIP features**, trained from the labels operators
produce in the review queue.

Not fine-tuning. With a few hundred labels, fine-tuning a ViT overfits them and does
worse on the next street than the model it replaced. A probe on frozen features
trains in seconds on a CPU and cannot destroy what CLIP already knows.

```bash
python scripts/train_probe.py                  # report only
python scripts/train_probe.py --out models/probe.npz
```

### What the trainer refuses to do

The point of the module is not that it trains. Anything trains.

- **It will not train below 25 labels per class.** Under that a probe has not seen a
  class, it has memorised a handful of crops.
- **It will not report training accuracy.** Accuracy comes from stratified k-fold
  cross-validation. A test asserts that noise-only features score near chance, so if
  the evaluation ever starts reading the answers it was given, that test fails.
- **It will not claim an improvement it cannot show.** The probe is scored against
  what the model currently in service predicted *for the same crops*. If it does not
  win, the weights are not written.
- **It will not promote itself.** Training writes a file. Nothing uses it until
  `BINA_PROBE_PATH` points at one, because which model is in service decides what a
  municipality's inventory claims.

### Serving

```bash
BINA_PROBE_PATH=/app/models/probe.npz
```

A probe that fails to load falls back to zero-shot with a message on stderr rather
than taking the worker down: a worker that refuses to start finds no signs at all,
which is worse than finding them with the older model.

Weights record which encoder produced their training features and refuse to load
against a different one. A probe served from a different feature space would still
multiply, and the answers would be noise.
