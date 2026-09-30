import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "cyclone_db")
DB_USER = os.getenv("DB_USER", "cyclone")
DB_PASSWORD = os.getenv("DB_PASSWORD", "cyclone_dev_pw")


PILOT_REGION_NAME = os.getenv("PILOT_REGION_NAME", "Odisha Coast (Puri-Paradip)")
PILOT_REGION_ID = os.getenv("PILOT_REGION_ID", "pilot-odisha-puri")  

SURGE_PRESSURE_COEFF = 0.020      
SURGE_WIND_COEFF = 0.012          

SURGE_SIZE_REF_RMW_NM = 30.0      
SURGE_SHELF_SLOPE_DEFAULT = 0.0009  
SURGE_SHELF_SLOPE_SUNDARBANS = 0.0006  
                                        
                                        
SURGE_FORWARD_SPEED_PENALTY_KT = 15.0  

# --- Flood (rainfall-runoff bathtub) model ---
FLOOD_RAINFALL_TO_DEPTH_RATIO = 0.18   
FLOOD_MAX_ELEVATION_M = 4.0            

EXPOSURE_CATEGORY_WEIGHT = {
    "hospital": 1.0,
    "shelter": 0.9,       
    "power_line": 0.7,
    "power_substation": 0.85,
    "road": 0.5,
}
EXPOSURE_DEFAULT_WEIGHT = 0.5
