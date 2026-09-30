from typing import List, Dict, Optional, Tuple

from app.modeling.surge_model import peak_surge, build_inundation_zones
from app.modeling.flood_model import build_flood_zones
from app.modeling.exposure_model import score_infrastructure
from app.modeling.config import PILOT_REGION_NAME, PILOT_REGION_ID


def _coastline_geom(coastline_geojson: dict):
    from shapely.geometry import shape
    return shape(coastline_geojson)


def _bundle(region_id: str, cyclone_id: str, surge_fc: dict, flood_fc: dict,
            exposure_fc: dict, peak: dict, bulletin_text: Optional[str]) -> dict:
    # summary_stats mirrors the mock file's shape exactly
    surge_heights = [f["properties"]["surge_height_m"] for f in surge_fc["features"]] or [0]
    flood_depths = [f["properties"]["flood_depth_m"] for f in flood_fc["features"]] or [0]
    exposure_scores = [f["properties"]["exposure_score"] for f in exposure_fc["features"]] or [0]
    affected = sorted({
        f["properties"]["name"] for f in exposure_fc["features"]
        if f["properties"]["exposure_score"] >= 0.5
    })

    return {
        "region_id": region_id,
        "cyclone_id": cyclone_id,
        "surge": surge_fc,
        "flood": flood_fc,
        "exposure": exposure_fc,
        "summary_stats": {
            "max_surge_height_m": max(surge_heights),
            "max_flood_depth_m": max(flood_depths),
            "mean_exposure_score": round(sum(exposure_scores) / len(exposure_scores), 2),
            "affected_areas": affected,
            "peak_surge_time": peak["iso_time"].isoformat() if hasattr(peak["iso_time"], "isoformat") else str(peak["iso_time"]),
        },
        "bulletin_text": bulletin_text,
        "satellite_image_url": None,
    }


def get_hazard_bundle_synthetic(region_id: str, cyclone_id: str, track_points: List[Dict],
                                 coastline_geojson: dict, bbox: Tuple[float, float, float, float],
                                 infrastructure: List[Dict], rainfall_24h_mm: float = 180.0,
                                 bulletin_text: Optional[str] = None) -> dict:
    """No DB required -- everything is passed in. This is what backtest.py
    and the standalone test in tests/ use, and what you can wire the backend
    to directly if the DB isn't up yet on demo day."""
    from app.modeling.elevation import get_default_elevation_grid

    coastline = _coastline_geom(coastline_geojson)
    elevation_grid = get_default_elevation_grid(coastline_geom=coastline)

    peak = peak_surge(track_points, coastline)
    surge_fc = build_inundation_zones(coastline, peak["surge_height_m"], elevation_grid, bbox)
    flood_fc = build_flood_zones(elevation_grid, bbox, rainfall_24h_mm)
    exposure_fc, _scored_rows = score_infrastructure(infrastructure, surge_fc, flood_fc)

    return _bundle(region_id, cyclone_id, surge_fc, flood_fc, exposure_fc, peak, bulletin_text)


def get_hazard_bundle_from_db(sid: str, region_name: str = PILOT_REGION_NAME,
                               region_id: str = PILOT_REGION_ID,
                               bbox: Optional[Tuple[float, float, float, float]] = None,
                               rainfall_24h_mm: float = 180.0,
                               srtm_tif_path: Optional[str] = None,
                               persist: bool = True) -> dict:
    """Full pipeline reading from Person 1's PostGIS tables. `bbox` defaults
    to the pilot region's bbox pulled from the DB if not given. Set
    `persist=True` (default) to also write the surge estimate and per-feature
    exposure scores back into surge_estimates/exposure_scores."""
    from app.modeling import db
    from app.modeling.elevation import get_default_elevation_grid

    track_points = db.fetch_track_points(sid)
    coastline_geojson = db.fetch_coastline_geojson(region_name)
    if coastline_geojson is None:
        raise ValueError(
            f"pilot_regions.coastline is NULL for '{region_name}' -- Person 1 needs to "
            f"populate it (a simple coastline LineString digitized from OSM or GEE is enough)."
        )
    coastline = _coastline_geom(coastline_geojson)

    if bbox is None:
        # fall back to a generous buffer around the coastline's own bounds
        minx, miny, maxx, maxy = coastline.bounds
        pad = 0.15
        bbox = (miny - pad, minx - pad, maxy + pad, maxx + pad)

    elevation_grid = get_default_elevation_grid(coastline_geom=coastline, srtm_tif_path=srtm_tif_path)
    infrastructure = db.fetch_infrastructure(region_name)

    peak = peak_surge(track_points, coastline)
    surge_fc = build_inundation_zones(coastline, peak["surge_height_m"], elevation_grid, bbox)
    flood_fc = build_flood_zones(elevation_grid, bbox, rainfall_24h_mm)
    exposure_fc, scored_rows = score_infrastructure(infrastructure, surge_fc, flood_fc)

    if persist:
        surge_estimate_id = db.write_surge_estimate(
            sid, region_name, peak["iso_time"], peak["surge_height_m"], "empirical", None,
        )
        for infra_id, level, score in scored_rows:
            db.write_exposure_score(surge_estimate_id, infra_id, level, score)

    return _bundle(region_id, sid, surge_fc, flood_fc, exposure_fc, peak, bulletin_text=None)
