from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import hazards, advisory, alerts

app = FastAPI(
    title="Cyclone Early Warning API",
    description="Backend serving hazard layers, LLM-generated advisories, and alert dispatch.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hazards.router)
app.include_router(advisory.router)
app.include_router(alerts.router)


@app.get("/health")
def health():
    return {"status": "ok"}
