
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from app.modeling.config import (
    SURGE_PRESSURE_COEFF, SURGE_WIND_COEFF, SURGE_SIZE_REF_RMW_NM,
    SURGE_SHELF_SLOPE_DEFAULT, SURGE_FORWARD_SPEED_PENALTY_KT,
)


def size_factor(rmw_nm: Optional[float]) -> float:
    """Larger storms (bigger radius of max winds) push more water -> bigger surge.
    Scales relative to a reference RMW; clamped to a sane range."""
    if not rmw_nm or rmw_nm <= 0:
        return 1.0
    factor = rmw_nm / SURGE_SIZE_REF_RMW_NM
    return max(0.6, min(factor, 1.8))


def shelf_factor(shelf_slope: float) -> float:
    """Shallower shelf slope (smaller number) amplifies surge -- water has
    nowhere to go but up and inland. Normalized so the default Odisha shelf
    slope gives factor 1.0."""
    if shelf_slope <= 0:
        return 1.0
    return max(0.5, min(SURGE_SHELF_SLOPE_DEFAULT / shelf_slope, 2.0))


def forward_speed_factor(storm_speed_kt: Optional[float]) -> float:
    """Very fast-moving storms have less time to pile water up against the
    coast; slow-moving storms cause prolonged, higher surge."""
    if not storm_speed_kt or storm_speed_kt <= 0:
        return 1.0
    if storm_speed_kt <= SURGE_FORWARD_SPEED_PENALTY_KT:
        return 1.0
    excess = storm_speed_kt - SURGE_FORWARD_SPEED_PENALTY_KT
    return max(0.75, 1.0 - 0.01 * excess)


def estimate_surge_height_m(pressure_mb: Optional[float], wind_kt: Optional[float],
                             rmw_nm: Optional[float] = None,
                             storm_speed_kt: Optional[float] = None,
                             shelf_slope: float = SURGE_SHELF_SLOPE_DEFAULT) -> float:
    """Single-point-in-time surge estimate. Returns meters, floored at 0."""
    pressure_term = SURGE_PRESSURE_COEFF * max(0.0, 1013.0 - (pressure_mb or 1013.0))
    wind_term = SURGE_WIND_COEFF * max(0.0, (wind_kt or 0.0) - 64.0)
    base = pressure_term + wind_term
    surge = base * size_factor(rmw_nm) * shelf_factor(shelf_slope) * forward_speed_factor(storm_speed_kt)
    return round(max(0.0, surge), 2)


def closest_approach(track_points: List[Dict], coastline) -> Dict:
    """Finds the track point with the smallest distance to the coastline --
    this is the point used for the peak surge estimate, analogous to
    'landfall' conditions."""
    from shapely.geometry import Point
    best = None
    best_dist = float("inf")
    for tp in track_points:
        pt = Point(tp["lon"], tp["lat"])
        d = coastline.distance(pt)
        if d < best_dist:
            best_dist = d
            best = tp
    if best is None:
        raise ValueError("Empty track_points list")
    return best


def compute_surge_series(track_points: List[Dict], coastline,
                          shelf_slope: float = SURGE_SHELF_SLOPE_DEFAULT) -> List[Dict]:
    """Surge estimate at every track point (for a time-series / animation view).
    Person 4 can use this later for a 'storm progression' slider if there's time."""
    return [
        dict(
            iso_time=tp["iso_time"],
            lon=tp["lon"], lat=tp["lat"],
            surge_height_m=estimate_surge_height_m(
                tp.get("pressure_mb"), tp.get("wind_kt"), tp.get("rmw_nm"),
                tp.get("storm_speed_kt"), shelf_slope,
            ),
        )
        for tp in track_points
    ]


def peak_surge(track_points: List[Dict], coastline, shelf_slope: float = SURGE_SHELF_SLOPE_DEFAULT) -> Dict:
    """The single number the rest of the pipeline (flood, exposure, advisory)
    keys off of: surge height at closest approach to the pilot region's coast."""
    cp = closest_approach(track_points, coastline)
    height = estimate_surge_height_m(
        cp.get("pressure_mb"), cp.get("wind_kt"), cp.get("rmw_nm"),
        cp.get("storm_speed_kt"), shelf_slope,
    )
    return dict(iso_time=cp["iso_time"], surge_height_m=height, closest_point=(cp["lon"], cp["lat"]))


def build_inundation_zones(coastline, surge_height_m: float, elevation_grid,
                            bbox: Tuple[float, float, float, float],
                            grid_step_deg: float = 0.01,
                            max_inland_km: float = 12.0) -> dict:
    """
    Bathtub-model inundation extent: samples a grid over the bbox, and for
    each cell within `max_inland_km` of the coastline, checks the synthetic/
    real elevation against two thresholds to produce an 'inner' (more severe,
    elevation well below surge height) and 'outer' (marginal, elevation just
    below surge height) zone -- mirroring the two-band style already used in
    the backend's mock data / schema.

    Returns a GeoJSON FeatureCollection ready to drop straight into the
    `surge` key of the hazard bundle Person 3's API serves.
    """
    from shapely.geometry import Point, box, mapping
    from shapely.ops import unary_union

    south, west, north, east = bbox
    inner_cells, outer_cells = [], []

    lat = south
    while lat <= north:
        lon = west
        while lon <= east:
            pt = Point(lon, lat)
            dist_km = coastline.distance(pt) * 111.0  # degrees -> km, fine at this scale
            if dist_km <= max_inland_km:
                elev = elevation_grid.elevation_at(lon, lat)
                cell = box(lon, lat, lon + grid_step_deg, lat + grid_step_deg)
                if elev < surge_height_m * 0.5:
                    inner_cells.append(cell)
                elif elev < surge_height_m:
                    outer_cells.append(cell)
            lon += grid_step_deg
        lat += grid_step_deg

    features = []
    if inner_cells:
        merged = unary_union(inner_cells)
        geoms = merged.geoms if hasattr(merged, "geoms") else [merged]
        for g in geoms:
            features.append({
                "type": "Feature",
                "properties": {"surge_height_m": surge_height_m, "zone": "coastal-inner"},
                "geometry": mapping(g),
            })
    if outer_cells:
        merged = unary_union(outer_cells)
        geoms = merged.geoms if hasattr(merged, "geoms") else [merged]
        for g in geoms:
            features.append({
                "type": "Feature",
                "properties": {"surge_height_m": round(surge_height_m * 0.6, 2), "zone": "coastal-outer"},
                "geometry": mapping(g),
            })

    return {"type": "FeatureCollection", "features": features}
