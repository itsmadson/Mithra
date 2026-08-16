from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mithra_api.routes import (
    audit,
    auth,
    basemaps,
    catalog,
    crops,
    export,
    features,
    geojson,
    runs,
    labels,
    overview,
    features,
    geojson,
    stats,
    streets,
    system,
    uploads,
)

app = FastAPI(title="Mithra", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audit.router)
app.include_router(auth.router)
app.include_router(basemaps.router)
app.include_router(catalog.router)
app.include_router(runs.router)
app.include_router(features.router)
app.include_router(geojson.router)
app.include_router(export.router)
app.include_router(labels.router)
app.include_router(crops.router)
app.include_router(streets.router)
app.include_router(uploads.router)
app.include_router(system.router)
app.include_router(stats.router)
app.include_router(overview.router)
app.include_router(features.all_features)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
