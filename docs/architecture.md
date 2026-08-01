# Architecture

Four processes, one database, one queue.

```
browser ── web (Next.js) ── api (FastAPI) ── PostgreSQL + PostGIS
                                │
                             Redis ── worker (RQ)
```

## Why the split

**The worker is separate because surveys are slow.** A single street can hold
hundreds of signs, each needing an image download and a model forward pass. Doing
that inside a request would hold a connection open for minutes and lose the work if
the client disconnected. The API writes a row, hands an id to the queue, and answers
immediately; the worker owns everything after that.

**The API and worker ship as one image.** They import the same models and the same
pipeline code. Two images built from the same source drift the moment one is rebuilt
without the other, and a worker running different model code than the API describes
would produce rows the API cannot explain.

**PostGIS rather than coordinates in columns.** Surveys are corridors — buffered
street centrelines — and asking "which signs fall inside this corridor" is a spatial
question. Answering it in SQL keeps it correct as the data grows; answering it in
Python means loading every sign to filter it.

## Data model

| Table | Holds |
|---|---|
| `organisations` | The tenancy boundary |
| `users`, `sessions` | Accounts, and logged-in browsers |
| `jobs` | A survey: its geometry, status, and owner |
| `job_tiles` | The tiles a survey was decomposed into, and which failed |
| `signs` | One detected sign: class, confidence, geometry, crop, provenance |
| `labels` | A human judgement about a sign, and who made it |
| `basemaps` | Tile sources an organisation added |

A sign records the model version that classified it. Swapping the model changes
future results without rewriting past ones, so a count from March stays explainable
in June.

## Request flow for a survey

1. The console resolves a street name through the API (Nominatim, proxied so the
   provider's usage policy is honoured and the operator's IP is not leaked).
2. `POST /api/jobs` writes a `queued` row and enqueues its id. If the queue is
   unreachable the row is marked `failed` rather than left looking like it is
   waiting.
3. The worker resolves the corridor (Overpass), decomposes it into tiles, and for
   each tile fetches imagery and detections, crops each sign, classifies it, and
   writes rows as it goes.
4. The console polls the survey and fills the map while the work runs.

Partial failure is a first-class outcome: a survey where some tiles failed finishes
`partial` with the failed count visible, rather than reporting a total that quietly
omits them.
