
from typing import Tuple

from app.modeling.config import FLOOD_RAINFALL_TO_DEPTH_RATIO, FLOOD_MAX_ELEVATION_M


def estimate_flood_depth_m(rainfall_24h_mm: float) -> float:
    """Very simple: a fraction of 24h rainfall becomes standing water depth
    in poorly-drained low-lying coastal flats. Calibrate
    FLOOD_RAINFALL_TO_DEPTH_RATIO against any historical flood-depth reports
    you can find for backtest events.

    e.g. 210mm of rainfall in 24h * ratio 0.18 -> ~0.04m (4cm) of standing
    depth in poor-drainage flats. Sanity-check any new ratio value against
    that order of magnitude -- standing depth should be centimeters here,
    not meters; a meters-deep result means the coefficient (or the whole
    approach) needs rethinking, not just retuning."""
    return round(max(0.0, (rainfall_24h_mm / 1000.0) * FLOOD_RAINFALL_TO_DEPTH_RATIO), 3)


def build_flood_zones(elevation_grid, bbox: Tuple[float, float, float, float],
                       rainfall_24h_mm: float, grid_step_deg: float = 0.01) -> dict:
    """
    Grid-samples the bbox and flags any cell below FLOOD_MAX_ELEVATION_M as
    flooded to `estimate_flood_depth_m(rainfall_24h_mm)`, independent of
    distance from coast (rainfall flooding isn't coast-bound the way surge is).

    Returns a GeoJSON FeatureCollection for the `flood` key of the hazard bundle.
    """
    from shapely.geometry import box, mapping
    from shapely.ops import unary_union

    depth = estimate_flood_depth_m(rainfall_24h_mm)
    if depth <= 0.05:
        return {"type": "FeatureCollection", "features": []}

    south, west, north, east = bbox
    cells = []
    lat = south
    while lat <= north:
        lon = west
        while lon <= east:
            elev = elevation_grid.elevation_at(lon, lat)
            if elev < FLOOD_MAX_ELEVATION_M:
                cells.append(box(lon, lat, lon + grid_step_deg, lat + grid_step_deg))
            lon += grid_step_deg
        lat += grid_step_deg

    if not cells:
        return {"type": "FeatureCollection", "features": []}

    merged = unary_union(cells)
    geoms = merged.geoms if hasattr(merged, "geoms") else [merged]
    features = [
        {
            "type": "Feature",
            "properties": {"flood_depth_m": depth, "cause": "rainfall_runoff"},
            "geometry": mapping(g),
        }
        for g in geoms
    ]
    return {"type": "FeatureCollection", "features": features}
