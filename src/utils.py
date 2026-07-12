import os
import time
import logging
import snowflake.connector
from dotenv import load_dotenv
import datetime

load_dotenv()

# ------------- LOGGING SETUP -------------
def setup_logging():
    logging.basicConfig(
        filename='logs/project.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

# ------------- SNOWFLAKE CONNECTION (With Retry) -------------
def get_snowflake_connection(retries=3, delay=5):
    """Returns a Snowflake connection with retry logic."""
    for attempt in range(retries):
        try:
            conn = snowflake.connector.connect(
                user=os.getenv('SNOWFLAKE_USER'),
                password=os.getenv('SNOWFLAKE_PASSWORD'),
                account=os.getenv('SNOWFLAKE_ACCOUNT'),
                warehouse=os.getenv('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH'),
                database=os.getenv('SNOWFLAKE_DATABASE', 'SMART_CITY_AQI'),
                schema=os.getenv('SNOWFLAKE_SCHEMA_RAW', 'RAW')
            )
            return conn
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            else:
                raise e

# ------------- EPA AQI CALCULATOR -------------
def calculate_aqi(pm25):
    """EPA standard AQI calculator. Returns (aqi_value, category)."""
    if pm25 is None or pm25 < 0:
        return None, None
    breakpoints = [
        (0.0, 12.0, 0, 50, "GOOD"),
        (12.1, 35.4, 51, 100, "MODERATE"),
        (35.5, 55.4, 101, 150, "UNHEALTHY FOR SENSITIVE"),
        (55.5, 150.4, 151, 200, "UNHEALTHY"),
        (150.5, 250.4, 201, 300, "VERY UNHEALTHY"),
        (250.5, 500.4, 301, 500, "HAZARDOUS"),
    ]
    for c_lo, c_hi, i_lo, i_hi, label in breakpoints:
        if c_lo <= pm25 <= c_hi:
            aqi = ((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo
            return round(aqi, 2), label
    return None, None

# ------------- HEALTH RISK MAPPER -------------
def get_health_risk(category):
    risk_map = {
        "GOOD": "LOW",
        "MODERATE": "LOW",
        "UNHEALTHY FOR SENSITIVE": "MEDIUM",
        "UNHEALTHY": "HIGH",
        "VERY UNHEALTHY": "HIGH",
        "HAZARDOUS": "CRITICAL"
    }
    return risk_map.get(category, "UNKNOWN")