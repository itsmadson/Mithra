from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bina_api.routes import (
    auth,
    crops,
    export,
    features,
    jobs,
    labels,
    overview,
    signs,
    stats,
    streets,
)

app = FastAPI(title="bina", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(signs.router)
app.include_router(export.router)
app.include_router(labels.router)
app.include_router(crops.router)
app.include_router(features.router)
app.include_router(streets.router)
app.include_router(stats.router)
app.include_router(overview.router)
app.include_router(signs.all_signs)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
