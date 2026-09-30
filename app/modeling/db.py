from contextlib import contextmanager
from typing import List, Dict, Optional

from app.modeling.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


@contextmanager
def get_conn():
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_event_id(cur, sid: str) -> int:
    cur.execute("SELECT id FROM cyclone_events WHERE sid = %s", (sid,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Cyclone event '{sid}' not found -- has Person 1 run ibtracs_ingest for it?")
    return row[0]


def get_region_id(cur, region_name: str) -> int:
    cur.execute("SELECT id FROM pilot_regions WHERE name = %s", (region_name,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Pilot region '{region_name}' not found -- did schema.sql run?")
    return row[0]


def fetch_track_points(sid: str) -> List[Dict]:
    """Returns track points ordered by time for one cyclone, as plain dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            event_id = get_event_id(cur, sid)
            cur.execute(
                """
                SELECT iso_time, ST_X(geom), ST_Y(geom), wind_kt, pressure_mb,
                       storm_speed_kt, storm_dir_deg, rmw_nm, category
                FROM cyclone_track_points
                WHERE event_id = %s
                ORDER BY iso_time
                """,
                (event_id,),
            )
            rows = cur.fetchall()
    return [
        dict(
            iso_time=r[0], lon=_to_float(r[1]), lat=_to_float(r[2]),
            wind_kt=_to_float(r[3]), pressure_mb=_to_float(r[4]),
            storm_speed_kt=_to_float(r[5]), storm_dir_deg=_to_float(r[6]),
            rmw_nm=_to_float(r[7]), category=r[8],
        )
        for r in rows
    ]


def _to_float(val):
    """Postgres NUMERIC columns come back as decimal.Decimal via psycopg2,
    which doesn't mix with plain floats in the surge formula's arithmetic
    (raises TypeError). Cast everything to float at the DB boundary so
    nothing downstream needs to know or care."""
    return None if val is None else float(val)


def fetch_infrastructure(region_name: str) -> List[Dict]:
    """Returns all infrastructure features for a region as plain dicts with
    geometry as GeoJSON (so callers can build shapely geometries without this
    module needing to depend on shapely itself)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            region_id = get_region_id(cur, region_name)
            cur.execute(
                """
                SELECT id, category, subcategory, name, ST_AsGeoJSON(geom)
                FROM infrastructure
                WHERE region_id = %s
                """,
                (region_id,),
            )
            rows = cur.fetchall()
    import json
    return [
        dict(id=r[0], category=r[1], subcategory=r[2], name=r[3], geometry=json.loads(r[4]))
        for r in rows
    ]


def fetch_coastline_geojson(region_name: str) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ST_AsGeoJSON(coastline) FROM pilot_regions WHERE name = %s",
                (region_name,),
            )
            row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    import json
    return json.loads(row[0])


def write_surge_estimate(sid: str, region_name: str, valid_time, surge_height_m: float,
                          method: str, inundation_geojson: Optional[dict]) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            event_id = get_event_id(cur, sid)
            region_id = get_region_id(cur, region_name)
            geom_sql = "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)" if inundation_geojson else "NULL"
            import json
            params = [event_id, region_id, valid_time, surge_height_m, method]
            if inundation_geojson:
                params.append(json.dumps(inundation_geojson))
            cur.execute(
                f"""
                INSERT INTO surge_estimates (event_id, region_id, valid_time, surge_height_m, method, geom)
                VALUES (%s, %s, %s, %s, %s, {geom_sql})
                RETURNING id
                """,
                params,
            )
            return cur.fetchone()[0]


def write_exposure_score(surge_estimate_id: int, infrastructure_id: int,
                          exposure_level: str, score: float) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO exposure_scores (surge_estimate_id, infrastructure_id, exposure_level, score)
                VALUES (%s, %s, %s, %s)
                """,
                (surge_estimate_id, infrastructure_id, exposure_level, score),
            )
