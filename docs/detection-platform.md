# From sign surveys to a detection platform

Research and architecture for turning Mithra from "Mapillary panoramas, Persian
road signs" into "any imagery, any object the models can actually find".

## The finding that shapes everything else

**What you can detect is decided by pixel size, not by the model.**

Ground sample distance (GSD) is how many metres one pixel covers. An object
smaller than a few pixels cannot be found by any model, at any accuracy, ever —
there is nothing in the image to find.

| Imagery | GSD | What is individually detectable |
|---|---|---|
| Sentinel-2 (free, global, 5-day) | 10 m | Water bodies, forest vs field, urban vs rural, large industrial roofs, coastline, flooded area. **Not** individual trees, cars, or houses. |
| Planet, SPOT | 3–5 m | Building blocks, road network, large vehicles in aggregate |
| NAIP (US aerial, free) | 0.6 m | Individual trees, buildings, pools, solar panels |
| Esri/Google/Bing tiles at z19–20 | 0.15–0.3 m | Everything above, plus cars, road markings, street furniture |
| Drone / UAV upload | 0.02–0.1 m | Individual crowns, damage, crop rows |

A user who picks Sentinel-2 and asks for "trees" must be told the truth before
the run starts, not handed an empty result or — worse — a plausible-looking one.
**The class catalogue is therefore a function of the imagery, not a fixed list.**

Sources: [Sentinel-2 GRD study](https://elib.dlr.de/212129/1/s41064-024-00330-x.pdf),
[trees at 10 m are not individuated](https://arxiv.org/pdf/2005.08702),
[sub-metre is the threshold for vehicles and building detail](https://skyfi.com/en/blog/high-resolution-satellite-imagery).

## Which model for which object

No single model wins everywhere. The honest answer is a registry with a
declared speciality per detector, the same shape as the existing classifier
registry.

| Target | Best available | Evidence | Notes |
|---|---|---|---|
| **Open vocabulary** (anything the user types) | **SAM 3** via `segment-geospatial` | SegEarth-OV3 reports 86.9 IoU building on WHU-Aerial, 72.4 on Inria, zero-shot across 20 RS datasets | The default. Text prompt in, polygons out, no training. |
| Trees (individual crowns) | **DeepForest** (RGB, boxes) or Tree-SAM | DeepForest ~64–70% on NEON crowns; Tree-SAM F1 0.83 urban / 0.76 forest on GZ-Tree | DeepForest is a purpose-trained baseline; SAM-family generalises better off-nadir |
| Water / flood | **OmniWaterMask** | Shipped in the GeoAI QGIS plugin for exactly this | Works at Sentinel-2 GSD, unlike most of this table |
| Buildings | SAM 3 text prompt, or a footprint model | 86.9 IoU above | Sub-metre imagery required for individual footprints |
| Cars, ships, planes | SAM 3 text prompt | — | Needs ≤0.3 m; count accuracy degrades fast with GSD |
| Land cover classes | SegEarth-OV3 semantic head | 20-dataset evaluation | Pixel classes rather than instances |

Sources: [SegEarth-OV3](https://arxiv.org/html/2512.08730v2) ·
[SegEarth-OV-3 code](https://github.com/earth-insights/SegEarth-OV-3) ·
[samgeo](https://samgeo.gishub.org/) ·
[GeoAI QGIS plugin](https://plugins.qgis.org/plugins/geoai/) ·
[Tree-SAM / zero-shot tree work](https://arxiv.org/pdf/2506.03114) ·
[SAM for tree crowns](https://arxiv.org/pdf/2503.20199) ·
[DeepForest on NEON](https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1009180)

`segment-geospatial` already does the unglamorous half of this: download tiles
for a bbox into a GeoTIFF, run SAM with text/point/box prompts, write
GeoPackage/GeoJSON. That is the engine; Mithra becomes the product around it —
areas, provenance, review, tenancy, exports, audit.

## The two inputs, made concrete

### 1. Where — an area of interest

Already half-built: the street composer resolves a name to geometry. It
generalises to:

- a drawn bbox or polygon,
- a place search (Nominatim, already proxied),
- an uploaded vector file (GeoJSON/Shapefile/GeoPackage),
- an administrative boundary.

### 2. What imagery — a source adapter

A registry mirroring the classifier registry. Each source declares its GSD,
extent, date range, bands, and licence:

| Adapter | Input the user gives |
|---|---|
| `xyz` | Any `{z}/{x}/{y}` template — the basemaps feature already stores these |
| `stac` | A STAC collection + date window (Sentinel-2 L2A on AWS, Planetary Computer) |
| `cog` | A URL to a Cloud-Optimised GeoTIFF |
| `upload` | A GeoTIFF the user uploads |
| `mapillary` | The existing street-level path, now one source among several |

`rio-tiler` + `pystac-client` read all of these against a bbox without
downloading whole scenes.
Sources: [rio-tiler STAC](https://cogeotiff.github.io/rio-tiler/examples/Using-rio-tiler-STACReader/) ·
[Sentinel-2 COGs on AWS](https://registry.opendata.aws/sentinel-2-l2a-cogs/)

### 3. What to detect — capability matching

The third input the request asked for, and the one that carries the design.
Given `(source.gsd, detector.classes, detector.min_gsd)`, the UI offers only
what that combination can deliver, and says why the rest is unavailable:

> **Tree (individual)** — unavailable with Sentinel-2 (10 m). A crown is 1 pixel
> here. Switch to aerial imagery, or detect **Forest cover** instead.

This is the single feature that separates an honest tool from a demo.

## Data model

The existing shape survives with renames; the tenancy, review queue, training
loop and audit trail all still apply.

| Now | Becomes | Change |
|---|---|---|
| `Job` (a survey) | `Run` | Add `source_kind`, `source_config`, `target_classes[]`, `detector`, `gsd`; area becomes a polygon rather than a bbox+corridor |
| `Sign` | `Feature` | `geom` becomes Geometry (point **or** polygon), `sign_class` becomes `class_name` (free text from the catalogue), keep confidence/crop/model_version |
| `Label` | unchanged | Still the review queue and still the training set |
| `Basemap` | unchanged | Already a tile source; becomes selectable as an imagery source too |

Two honest consequences: `class_name` can no longer be an enum, and the
classifier registry becomes a **detector** registry whose members declare which
classes they support.

## Dashboard at scale

Today's dashboard answers one organisation's single question. With many
projects, many runs and arbitrary classes it needs:

- **Projects** above runs — a city, a client, a campaign. Runs belong to a
  project; the dashboard scopes to one.
- **A map as the home surface**, not a panel. At this scale the inventory *is*
  the map: all runs, layered by class, with the charts as an overlay rail.
- **Class layers with counts**, replacing the fixed five-class filter.
- **Area-normalised figures** — "412 trees" means nothing without "per km²",
  and comparing two runs of different sizes by raw count is misleading.
- **A run comparison view** — the same area, two dates, what changed. This is
  where the money is in GIS, and the schema above already supports it.
- **Cost and quota**, once inference runs on real imagery: every run has a
  compute cost, and an operator who cannot see it will be surprised by a bill.

## Phased plan

Each phase ships something usable and keeps the tests green.

1. **Generalise the core** — `Run`/`Feature` rename, detector registry, the
   capability matrix, and the honest "not at this resolution" refusal. No new
   models yet; the existing pipeline keeps working as the `mapillary` source.
2. **Imagery adapters** — `xyz` and `cog` first (they need no credentials),
   then `stac` for Sentinel-2, then upload.
3. **SAM 3 detector** — `segment-geospatial` behind the registry, text prompts,
   polygons out. This is the moment arbitrary classes become real.
4. **Specialist detectors** — DeepForest for crowns, OmniWaterMask for water,
   registered alongside SAM with their own declared specialities and minimum
   GSD.
5. **Dashboard for scale** — projects, map-first home, class layers, per-km²
   figures, run comparison.

## What this costs

Honest, before anything is built:

- **Inference is heavy.** SAM 3 on a city-sized area is GPU work. The current
  CPU-only image classifies one crop at a time; segmenting a 10 km² area at
  0.3 m is a different order of compute. Either a GPU worker or a queue that
  admits runs take hours.
- **Imagery licences differ.** Sentinel-2 is free and redistributable. Esri and
  Google tiles are not — using them for bulk inference likely violates their
  terms. The source registry must carry the licence and the UI must show it.
- **Accuracy claims need per-class evidence.** The existing probe already
  refuses to promote itself without beating the incumbent; that discipline has
  to extend per class, or "detects 40 object types" becomes marketing rather
  than measurement.
