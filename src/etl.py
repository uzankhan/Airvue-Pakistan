import os
import sys
import time
import polars as pl
import pandas as pd
import logging
import datetime
import snowflake.connector

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils import setup_logging, get_snowflake_connection, calculate_aqi, get_health_risk

logger = setup_logging()

# ------------- TRANSFORM IoT DATA -------------
def transform_iot(df):
    """Clean and transform IoT data."""
    print("🔄 Transforming IoT data...")
    
    # Drop nulls in critical columns
    df = df.filter(pl.col("pm25").is_not_null() & pl.col("aqi_value").is_not_null())
    
    # Validate ranges
    df = df.filter(
        (pl.col("pm25") >= 0) & (pl.col("pm25") <= 500) &
        (pl.col("co2_ppm") >= 400) & (pl.col("co2_ppm") <= 2000) &
        (pl.col("humidity_pct") >= 0) & (pl.col("humidity_pct") <= 100)
    )
    
    # Deduplicate on (sensor_id, recorded_at)
    df = df.unique(subset=["sensor_id", "recorded_at"], keep="first")
    
    # Apply AQI Category and Health Risk using vectorized mapping (apply)
    # Note: Since map_elements with Python functions can be slow but fine for small data.
    # We'll use map_elements safely.
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
    
    # Add source and processed_at
    df = df.with_columns([
        pl.lit("iot_simulator").alias("source"),
        pl.lit(datetime.datetime.utcnow().isoformat()).alias("processed_at"),
        pl.lit(None).alias("latitude"),  # IoT doesn't have lat/lng, but Silver expects it
        pl.lit(None).alias("longitude")
    ])
    
    # Select columns matching Silver table exactly
    df = df.select([
        "source", "city", "sensor_id", "pm25", "pm10", "co2_ppm", "aqi_value", 
        "aqi_category", "health_risk", "latitude", "longitude", "recorded_at", "processed_at"
    ])
    
    print(f"✅ IoT transformation complete: {df.height} rows")
    return df

# ------------- TRANSFORM OpenAQ DATA -------------
def transform_openaq(df):
    """Clean and transform OpenAQ data."""
    print("🔄 Transforming OpenAQ data...")
    
    if df.is_empty():
        print("⚠️ OpenAQ data is empty, skipping.")
        return df
    
    # Filter to only pm25/pm10
    df = df.filter(pl.col("pollutant_type").is_in(["pm25", "pm10"]))
    
    # Convert recorded_at to UTC (assuming already)
    # Drop negative values
    df = df.filter(pl.col("pollutant_value") > 0)
    
    if df.is_empty():
        return df
    
    # Pivot to get pm25 and pm10 in same row per (location_id, recorded_at)
    # First, create a unique id for each timestamp + location
    pivot_df = df.pivot(
        index=["location_id", "station_name", "city", "latitude", "longitude", "recorded_at"],
        columns="pollutant_type",
        values="pollutant_value"
    )
    
    # Rename columns (pivot creates them automatically)
    # Ensure pm25 and pm10 exist, if not fill with null
    if "pm25" not in pivot_df.columns:
        pivot_df = pivot_df.with_columns(pl.lit(None).alias("pm25"))
    if "pm10" not in pivot_df.columns:
        pivot_df = pivot_df.with_columns(pl.lit(None).alias("pm10"))
    
    # Add co2 (OpenAQ usually doesn't have it, set null)
    pivot_df = pivot_df.with_columns(pl.lit(None).alias("co2_ppm"))
    
    # Calculate AQI and Health Risk using pm25
    pivot_df = pivot_df.with_columns([
        pl.struct(["pm25"]).map_elements(
            lambda x: calculate_aqi(x["pm25"])[0] if x["pm25"] is not None else None,
            return_dtype=pl.Float64
        ).alias("aqi_value"),
        pl.struct(["pm25"]).map_elements(
            lambda x: calculate_aqi(x["pm25"])[1] if x["pm25"] is not None else None,
            return_dtype=pl.String
        ).alias("aqi_category"),
        pl.struct(["pm25"]).map_elements(
            lambda x: get_health_risk(calculate_aqi(x["pm25"])[1]) if x["pm25"] is not None else None,
            return_dtype=pl.String
        ).alias("health_risk")
    ])
    
    # Add source, sensor_id null, processed_at
    pivot_df = pivot_df.with_columns([
        pl.lit("openaq_v3").alias("source"),
        pl.lit(None).alias("sensor_id"),
        pl.lit(datetime.datetime.utcnow().isoformat()).alias("processed_at")
    ])
    
    # Select columns matching Silver
    pivot_df = pivot_df.select([
        "source", "city", "sensor_id", "pm25", "pm10", "co2_ppm", "aqi_value", 
        "aqi_category", "health_risk", "latitude", "longitude", "recorded_at", "processed_at"
    ])
    
    print(f"✅ OpenAQ transformation complete: {pivot_df.height} rows")
    return pivot_df

# ------------- LOAD TO SILVER -------------
def load_to_silver(df, table_name="CLEAN.AQI_CLEAN"):
    """Load transformed DataFrame to Snowflake Silver table."""
    if df.is_empty():
        print("⚠️ No data to load to Silver.")
        return
    
    conn = None
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        
        # Convert Polars to list of tuples for batch insert
        records = df.to_pandas().to_dict('records')
        
        for rec in records:
            # Handle None values properly for SQL
            latitude = rec.get("latitude")
            longitude = rec.get("longitude")
            
            cursor.execute(f"""
                INSERT INTO {table_name} 
                (source, city, sensor_id, pm25, pm10, co2_ppm, aqi_value, aqi_category, health_risk, latitude, longitude, recorded_at, processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (rec["source"], rec["city"], rec["sensor_id"], rec["pm25"], rec["pm10"],
                  rec["co2_ppm"], rec["aqi_value"], rec["aqi_category"], rec["health_risk"],
                  latitude, longitude, rec["recorded_at"], rec["processed_at"]))
        
        conn.commit()
        print(f"✅ Loaded {len(records)} rows to Silver table ({table_name})")
        logger.info(f"Loaded {len(records)} rows to Silver table.")
    except Exception as e:
        print(f"❌ Load to Silver failed: {e}")
        logger.error(f"Load to Silver failed: {e}")
    finally:
        if conn:
            conn.close()

# ------------- MAIN ETL -------------
def run_etl():
    print("\n" + "="*50)
    print("🚀 STARTING ETL PIPELINE")
    print("="*50 + "\n")
    
    # 1. Process IoT Data (from CSV)
    iot_path = "data/iot_readings.csv"
    if os.path.exists(iot_path):
        print(f"📂 Reading IoT CSV: {iot_path}")
        iot_df = pl.read_csv(iot_path)
        print(f"   Read {iot_df.height} rows from IoT CSV.")
        if not iot_df.is_empty():
            iot_clean = transform_iot(iot_df)
            load_to_silver(iot_clean)
        else:
            print("⚠️ IoT CSV is empty.")
    else:
        print("⚠️ IoT CSV not found. Run simulator first to generate data.")
    
    # 2. Process OpenAQ Data (from Snowflake RAW)
    print("\n📂 Reading OpenAQ from Snowflake RAW...")
    conn = None
    try:
        conn = get_snowflake_connection()
        # Fetch data from RAW.OPENAQ_RAW
        query = "SELECT * FROM RAW.OPENAQ_RAW"
        # Use pandas to fetch, then convert to Polars
        df_pandas = pd.read_sql(query, conn)
        if not df_pandas.empty:
            openaq_df = pl.from_pandas(df_pandas)
            print(f"   Read {openaq_df.height} rows from OpenAQ RAW.")
            openaq_clean = transform_openaq(openaq_df)
            load_to_silver(openaq_clean)
        else:
            print("⚠️ No OpenAQ data found in RAW table.")
    except Exception as e:
        print(f"❌ Failed to read OpenAQ from Snowflake: {e}")
        logger.error(f"Failed to read OpenAQ: {e}")
    finally:
        if conn:
            conn.close()
    
    print("\n" + "="*50)
    print("✅ ETL PIPELINE COMPLETE!")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_etl()