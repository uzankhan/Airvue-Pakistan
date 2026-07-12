import os
import sys
import time
import requests
import logging
import datetime
import threading
import queue
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils import setup_logging, get_snowflake_connection

load_dotenv()
logger = setup_logging()

# ------------- CONFIG -------------
API_KEY = os.getenv('OPENAQ_API_KEY')
BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": API_KEY}
q = queue.Queue()

# ------------- API CALLS (With Retry) -------------
def fetch_url(url, params=None, retries=2):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Attempt {attempt+1} failed: {resp.status_code}")
            time.sleep(1)
        except Exception as e:
            logger.error(f"Attempt {attempt+1} error: {e}")
            time.sleep(1)
    return None

def get_pakistan_locations():
    """Fetch all Pakistan locations."""
    all_locations = []
    page = 1
    while True:
        data = fetch_url(f"{BASE_URL}/locations", params={"country_id": "PK", "limit": 100, "page": page})
        if not data or not data.get("results"):
            break
        all_locations.extend(data["results"])
        if len(data["results"]) < 100:
            break
        page += 1
        time.sleep(0.5)
    logger.info(f"📍 Found {len(all_locations)} locations in Pakistan.")
    return all_locations

def fetch_location_data(loc):
    """Fetch latest + 24h historical data for a location (with error handling)."""
    loc_id = loc["id"]
    # 🔥 Fix: City name null ho toh 'Unknown' daal do
    city_name = loc.get("locality") or loc.get("city") or "Unknown City"
    
    records = []
    
    # 1. Get LATEST measurements
    latest_data = fetch_url(f"{BASE_URL}/locations/{loc_id}/latest")
    if latest_data:
        for sensor in latest_data.get("results", []):
            # 🔥 FIX: Check if 'parameter' exists
            if 'parameter' not in sensor:
                continue
            param = sensor["parameter"].get("name")
            if param not in ["pm25", "pm10"]:
                continue
            records.append({
                "location_id": loc_id,
                "station_name": loc.get("name", "Unknown"),
                "city": city_name,
                "country_code": "PK",
                "latitude": loc["coordinates"]["latitude"],
                "longitude": loc["coordinates"]["longitude"],
                "pollutant_type": param,
                "pollutant_value": sensor.get("latest", {}).get("value"),
                "unit": sensor["parameter"].get("units", ""),
                "recorded_at": sensor.get("latest", {}).get("datetime")
            })
    
    # 2. Get HISTORICAL data (last 24h) - agar fail ho toh skip
    try:
        sensors_data = fetch_url(f"{BASE_URL}/locations/{loc_id}/sensors")
        if sensors_data:
            for sensor in sensors_data.get("results", []):
                # 🔥 FIX: Check if 'parameter' exists
                if 'parameter' not in sensor:
                    continue
                param = sensor["parameter"].get("name")
                if param not in ["pm25", "pm10"]:
                    continue
                sensor_id = sensor.get("id")
                if not sensor_id:
                    continue
                    
                date_from = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat() + "Z"
                date_to = datetime.datetime.utcnow().isoformat() + "Z"
                hist_data = fetch_url(
                    f"{BASE_URL}/sensors/{sensor_id}/measurements",
                    params={"date_from": date_from, "date_to": date_to, "limit": 50}
                )
                if hist_data:
                    for meas in hist_data.get("results", []):
                        records.append({
                            "location_id": loc_id,
                            "station_name": loc.get("name", "Unknown"),
                            "city": city_name,
                            "country_code": "PK",
                            "latitude": loc["coordinates"]["latitude"],
                            "longitude": loc["coordinates"]["longitude"],
                            "pollutant_type": param,
                            "pollutant_value": meas.get("value"),
                            "unit": sensor["parameter"].get("units", ""),
                            "recorded_at": meas.get("datetime")
                        })
    except Exception as e:
        logger.warning(f"Historical fetch failed for {loc_id}: {e}")
    
    return records

# ------------- SNOWFLAKE INSERTER -------------
def insert_openaq_batch(records):
    if not records:
        return
    conn = None
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        for rec in records:
            cursor.execute("""
                INSERT INTO RAW.OPENAQ_RAW 
                (location_id, station_name, city, country_code, latitude, longitude, pollutant_type, pollutant_value, unit, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (rec["location_id"], rec["station_name"], rec["city"], rec["country_code"],
                  rec["latitude"], rec["longitude"], rec["pollutant_type"], rec["pollutant_value"],
                  rec["unit"], rec["recorded_at"]))
        conn.commit()
        logger.info(f"✅ Inserted {len(records)} OpenAQ records.")
        print(f"✅ {len(records)} OpenAQ records sent to Snowflake.")
    except Exception as e:
        logger.error(f"❌ Snowflake insert failed: {e}")
        print(f"❌ Error: {e}")
    finally:
        if conn:
            conn.close()

# ------------- CONSUMER -------------
def consumer():
    while True:
        records = q.get()
        if records is None:
            break
        insert_openaq_batch(records)
        q.task_done()

# ------------- PRODUCER -------------
def producer():
    locations = get_pakistan_locations()
    batch_size = 30
    current_batch = []
    
    for idx, loc in enumerate(locations):
        city_name = loc.get("locality") or loc.get("city") or "Unknown"
        print(f"🔄 Fetching data for {city_name}...")
        recs = fetch_location_data(loc)
        if recs:
            current_batch.extend(recs)
        
        if len(current_batch) >= batch_size or idx == len(locations) - 1:
            if current_batch:
                q.put(current_batch)
                current_batch = []
        
        time.sleep(1)  # Rate limit
    
    if current_batch:
        q.put(current_batch)
    q.put(None)  # Stop signal

# ------------- MAIN -------------
if __name__ == "__main__":
    print("🌍 Starting OpenAQ Fetcher (Advanced - Fixed)...")
    cons_thread = threading.Thread(target=consumer, daemon=True)
    cons_thread.start()
    producer()
    q.join()
    print("✅ OpenAQ data fetch complete!")