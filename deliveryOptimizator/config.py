# Configuration for deliveryOptimizator
# NOTE: Do not hardcode real keys here. Use environment variables or an.env file.

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Loads variables from an.env file if present

# API & runtime
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
USE_REAL_API = bool(
    int(os.getenv("USE_REAL_API", "1"))
)  # 1=use Google Apps, 0=offline mock
FORCE_REFRESH = bool(int(os.getenv("FORCE_REFRESH", "0")))  # ignore cache if 1
MAX_API_REQUESTS_PER_DAY = int(os.getenv("MAX_API_REQUESTS_PER_DAY", "950"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Caching
CACHE_DIR = os.getenv("CACHE_DIR", str(Path(__file__).parent / "data" / "cache"))

# Optimization
OPTIMIZATION_CONFIG = {
    "vehicles": int(os.getenv("VEHICLES", "1")),
    "time_limit_seconds": int(os.getenv("TIME_LIMIT_SECONDS", "15")),
}
