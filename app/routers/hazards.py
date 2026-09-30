
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas.models import RegionHazardBundle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/regions", tags=["hazards"])

MOCK_DATA_DIR = Path(__file__).parent.parent / "mock_data"

REGION_FILES = {
    "pilot-odisha-puri": "hazards_pilot_region.json",
}
REGION_LIVE_CONFIG = {
    "pilot-odisha-puri": dict(sid="2019116N02090", region_name="Odisha Coast (Puri-Paradip)"),  # Fani 2019 -- verified against real IBTrACS ingest output, not guessed
}


def _load_mock_region_data(region_id: str) -> dict:
    filename = REGION_FILES.get(region_id)
    if not filename:
        raise HTTPException(status_code=404, detail=f"No data for region '{region_id}'")
    path = MOCK_DATA_DIR / filename
    with open(path, "r") as f:
        return json.load(f)


def _load_region_data(region_id: str) -> dict:
    """Real modeling pipeline first, mock JSON as a safety net.

    Set HAZARDS_FORCE_MOCK=1 in the environment to skip straight to mock data
    (useful for Person 4 developing the frontend without a live DB, or as a
    guaranteed-safe path on demo day if the DB connection is flaky venue wifi
    away from being trustworthy).
    """
    import os
    if os.getenv("HAZARDS_FORCE_MOCK") == "1":
        return _load_mock_region_data(region_id)

    live_cfg = REGION_LIVE_CONFIG.get(region_id)
    if live_cfg:
        try:
            from app.modeling.export import get_hazard_bundle_from_db
            return get_hazard_bundle_from_db(
                sid=live_cfg["sid"],
                region_name=live_cfg["region_name"],
                region_id=region_id,
            )
        except Exception as exc:
            logger.warning(
                "Live hazard modeling failed for region '%s' (%s) -- "
                "falling back to mock data.", region_id, exc,
            )

    return _load_mock_region_data(region_id)


@router.get("/{region_id}/hazard-layers", response_model=RegionHazardBundle)
def get_hazard_layers(region_id: str):
    """
    Returns all hazard layers (surge, flood, exposure) for one region as
    GeoJSON, ready to feed into Mapbox GL / deck.gl sources on the frontend.
    """
    data = _load_region_data(region_id)
    return RegionHazardBundle(
        region_id=region_id,
        cyclone_id=data.get("cyclone_id"),
        surge=data.get("surge"),
        flood=data.get("flood"),
        exposure=data.get("exposure"),
    )


@router.get("/{region_id}/summary")
def get_region_summary(region_id: str):
    """Quick numeric summary -- useful for the advisory prompt and for
    lightweight dashboard widgets that don't need full GeoJSON."""
    data = _load_region_data(region_id)
    return {
        "region_id": region_id,
        "cyclone_id": data.get("cyclone_id"),
        "summary_stats": data.get("summary_stats", {}),
        "bulletin_text": data.get("bulletin_text"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/")
def list_regions():
    """Lists region_ids currently available (mock or real)."""
    return {"regions": list(REGION_FILES.keys())}