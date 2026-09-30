
import os
from dotenv import load_dotenv

load_dotenv()

# --- Database ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "cyclone_db")
DB_USER = os.getenv("DB_USER", "cyclone")
DB_PASSWORD = os.getenv("DB_PASSWORD", "cyclone_dev_pw")

DB_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- GEE ---
GEE_SERVICE_ACCOUNT = os.getenv("GEE_SERVICE_ACCOUNT")
GEE_PRIVATE_KEY_PATH = os.getenv("GEE_PRIVATE_KEY_PATH", "./config/gee-service-account.json")
GEE_PROJECT_ID = os.getenv("GEE_PROJECT_ID")

# --- Met APIs ---
NOAA_GFS_BASE_URL = os.getenv("NOAA_GFS_BASE_URL", "https://nomads.ncep.noaa.gov/dods/gfs_0p25")
OPEN_METEO_BASE_URL = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1")

# --- Overpass ---
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

# --- Pilot region bbox: (south, west, north, east) ---
_bbox_str = os.getenv("PILOT_BBOX", "19.5,85.5,20.6,86.8")
PILOT_BBOX = tuple(float(x) for x in _bbox_str.split(","))  # (south, west, north, east)
PILOT_REGION_NAME = "Odisha Coast (Puri-Paradip)"


def gee_bbox_ee_geometry():
    """Returns the pilot bbox as an ee.Geometry.Rectangle (lazy import so this
    module doesn't hard-require earthengine-api just to read config)."""
    import ee
    south, west, north, east = PILOT_BBOX
    return ee.Geometry.Rectangle([west, south, east, north])
