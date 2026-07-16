import sys
import os
# Force add current directory to path
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import random
import math
import datetime
import threading
import queue
import csv
import logging

from src.utils import setup_logging, get_snowflake_connection, calculate_aqi, get_health_risk
