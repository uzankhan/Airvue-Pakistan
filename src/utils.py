import os
import time
import logging
import urllib.parse
from dotenv import load_dotenv
import datetime
import subprocess
import sys

# 🔥 Auto-install psycopg2-binary if missing
try:
    import psycopg2
except ImportError:
    print("⚠️ psycopg2 not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
    import psycopg2

load_dotenv()

def setup_logging():
    logging.basicConfig(
        filename='logs/project.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def get_snowflake_connection(retries=3, delay=5):
    db_url = os.getenv('SUPABASE_DB_URL')
    if not db_url:
        raise ValueError("❌ SUPABASE_DB_URL missing in .env file")
    
    parsed = urllib.parse.urlparse(db_url)
    host = parsed.hostname
    port = parsed.port or 5432
    user = parsed.username
    password = parsed.password
    dbname = parsed.path.lstrip('/')
    
    if not user or not password:
        raise ValueError("❌ Invalid DB URL format (missing user/password)")
    
    for attempt in range(retries):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname
            )
            conn.autocommit = False
            return conn
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            else:
                raise e

def calculate_aqi(pm25):
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
