
import json
import time
import requests

from src.config import OVERPASS_URL, PILOT_BBOX, PILOT_REGION_NAME
from src.db import get_conn, get_pilot_region_id

# bbox for Overpass is (south, west, north, east) — matches our PILOT_BBOX order
BBOX_STR = ",".join(str(x) for x in PILOT_BBOX)

# Category -> Overpass QL filter fragment. Each produces node/way/relation queries.
QUERIES = {
    "hospital": f'node["amenity"="hospital"]({BBOX_STR});way["amenity"="hospital"]({BBOX_STR});',
    "shelter": (
        f'node["amenity"="shelter"]({BBOX_STR});'
        f'node["emergency"="shelter"]({BBOX_STR});'
        f'way["emergency"="shelter"]({BBOX_STR});'
        # Cyclone shelters in coastal India are often tagged as community
        # centres / schools used as shelters — widen the net a bit:
        f'node["building"="civic"]({BBOX_STR});'
    ),
    "power_line": f'way["power"="line"]({BBOX_STR});way["power"="minor_line"]({BBOX_STR});',
    "power_substation": f'node["power"="substation"]({BBOX_STR});way["power"="substation"]({BBOX_STR});',
    "road_primary": (
        f'way["highway"~"^(primary|trunk|motorway)$"]({BBOX_STR});'
    ),
    "road_secondary": f'way["highway"~"^(secondary|tertiary)$"]({BBOX_STR});',
}


def build_overpass_query(fragment: str) -> str:
    return f"""
    [out:json][timeout:120];
    (
      {fragment}
    );
    out body geom;
    """


def fetch_category(category: str, fragment: str, retries: int = 3):
    query = build_overpass_query(fragment)
    
    headers = {
        "User-Agent": "cyclone-early-warning-platform/1.0 (hackathon project; contact: set-your-email-here)",
        "Accept": "application/json",
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=180)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[osm] {category}: attempt {attempt} failed ({e}); retrying...")
            time.sleep(5 * attempt)
    raise RuntimeError(f"[osm] Failed to fetch category '{category}' after {retries} attempts")


def element_to_geojson_geom(element: dict):
    """Convert an Overpass element (node/way with 'geom') into a GeoJSON geometry."""
    if element["type"] == "node":
        return {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
    if element["type"] == "way" and "geometry" in element:
        coords = [[pt["lon"], pt["lat"]] for pt in element["geometry"]]
        # Treat closed ways with building/area-like tags as polygons, else lines.
        is_closed = len(coords) > 2 and coords[0] == coords[-1]
        tags = element.get("tags", {})
        if is_closed and ("building" in tags or "amenity" in tags):
            return {"type": "Polygon", "coordinates": [coords]}
        return {"type": "LineString", "coordinates": coords}
    return None


def save_category_to_db(category: str, data: dict, region_id: int):
    rows = []
    for el in data.get("elements", []):
        geom = element_to_geojson_geom(el)
        if geom is None:
            continue
        tags = el.get("tags", {})
        rows.append((
            region_id,
            el["id"],
            el["type"],
            category,
            tags.get("highway") or tags.get("power") or tags.get("amenity") or tags.get("emergency"),
            tags.get("name"),
            json.dumps(tags),
            json.dumps(geom),
        ))

    if not rows:
        print(f"[osm] {category}: 0 features found")
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO infrastructure
                        (region_id, osm_id, osm_type, category, subcategory,
                         name, tags, geom)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb,
                            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    """,
                    r,
                )
    print(f"[osm] {category}: saved {len(rows)} features")


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            region_id = get_pilot_region_id(cur, PILOT_REGION_NAME)

    print(f"[osm] Extracting infrastructure for bbox {BBOX_STR} (region_id={region_id})")
    for category, fragment in QUERIES.items():
        print(f"[osm] Fetching category: {category}")
        data = fetch_category(category, fragment)
        save_category_to_db(category, data, region_id)
        time.sleep(2)  # be polite to the public Overpass instance

    print("[osm] Done.")


if __name__ == "__main__":
    main()