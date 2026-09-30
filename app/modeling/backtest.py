import argparse
from shapely.geometry import LineString

from app.modeling.surge_model import peak_surge
from app.modeling.config import SURGE_PRESSURE_COEFF, SURGE_WIND_COEFF, SURGE_SHELF_SLOPE_DEFAULT, SURGE_SHELF_SLOPE_SUNDARBANS

ODISHA_COASTLINE_APPROX = LineString([(85.70, 19.70), (85.95, 19.90), (86.20, 20.20)])


HARDCODED_EVENTS = {
    "FANI_2019": {
        "track_points": [
            dict(iso_time="2019-05-02T18:00:00Z", lon=86.60, lat=18.90, wind_kt=100, pressure_mb=938, storm_speed_kt=11, rmw_nm=25),
            dict(iso_time="2019-05-03T00:00:00Z", lon=86.30, lat=19.30, wind_kt=105, pressure_mb=932, storm_speed_kt=10, rmw_nm=25),
            dict(iso_time="2019-05-03T06:00:00Z", lon=85.90, lat=19.80, wind_kt=100, pressure_mb=938, storm_speed_kt=12, rmw_nm=28),  # ~landfall, near Puri
        ],
        "documented_surge_range_m": (1.5, 2.1),
        "shelf_slope": SURGE_SHELF_SLOPE_DEFAULT,
        "note": "Very severe cyclonic storm, landfall near Puri, Odisha, 3 May 2019.",
    },
    "AMPHAN_2020": {
        "track_points": [
            dict(iso_time="2020-05-20T06:00:00Z", lon=88.60, lat=20.40, wind_kt=90, pressure_mb=950, storm_speed_kt=18, rmw_nm=35),
            dict(iso_time="2020-05-20T12:00:00Z", lon=88.55, lat=21.00, wind_kt=85, pressure_mb=955, storm_speed_kt=20, rmw_nm=35),  # ~landfall, Sundarbans/WB coast
        ],
        "documented_surge_range_m": (2.5, 4.0),
        "shelf_slope": SURGE_SHELF_SLOPE_SUNDARBANS,
        "note": "Super cyclonic storm weakening to VSCS, landfall near Sundarbans, 20 May 2020. "
                "Uses the Sundarbans shelf-slope constant (shallower/funnel-shaped delta) rather "
                "than the Odisha default -- this region-specific tuning, not just global "
                "coefficients, is what brings the estimate into range. Locally, delta funneling "
                "reportedly pushed some observations even higher than this range; the model "
                "still doesn't capture fine-grained channel geometry.",
    },
}


def run_hardcoded():
    print(f"{'Event':<14} {'Predicted (m)':<15} {'Documented range (m)':<22} {'Verdict'}")
    print("-" * 70)
    for name, event in HARDCODED_EVENTS.items():
        peak = peak_surge(event["track_points"], ODISHA_COASTLINE_APPROX,
                           shelf_slope=event.get("shelf_slope", SURGE_SHELF_SLOPE_DEFAULT))
        lo, hi = event["documented_surge_range_m"]
        verdict = "OK (within range)" if lo <= peak["surge_height_m"] <= hi else "OUT OF RANGE -- retune config.py"
        print(f"{name:<14} {peak['surge_height_m']:<15} {f'{lo}-{hi}':<22} {verdict}")
        print(f"   note: {event['note']}")
    print("\nCurrent calibration: SURGE_PRESSURE_COEFF="
          f"{SURGE_PRESSURE_COEFF}, SURGE_WIND_COEFF={SURGE_WIND_COEFF}")
    print("If a verdict is OUT OF RANGE, adjust these two constants in "
          "src/config.py first (they have the largest effect), rerun, repeat.")


def run_db(sid: str, region_name: str):
    from app.modeling import db
    track_points = db.fetch_track_points(sid)
    coastline_geojson = db.fetch_coastline_geojson(region_name)
    from shapely.geometry import shape
    coastline = shape(coastline_geojson)
    peak = peak_surge(track_points, coastline)
    print(f"sid={sid}: predicted peak surge = {peak['surge_height_m']} m at {peak['iso_time']}")
    print("Compare this against the real post-storm surge report for this event "
          "(IMD Cyclone Warning Division reports, or published papers) and tune "
          "src/config.py accordingly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest the surge model against historical cyclones")
    parser.add_argument("--source", choices=["hardcoded", "db"], default="hardcoded")
    parser.add_argument("--sid", help="IBTrACS SID, required if --source db")
    parser.add_argument("--region-name", default="Odisha Coast (Puri-Paradip)")
    args = parser.parse_args()

    if args.source == "hardcoded":
        run_hardcoded()
    else:
        if not args.sid:
            parser.error("--sid is required with --source db")
        run_db(args.sid, args.region_name)
