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
  `MITHRA_PROBE_PATH` points at one, because which model is in service decides what a
  municipality's inventory claims.

### Serving

```bash
MITHRA_PROBE_PATH=/app/models/probe.npz
```

A probe that fails to load falls back to zero-shot with a message on stderr rather
than taking the worker down: a worker that refuses to start finds no signs at all,
which is worse than finding them with the older model.

Weights record which encoder produced their training features and refuse to load
against a different one. A probe served from a different feature space would still
multiply, and the answers would be noise.


---

# The model registry

Eleven detectors, each declaring what it finds, what it needs to run, and the
published number that justifies choosing it. Where two answer the same target,
the one with the better score wins — if the hardware allows it.

| Target | Detector | Benchmark | Needs |
|---|---|---|---|
| **water** | NDWI index | standard method for open water at 10 m | CPU, no weights |
| water (robust) | OmniWaterMask | — | CPU, slow |
| **tree** | Tree-SAM | F1 0.83 urban / 0.76 forest (GZ-Tree) | GPU 6 GB |
| tree (CPU) | DeepForest | 70% (NEON crowns) | CPU, slow |
| **building** | SAM 3 | IoU 0.87 (WHU-Aerial), 0.72 (Inria) | GPU 8 GB |
| **road** | SAM-Road | APLS 0.66 (SpaceNet / city-scale) | GPU 8 GB |
| road (cheaper) | D-LinkNet | IoU 0.64 (DeepGlobe) | GPU 4 GB |
| **car, ship** | Oriented R-CNN | mAP 0.58 (DOTA-v2.0 OBB) | GPU 8 GB |
| **solar panel** | rooftop PV CNN | F1 0.85 (aerial) | GPU 4 GB |
| **land cover** | Dynamic World | 73.8% (global validation) | CPU |
| **anything else** | SAM 3 (text prompt) | as above | GPU 8 GB |
| sign (street) | CLIP zero-shot | — untrained, frequently wrong | CPU, slow |

Sources: [SegEarth-OV3](https://arxiv.org/html/2512.08730v2) ·
[Tree-SAM](https://arxiv.org/pdf/2506.03114) ·
[DeepForest / NEON](https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1009180) ·
[SAM-Road](https://arxiv.org/pdf/2403.16051) ·
[D-LinkNet](https://github.com/zlckanata/DeepGlobe-Road-Extraction-Challenge) ·
[DOTA benchmark](https://captain-whu.github.io/DOTA/) ·
[Dynamic World](https://www.nature.com/articles/s41597-022-01307-4) ·
[rooftop PV](https://www.tandfonline.com/doi/full/10.1080/07038992.2024.2363236)

Two of the eleven are built into this release: the NDWI index and SAM 3. The
rest are declared with their requirements so the console can plan around them
and so adding one is a single adapter rather than a redesign.

## The server decides what you can run

The same build behaves differently on a laptop and on a GPU host, and the
difference is not speed — a detector needing 8 GB of VRAM on a machine with
none does not run slowly, it does not run. So the machine is measured and the
answer is shown before anybody starts:

| Tier | Meaning | What it can do |
|---|---|---|
| `gpu` | GPU with ≥8 GB VRAM | everything installed |
| `small_gpu` | GPU under 8 GB | the lighter models; SAM refused with the numbers |
| `strong_cpu` | ≥8 cores, ≥16 GB | index and CPU models at reasonable speed |
| `modest` | anything less | index models; CPU models flagged slow |

Settings shows this per detector, with the reason for each refusal, and the
composer picks the most accurate detector the machine can actually run.

## Before trusting SAM on a new host

The SAM adapter is written against segment-geospatial's documented interface
and has not been exercised on a GPU by its author. Run this once on the GPU
server before trusting any count from it:

```bash
python scripts/check_sam.py
```

It reports the machine, whether the weights load, and what SAM finds on a real
scene, so the first honest number comes from a deliberate check rather than
from a production run.


---

# The taxonomy

Seventy-one targets across ten domains, because "detect objects" is not a
question anybody asks. A municipality asks how much of the city is built, which
roofs carry solar, what condition the asphalt is in, where the informal
settlements are — and those are different questions with different imagery,
different models and different failure modes.

| Domain | Targets | Examples |
|---|---|---|
| Land cover | 8 | forest, shrubland, grassland, bare ground, snow, built-up |
| Land use | 10 | residential, commercial, industrial, informal settlement, quarry, landfill |
| Buildings | 12 | residential, apartment, commercial, industrial, school, hospital, mosque, warehouse, greenhouse, under construction, roof material |
| Transport | 8 | road, road surface type, sidewalk, crosswalk, parking, bridge, railway, runway |
| Condition | 6 | pavement distress, pothole, faded markings, facade condition, graffiti, litter |
| Street furniture | 10 | traffic light, street light, utility pole, manhole, bus stop, bench, bin, guardrail, hydrant |
| Water | 3 | water, river, reservoir |
| Energy | 5 | solar panel, wind turbine, power line, substation, storage tank |
| Agriculture | 4 | cropland, field boundary, orchard, irrigation pivot |
| Vehicles | 5 | car, truck, bus, ship, aircraft |

## Two viewpoints, two different products

Overhead imagery at 0.3 m answers 53 of them. Street-level panoramas at 0.05 m
answer 35 — and the overlap is smaller than it looks, because the two see
genuinely different things:

- **Only from above**: land cover, land use, field boundaries, parking extent,
  roof material, irrigation pivots. A panorama at five centimetres per pixel
  still cannot see the shape of a lake.
- **Only from the street**: road surface type (asphalt, concrete, gravel),
  pavement distress, faded markings, facade condition, manholes, sign faces.
  Satellite imagery cannot read a crack in asphalt or the front of a shop at
  any resolution, because it is looking at the wrong side of the world.

That is why the catalogue gates on viewpoint before resolution.

## Every target answers "how would you detect this?"

`GET /api/catalog/plan/{target}` returns, for one target: every imagery source
with whether it can see it and why not, every model that claims it with its
published benchmark and whether this server can run it, and which one would be
chosen. The console shows it inline when a user asks.

The rule that keeps it honest: **a specialist outranks a generalist for its own
target, even when the generalist publishes a bigger number**. SAM 3's 87% IoU
was measured on WHU-Aerial buildings; quoting it beside a pavement-crack
benchmark would compare two different questions. The API marks such a score
`measures_this_target: false` and the console prints "measured on a different
task" next to it.
