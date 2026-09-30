
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from enum import Enum

class SeverityLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    severe = "severe"


class HazardLayerResponse(BaseModel):
    """
    GeoJSON-friendly wrapper for a single hazard layer (surge, flood, or
    exposure). `geojson` is passed through untouched so Person 4 can feed
    it straight into Mapbox GL / deck.gl source data.
    """
    region_id: str
    cyclone_id: Optional[str] = None
    layer_type: Literal["surge", "flood", "exposure"]
    generated_at: str  # ISO timestamp
    geojson: dict = Field(..., description="Raw GeoJSON FeatureCollection")


class RegionHazardBundle(BaseModel):
    """All hazard layers for one region, bundled for one map load."""
    region_id: str
    cyclone_id: Optional[str] = None
    surge: Optional[dict] = None
    flood: Optional[dict] = None
    exposure: Optional[dict] = None



class AdvisoryRequest(BaseModel):
    region_id: str
    cyclone_id: str
    language: str = Field(default="en", description="BCP-47-ish code, e.g. 'en', 'hi', 'bn'")
    # Optional overrides -- if omitted, the service pulls current mock/real
    # data for the region itself.
    surge_height_m: Optional[float] = None
    flood_extent_km2: Optional[float] = None
    exposure_score: Optional[float] = None  # 0-1
    bulletin_text: Optional[str] = None
    satellite_image_url: Optional[str] = None


class AdvisoryResponse(BaseModel):
    region_id: str
    cyclone_id: str
    language: str
    severity: SeverityLevel
    affected_areas: List[str]
    recommended_actions: List[str]
    advisory_text: str
    generated_at: str
    model_used: str
    is_fallback: bool = Field(
        default=False,
        description="True if Gemini failed and this is a canned fallback advisory."
    )


class AlertChannel(str, Enum):
    webhook = "webhook"
    email_mock = "email_mock"
    sms_mock = "sms_mock"


class AlertDispatchRequest(BaseModel):
    region_id: str
    cyclone_id: str
    channel: AlertChannel
    advisory: AdvisoryResponse
    recipient: Optional[str] = None  


class AlertDispatchResponse(BaseModel):
    dispatched: bool
    channel: AlertChannel
    logged_at: str
    detail: str
