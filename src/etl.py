import os
import sys
import polars as pl
import pandas as pd
import logging
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils import setup_logging, get_snowflake_connection, calculate_aqi, get_health_risk

logger = setup_logging()

def transform_iot(df):
    print("🔄 Transforming IoT data...")
    df = df.filter(pl.col("pm25").is_not_null() & pl.col("aqi_value").is_not_null())
    df = df.filter(
        (pl.col("pm25") >= 0) & (pl.col("pm25") <= 500) &
        (pl.col("co2_ppm") >= 400) & (pl.col("co2_ppm") <= 2000) &
        (pl.col("humidity_pct") >= 0) & (pl.col("humidity_pct") <= 100)
    )
    df = df.unique(subset=["sensor_id", "recorded_at"], keep="first")
    
    df = df.with_columns([
        pl.struct(["pm25"]).map_elements(
            lambda x: calculate_aqi(x["pm25"])[1] if x["pm25"] is not None else None,
            return_dtype=pl.String
        ).alias("aqi_category"),
        pl.struct(["pm25"]).map_elements(
            lambda x: get_health_risk(calculate_aqi(x["pm25"])[1]) if x["pm25"] is not None else None,
            return_dtype=pl.String
        ).alias("health_risk")
    ])
    
    df = df.with_columns([
        pl.lit("iot_simulator").alias("source"),
        pl.lit(datetime.datetime.utcnow().isoformat()).alias("processed_at"),
        pl.lit(None).alias("latitude"),
        pl.lit(None).alias("longitude")
    ])
    
    df = df.select([
        "source", "city", "sensor_id", "pm25", "pm10", "co2_ppm", "aqi_value", 
        "aqi_category", "health_risk", "latitude", "longitude", "recorded_at", "processed_at"
    ])
    
    print(f"✅ IoT transformation complete: {df.height} rows")
    return df

def load_to_silver(df, table_name="clean.aqi_clean"):
    if df.is_empty():
        print("⚠️ No data to load to Silver.")
        return
    
    conn = None
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        records = df.to_pandas().to_dict('records')
        
        for rec in records:
            cursor.execute(f"""
                INSERT INTO {table_name} 
                (source, city, sensor_id, pm25, pm10, co2_ppm, aqi_value, aqi_category, health_risk, latitude, longitude, recorded_at, processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (rec["source"], rec["city"], rec["sensor_id"], rec["pm25"], rec["pm10"],
                  rec["co2_ppm"], rec["aqi_value"], rec["aqi_category"], rec["health_risk"],
                  rec.get("latitude"), rec.get("longitude"), rec["recorded_at"], rec["processed_at"]))
        
        conn.commit()
        print(f"✅ Loaded {len(records)} rows to Silver table ({table_name})")
        logger.info(f"Loaded {len(records)} rows to Silver table.")
    except Exception as e:
        print(f"❌ Load to Silver failed: {e}")
        logger.error(f"Load to Silver failed: {e}")
    finally:
        if conn:
            conn.close()

def update_gold():
    print("\n📊 Updating Gold table (analytics.city_daily)...")
    conn = None
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        
        # First delete old data
        cursor.execute("DELETE FROM analytics.city_daily;")
        
        # Then insert fresh data
        cursor.execute("""
            INSERT INTO analytics.city_daily 
                (city, report_date, avg_aqi, max_aqi, min_aqi, avg_pm25, avg_co2, dominant_risk, reading_count, livability_score, health_advisory)
            WITH agg AS (
                SELECT 
                    city,
                    DATE(recorded_at) as report_date,
                    AVG(aqi_value) as avg_aqi,
                    MAX(aqi_value) as max_aqi,
                    MIN(aqi_value) as min_aqi,
                    AVG(pm25) as avg_pm25,
                    AVG(co2_ppm) as avg_co2,
                    COUNT(*) as reading_count,
                    ROUND(GREATEST(0, 100 - (AVG(aqi_value) / 5))::numeric, 2) as livability_score,
                    CASE 
                        WHEN AVG(aqi_value) <= 50 THEN '🌿 Safe & Clean'
                        WHEN AVG(aqi_value) <= 100 THEN '😷 Moderate'
                        WHEN AVG(aqi_value) <= 200 THEN '⚠️ Unhealthy'
                        WHEN AVG(aqi_value) <= 300 THEN '🚨 Very Unhealthy'
                        ELSE '☣️ HAZARDOUS'
                    END as health_advisory
                FROM clean.aqi_clean
                GROUP BY city, DATE(recorded_at)
            ),
            dominant AS (
                SELECT DISTINCT ON (city, report_date)
                    city,
                    DATE(recorded_at) as report_date,
                    health_risk,
                    COUNT(*) as cnt
                FROM clean.aqi_clean
                GROUP BY city, DATE(recorded_at), health_risk
                ORDER BY city, DATE(recorded_at), cnt DESC
            )
            SELECT 
                a.city,
                a.report_date,
                a.avg_aqi,
                a.max_aqi,
                a.min_aqi,
                a.avg_pm25,
                a.avg_co2,
                d.health_risk as dominant_risk,
                a.reading_count,
                a.livability_score,
                a.health_advisory
            FROM agg a
            LEFT JOIN dominant d ON a.city = d.city AND a.report_date = d.report_date;
        """)
        conn.commit()
        print("✅ Gold table updated successfully!")
        logger.info("Gold table updated successfully!")
    except Exception as e:
        print(f"❌ Gold update failed: {e}")
        logger.error(f"Gold update failed: {e}")
    finally:
        if conn:
            conn.close()

def run_etl():
    print("\n" + "="*50)
    print("🚀 STARTING ETL PIPELINE")
    print("="*50 + "\n")
    
    iot_path = "data/iot_readings.csv"
    if os.path.exists(iot_path):
        print(f"📂 Reading IoT CSV: {iot_path}")
        iot_df = pl.read_csv(iot_path)
        print(f"   Read {iot_df.height} rows from IoT CSV.")
        if not iot_df.is_empty():
            iot_clean = transform_iot(iot_df)
            load_to_silver(iot_clean, "clean.aqi_clean")
        else:
            print("⚠️ IoT CSV is empty.")
    else:
        print("⚠️ IoT CSV not found. Run simulator first.")
    
    update_gold()
    
    print("\n" + "="*50)
    print("✅ ETL PIPELINE COMPLETE!")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_etl()
