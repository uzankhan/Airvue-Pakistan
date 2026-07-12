import os
import time
import logging
import snowflake.connector
from dotenv import load_dotenv
import datetime

load_dotenv()

def setup_logging():
    logging.basicConfig(
        filename='logs/project.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def get_snowflake_connection(retries=3, delay=5):
    """Returns Snowflake connection with robust env var handling."""
    
    # Read env vars with fallback
    account = os.getenv('SNOWFLAKE_ACCOUNT')
    user = os.getenv('SNOWFLAKE_USER')
    password = os.getenv('SNOWFLAKE_PASSWORD')
    warehouse = os.getenv('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH')
    database = os.getenv('SNOWFLAKE_DATABASE', 'SMART_CITY_AQI')
    schema = os.getenv('SNOWFLAKE_SCHEMA_RAW', 'RAW')

    # Validate critical variables
    if not account:
        raise ValueError("❌ SNOWFLAKE_ACCOUNT is missing in .env file. Please set it (e.g., veazqnc-px62337).")
    if not user:
        raise ValueError("❌ SNOWFLAKE_USER is missing in .env file.")
    if not password:
        raise ValueError("❌ SNOWFLAKE_PASSWORD is missing in .env file.")

    for attempt in range(retries):
        try:
            conn = snowflake.connector.connect(
                user=user,
                password=password,
                account=account,
                warehouse=warehouse,
                database=database,
                schema=schema
            )
            return conn
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            else:
                raise e

# ... (baqi functions calculate_aqi, get_health_risk same rahenge)