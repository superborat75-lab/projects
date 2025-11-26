# config.py — central configuration for mapFleet + ERP

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env next to this file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# -----------------------------
# Google Maps Configuration
# -----------------------------
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# 1 = use real Google Maps API, 0 = use mock (for development)
USE_REAL_API = bool(int(os.getenv("USE_REAL_API", "1")))
FORCE_REFRESH = bool(int(os.getenv("FORCE_REFRESH", "0")))
MAX_API_REQUESTS_PER_DAY = int(os.getenv("MAX_API_REQUESTS_PER_DAY", "950"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Caching directory
CACHE_DIR = os.getenv(
    "CACHE_DIR",
    str(BASE_DIR / "data" / "cache")
)

# Optimization options
OPTIMIZATION_CONFIG = {
    "vehicles": int(os.getenv("VEHICLES", "1")),
    "time_limit_seconds": int(os.getenv("TIME_LIMIT_SECONDS", "15")),
}

# -----------------------------
# ERP API Configuration
# -----------------------------
ERP_BASE_URL = os.getenv("ERP_BASE_URL", "").rstrip("/")
ERP_TOKEN = os.getenv("ERP_TOKEN", "")

if not ERP_BASE_URL:
    print("⚠️ WARNING: ERP_BASE_URL not set in .env — ERP features disabled.")

if not ERP_TOKEN:
    print("⚠️ WARNING: ERP_TOKEN not set in .env — ERP requests will fail.")
