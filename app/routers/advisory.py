
from fastapi import APIRouter

from app.schemas.models import AdvisoryRequest, AdvisoryResponse
from app.routers.hazards import _load_region_data
from app.services import gemini_service

router = APIRouter(prefix="/advisory", tags=["advisory"])


@router.post("/generate", response_model=AdvisoryResponse)
async def generate_advisory(req: AdvisoryRequest):
    # Fall back to the region's on-file summary for any field the caller
    # didn't explicitly supply.
    region_data = _load_region_data(req.region_id)
    stats = region_data.get("summary_stats", {})

    surge = req.surge_height_m if req.surge_height_m is not None else stats.get("max_surge_height_m")
    flood = req.flood_extent_km2 if req.flood_extent_km2 is not None else stats.get("max_flood_depth_m")
    exposure = req.exposure_score if req.exposure_score is not None else stats.get("mean_exposure_score")
    bulletin = req.bulletin_text or region_data.get("bulletin_text")

    result = await gemini_service.generate_advisory(
        region_id=req.region_id,
        cyclone_id=req.cyclone_id,
        language=req.language,
        surge_height_m=surge,
        flood_extent_km2=flood,
        exposure_score=exposure,
        bulletin_text=bulletin,
        # satellite_image_bytes: wire this up once Person 1's GEE image
        # export is available -- fetch/read the image, pass raw bytes here.
    )
    return result
