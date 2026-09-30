
from typing import List, Dict

from app.modeling.config import EXPOSURE_CATEGORY_WEIGHT, EXPOSURE_DEFAULT_WEIGHT


def _shapely_geom(geojson_geom: dict):
    from shapely.geometry import shape
    return shape(geojson_geom)


def _hazard_union(hazard_feature_collection: dict):
    """Merges all polygons in a surge/flood FeatureCollection into one geometry
    for fast contains/distance checks, tagging the max severity value seen."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    if not hazard_feature_collection or not hazard_feature_collection.get("features"):
        return None
    geoms = [shape(f["geometry"]) for f in hazard_feature_collection["features"]]
    return unary_union(geoms)


def _proximity_score(geom, hazard_union) -> float:
    """1.0 if inside/intersecting the hazard zone, decaying to 0 over 5km outside it."""
    if hazard_union is None:
        return 0.0
    if geom.intersects(hazard_union):
        return 1.0
    dist_km = geom.distance(hazard_union) * 111.0
    decay_km = 5.0
    return max(0.0, 1.0 - dist_km / decay_km)


def score_level(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.5:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def score_infrastructure(infrastructure: List[Dict], surge_fc: dict, flood_fc: dict) -> dict:
    """
    infrastructure: list of dicts with 'id', 'category', 'name', 'geometry' (GeoJSON).
    Returns a GeoJSON FeatureCollection for the `exposure` key of the hazard bundle,
    matching the schema's expected properties: infra_type, exposure_score, name.
    """
    surge_union = _hazard_union(surge_fc)
    flood_union = _hazard_union(flood_fc)

    features = []
    scored_rows = []  # (infrastructure_id, score) for callers that want to persist to DB
    for feat in infrastructure:
        geom = _shapely_geom(feat["geometry"])
        surge_p = _proximity_score(geom, surge_union)
        flood_p = _proximity_score(geom, flood_union)
        # take the worse of the two hazards, then weight by criticality
        raw = max(surge_p, flood_p)
        weight = EXPOSURE_CATEGORY_WEIGHT.get(feat["category"], EXPOSURE_DEFAULT_WEIGHT)
        score = round(min(1.0, raw * weight + (0.1 if feat["category"] == "hospital" and raw > 0 else 0.0)), 2)

        features.append({
            "type": "Feature",
            "properties": {
                "infra_type": feat["category"],
                "exposure_score": score,
                "exposure_level": score_level(score),
                "name": feat.get("name") or f"{feat['category']} #{feat['id']}",
            },
            "geometry": feat["geometry"],
        })
        scored_rows.append((feat["id"], score_level(score), score))

    return {"type": "FeatureCollection", "features": features}, scored_rows
