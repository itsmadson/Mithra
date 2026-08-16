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

## The console, as an operator tool

Three decisions shape every screen, and they are worth stating because each has a
tempting cheaper version that fails silently.

**The list is a server query.** Filtering, searching, sorting and paging all happen in
Postgres. The obvious alternative — fetch a few thousand rows and filter them in the
browser — works until an organisation has more than a few thousand detections, at
which point the console keeps answering, just about a subset it never mentions. The
facet counts beside the table come from the same predicate as the rows, so a panel
cannot claim twenty-four of something the table shows nineteen of.

**Colour encodes the domain, never the class.** There are seventy-one classes and ten
domains; a hue per class is a legend nobody reads and two greens that mean unrelated
things. Hue carries the domain, lightness separates classes inside it, and the class
is always written beside its dot, so identity is never colour alone. The ten hues were
generated against the lightness band, chroma floor, colour-vision separation and
contrast on both surfaces rather than picked by eye — the light set is stepped for its
own background, not flipped from the dark one.

**The catalogue names things, the console phrases them.** Class names, domains, source
descriptions and refusal reasons all come from the catalogue, which is a library and
answers in English. Anything a person reads is translated in the console: a refusal
arrives as a code and its values (`too_coarse`, needs 0.5, has 10) so it can be said in
Persian, and falls back to the catalogue's own sentence if the console has no phrasing
for it yet. A screen that is Persian except for the one line explaining why something
cannot be detected is a screen that fails exactly where it matters.

## The audit log

Append-only, administrator-only, scoped to one organisation. Written from the routes
that change something rather than from middleware, because middleware can see that a
request arrived but not which class an operator overrode the model with — and the
detail is the entire value of the record.

Three properties hold it up:

- **It cannot fail the action it describes.** A failed audit write is logged and the
  request proceeds. An audit table that can stop a survey is an availability risk.
- **It outlives its subjects.** The actor's email is copied into the row, so deleting
  an account next year does not erase what it did last year.
- **It cannot be edited from inside the application.** There is no update or delete
  route. A log the people it describes can rewrite answers a different question than
  the one it is kept for.

Reads are not recorded. Logging every list request would bury the four events somebody
actually comes looking for under a million rows of routine traffic.
