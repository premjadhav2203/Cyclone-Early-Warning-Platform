
import argparse
import json
from datetime import datetime, timezone
import requests
from src.config import OPEN_METEO_BASE_URL, PILOT_BBOX
from src.db import get_conn

JTWC_NORTH_INDIAN_WARNINGS_URL = "https://www.metoc.navy.mil/jtwc/products/io-io.txt"
IMD_BULLETIN_PAGE_URL = "https://mausam.imd.gov.in/imd_latest/contents/cyclone.php"


def fetch_open_meteo(lat: float, lon: float) -> dict:
    """Forecast wind/pressure/precip at a point — cheapest, most reliable feed."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "surface_pressure,wind_speed_10m,wind_gusts_10m,precipitation",
        "forecast_days": 5,
        "timezone": "UTC",
    }
    resp = requests.get(f"{OPEN_METEO_BASE_URL}/forecast", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_jtwc_warning() -> str:
    """Raw text bulletin for the North Indian Ocean basin. Returns '' on
    failure rather than raising — met feeds are flaky and one down source
    shouldn't kill the pipeline run."""
    try:
        resp = requests.get(JTWC_NORTH_INDIAN_WARNINGS_URL, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"[met] JTWC fetch failed (non-fatal): {e}")
        return ""


def fetch_imd_bulletin_html() -> str:
    """Best-effort raw HTML pull. See module docstring — this is intentionally
    not a robust parser. Store raw, let the LLM layer extract meaning."""
    try:
        resp = requests.get(IMD_BULLETIN_PAGE_URL, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"[met] IMD fetch failed (non-fatal, no public API — expected): {e}")
        return ""


def save_bulletin(source: str, storm_name: str, raw_text: str = None,
                   raw_json: dict = None, lat: float = None, lon: float = None):
    if not raw_text and not raw_json:
        print(f"[met] {source}: nothing to save, skipping")
        return

    geom_sql = "NULL"
    params_extra = []
    if lat is not None and lon is not None:
        geom_sql = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)"
        params_extra = [lon, lat]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO met_bulletins
                    (source, storm_name, issued_at, raw_text, raw_json, geom)
                VALUES (%s, %s, %s, %s, %s::jsonb, {geom_sql})
                """,
                [source, storm_name, datetime.now(timezone.utc),
                 raw_text, json.dumps(raw_json) if raw_json else None] + params_extra,
            )
    print(f"[met] Saved bulletin from {source}")


def main():
    parser = argparse.ArgumentParser(description="Pull met bulletins for a point/storm")
    parser.add_argument("--lat", type=float, default=(PILOT_BBOX[0] + PILOT_BBOX[2]) / 2,
                         help="Latitude (defaults to pilot region center)")
    parser.add_argument("--lon", type=float, default=(PILOT_BBOX[1] + PILOT_BBOX[3]) / 2,
                         help="Longitude (defaults to pilot region center)")
    parser.add_argument("--storm-name", default=None, help="Storm name if tracking a live event")
    args = parser.parse_args()

    print(f"[met] Fetching Open-Meteo forecast at ({args.lat}, {args.lon})")
    om_data = fetch_open_meteo(args.lat, args.lon)
    save_bulletin("OPEN_METEO", args.storm_name, raw_json=om_data, lat=args.lat, lon=args.lon)

    print("[met] Fetching JTWC North Indian Ocean warning text")
    jtwc_text = fetch_jtwc_warning()
    save_bulletin("JTWC", args.storm_name, raw_text=jtwc_text)

    print("[met] Fetching IMD bulletin page")
    imd_html = fetch_imd_bulletin_html()
    save_bulletin("IMD", args.storm_name, raw_text=imd_html)

    print("[met] Done. (GFS raw GRIB ingestion not included — Open-Meteo covers "
          "the same underlying model output for hackathon purposes; add "
          "src/gfs_raw.py later only if you need fields Open-Meteo doesn't expose.)")


if __name__ == "__main__":
    main()
