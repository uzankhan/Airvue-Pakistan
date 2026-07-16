import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import random
import math
import datetime
import threading
import queue
import csv
import logging

from src.utils import setup_logging, get_snowflake_connection, calculate_aqi, get_health_risk

logger = setup_logging()

# ------------- SENSOR CONFIGURATION -------------
SENSORS = [
    {"sensor_id": "PKS_KHI_IND_01", "city": "Karachi", "zone": "industrial"},
    {"sensor_id": "PKS_KHI_TRF_02", "city": "Karachi", "zone": "traffic"},
    {"sensor_id": "PKS_LHR_RES_01", "city": "Lahore", "zone": "residential"},
    {"sensor_id": "PKS_LHR_IND_02", "city": "Lahore", "zone": "industrial"},
    {"sensor_id": "PKS_ISB_PRK_01", "city": "Islamabad", "zone": "park"},
    {"sensor_id": "PKS_ISB_TRF_02", "city": "Islamabad", "zone": "traffic"},
    {"sensor_id": "PKS_PEW_IND_01", "city": "Peshawar", "zone": "industrial"},
    {"sensor_id": "PKS_PEW_RES_02", "city": "Peshawar", "zone": "residential"},
    {"sensor_id": "PKS_MUL_TRF_01", "city": "Multan", "zone": "traffic"},
    {"sensor_id": "PKS_MUL_PRK_02", "city": "Multan", "zone": "park"},
]

ZONE_BASE = {
    "industrial": {"pm25": (80, 120), "co2": (600, 900), "temp": (30, 42)},
    "traffic": {"pm25": (55, 80), "co2": (500, 700), "temp": (28, 40)},
    "residential": {"pm25": (25, 50), "co2": (420, 500), "temp": (25, 38)},
    "park": {"pm25": (8, 20), "co2": (400, 430), "temp": (22, 35)},
}

CSV_FILE = "data/iot_readings.csv"
q = queue.Queue()

def generate_reading(sensor):
    zone = sensor["zone"]
    base_pm25_low, base_pm25_high = ZONE_BASE[zone]["pm25"]
    base_co2_low, base_co2_high = ZONE_BASE[zone]["co2"]
    base_temp_low, base_temp_high = ZONE_BASE[zone]["temp"]
    
    hour = datetime.datetime.now().hour
    time_factor = 1.0 + 0.3 * math.sin((hour - 8) * math.pi / 12)
    
    pm25 = random.uniform(base_pm25_low, base_pm25_high) * time_factor * random.uniform(0.85, 1.15)
    if random.random() < 0.15:
        pm25 *= random.uniform(2.5, 4.0)
    pm25 = max(0, min(500, pm25))
    
    pm10 = pm25 * random.uniform(1.0, 1.2)
    co2 = random.uniform(base_co2_low, base_co2_high) * random.uniform(0.85, 1.15)
    temp = random.uniform(base_temp_low, base_temp_high) * random.uniform(0.85, 1.15)
    humidity = random.uniform(10, 90)
    wind = random.uniform(0, 60)
    
    aqi_value, severity = calculate_aqi(pm25)
    
    reading = {
        "sensor_id": sensor["sensor_id"],
        "city": sensor["city"],
        "zone_type": zone,
        "pm25": round(pm25, 2),
        "pm10": round(pm10, 2),
        "co2_ppm": round(co2, 2),
        "temperature_c": round(temp, 2),
        "humidity_pct": round(humidity, 2),
        "wind_speed_kmh": round(wind, 2),
        "aqi_value": aqi_value,
        "severity": severity,
        "recorded_at": datetime.datetime.utcnow().isoformat()
    }
    return reading

def insert_into_snowflake(readings):
    if not readings:
        return
    conn = None
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        for r in readings:
            cursor.execute("""
                INSERT INTO raw.iot_readings 
                (sensor_id, city, zone_type, pm25, pm10, co2_ppm, temperature_c, humidity_pct, wind_speed_kmh, aqi_value, severity, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (r["sensor_id"], r["city"], r["zone_type"], r["pm25"], r["pm10"],
                  r["co2_ppm"], r["temperature_c"], r["humidity_pct"], r["wind_speed_kmh"],
                  r["aqi_value"], r["severity"], r["recorded_at"]))
        conn.commit()
        print(f"✅ Inserted {len(readings)} IoT readings to Snowflake.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if conn:
            conn.close()

def save_to_csv(readings):
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=readings[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(readings)

def producer():
    while True:
        readings = [generate_reading(s) for s in SENSORS]
        for r in readings:
            if r["severity"] in ["UNHEALTHY", "HAZARDOUS"]:
                print(f"🔴 ALERT: {r['sensor_id']} in {r['city']} - {r['severity']} (AQI: {r['aqi_value']})")
        q.put(readings)
        save_to_csv(readings)
        time.sleep(10)

def consumer():
    while True:
        readings = q.get()
        if readings is None:
            break
        insert_into_snowflake(readings)
        q.task_done()

if __name__ == "__main__":
    print("🚀 Starting IoT Simulator... (Press Ctrl+C to stop)")
    prod_thread = threading.Thread(target=producer, daemon=True)
    prod_thread.start()
    cons_thread = threading.Thread(target=consumer, daemon=True)
    cons_thread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Simulator stopped by user.")
