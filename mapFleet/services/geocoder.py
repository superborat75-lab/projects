import json
import os
import time
from pathlib import Path
from typing import Dict, Tuple

import googlemaps
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "cache" / "coords.json"


class Geocoder:
    """
    Handles geocoding operations using Google Maps API, with local caching of results.

    This class provides functionality to geocode single or multiple addresses by converting
    them into latitude and longitude coordinates. It uses Google Maps API for geocoding and
    implements a local caching mechanism to avoid redundant API calls and reduce latency.

    :ivar client: Google Maps API client to perform geocoding operations.
    :type client: googlemaps.Client
    :ivar cache: Local cache storing previously geocoded results to reduce API calls. The
        cache is stored as a dictionary with the address as the key and coordinates as the value.
    :type cache: Dict
    """

    def __init__(self, api_key: str = GOOGLE_MAPS_API_KEY):
        if not api_key:
            raise ValueError(
                "Google Maps API key is missing. Please set GOOGLE_MAPS_API_KEY in .env"
            )
        self.client = googlemaps.Client(key=api_key)
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_cache(self):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def geocode_address(self, address: str) -> Tuple[float, float]:
        """
        Returns (lat, lon) for a given address.
        Checks local cache before calling Google API.
        """
        if address in self.cache:
            return tuple(self.cache[address])

        print(f"Geocoding: {address}")
        result = self.client.geocode(address)
        if not result:
            raise ValueError(f"Could not geocode address: {address}")

        location = result[0]["geometry"]["location"]
        lat, lon = location["lat"], location["lng"]

        self.cache[address] = [lat, lon]
        self._save_cache()

        # Respect rate limits
        time.sleep(0.2)
        return lat, lon

    def bulk_geocode(self, addresses):
        return {addr: self.geocode_address(addr) for addr in addresses}
