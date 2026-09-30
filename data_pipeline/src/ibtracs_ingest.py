
import argparse
import io
import pandas as pd
import requests

from src.db import get_conn

IBTRACS_NI_URL = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-"
    "climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NI.list.v04r01.csv"
)


def download_ibtracs_ni(cache_path: str = "data/ibtracs_ni.csv") -> pd.DataFrame:
    import os
    if os.path.exists(cache_path):
        print(f"[ibtracs] Using cached file: {cache_path}")
        return pd.read_csv(cache_path, skiprows=[1], low_memory=False)

    print(f"[ibtracs] Downloading {IBTRACS_NI_URL} ...")
    resp = requests.get(IBTRACS_NI_URL, timeout=120)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        f.write(resp.content)
    # IBTrACS CSVs have a units row as line 2 — skip it when parsing
    return pd.read_csv(io.BytesIO(resp.content), skiprows=[1], low_memory=False)


def filter_storms(df: pd.DataFrame, sids=None, season=None, name=None) -> pd.DataFrame:
    out = df
    if sids:
        out = out[out["SID"].isin(sids)]
    if season:
        out = out[out["SEASON"] == season]
    if name:
        out = out[out["NAME"].str.upper() == name.upper()]
    return out


def upsert_event(cur, sid: str, name: str, season: int, basin: str):
    cur.execute(
        """
        INSERT INTO cyclone_events (sid, name, season, basin, source)
        VALUES (%s, %s, %s, %s, 'IBTrACS')
        ON CONFLICT (sid) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (sid, name, season, basin),
    )
    return cur.fetchone()[0]


def insert_track_points(cur, event_id: int, storm_df: pd.DataFrame):
    rows = []
    for _, row in storm_df.iterrows():
        try:
            lat, lon = float(row["LAT"]), float(row["LON"])
        except (ValueError, TypeError):
            continue
        rows.append((
            event_id,
            row["ISO_TIME"],
            lon, lat,
            _safe_float(row.get("USA_WIND") or row.get("WMO_WIND")),
            _safe_float(row.get("USA_PRES") or row.get("WMO_PRES")),
            _safe_float(row.get("STORM_SPEED")),
            _safe_float(row.get("STORM_DIR")),
            _safe_float(row.get("USA_RMW")),
            row.get("USA_SSHS") or row.get("NATURE"),
        ))

    for r in rows:
        cur.execute(
            """
            INSERT INTO cyclone_track_points
                (event_id, iso_time, geom, wind_kt, pressure_mb,
                 storm_speed_kt, storm_dir_deg, rmw_nm, category)
            VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s, %s, %s, %s, %s, %s)
            """,
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]),
        )
    return len(rows)


def _safe_float(val):
    try:
        f = float(val)
        return f if f not in (-999, 9999) else None  # IBTrACS missing-value sentinels
    except (ValueError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description="Ingest IBTrACS North Indian Ocean cyclone tracks")
    parser.add_argument("--sids", nargs="*", help="Specific IBTrACS storm IDs")
    parser.add_argument("--season", type=int, help="Filter by season/year")
    parser.add_argument("--name", help="Filter by storm name, e.g. FANI")
    args = parser.parse_args()

    df = download_ibtracs_ni()
    filtered = filter_storms(df, sids=args.sids, season=args.season, name=args.name)

    if filtered.empty:
        print("[ibtracs] No matching storms found for the given filters.")
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            for sid, storm_df in filtered.groupby("SID"):
                name = storm_df["NAME"].iloc[0]
                season = int(storm_df["SEASON"].iloc[0])
                basin = storm_df["BASIN"].iloc[0]
                event_id = upsert_event(cur, sid, name, season, basin)
                n = insert_track_points(cur, event_id, storm_df)
                print(f"[ibtracs] {name} ({sid}, {season}): inserted {n} track points")

    print("[ibtracs] Done.")


if __name__ == "__main__":
    main()
