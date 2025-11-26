"""maps.py - Google Maps wrapper with simple caching and chunked Distance Matrix calls.
If USE_REAL_API=0 or no key is set, this module raises MapsAPIError when distance matrix is requested.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import googlemaps
import numpy as np
from ratelimit import limits, sleep_and_retry

from config import (
    CACHE_DIR,
    FORCE_REFRESH,
    GOOGLE_MAPS_API_KEY,
    LOG_LEVEL,
    MAX_API_REQUESTS_PER_DAY,
    USE_REAL_API,
)
from utils.exceptions import MapsAPIError

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

PER_MINUTE = 60

# Google standard quota: max elements (origins * destinations) per request = 100
# We'll be conservative and use 10x10 tiles.
TILE_SIZE = 10  # 10x10 = 100 elements/request (fits standard plan hard cap)


class MapsService:
    """
    Handles interaction with the Google Maps API to compute distance and duration matrices
    for specified deliveries and depots.

    This service class is responsible for managing API requests to compute the distance
    and duration between given locations, caching the results to avoid redundant
    API calls, and efficiently handling large datasets by processing the requests
    in tiles. It also includes methods to track and manage the remaining daily API
    requests allowed.

    :ivar cache_dir: The directory where cached responses are stored.
    :type cache_dir: Path
    :ivar request_count: The current count of API requests made for the day.
    :type request_count: int
    :ivar client: The Google Maps API client instance, initialized based on API
        configuration. It will only be set if real API access is enabled.
    :type client: Optional[googlemaps.Client]
    """

    def __init__(self) -> None:
        self.cache_dir = Path(CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_count = 0
        if USE_REAL_API and not GOOGLE_MAPS_API_KEY:
            raise MapsAPIError("USE_REAL_API=1 but GOOGLE_MAPS_API_KEY is empty.")
        self.client = (
            googlemaps.Client(key=GOOGLE_MAPS_API_KEY) if USE_REAL_API else None
        )

    def _key(self, deliveries: List[str], depots: List[str]) -> str:
        data = json.dumps(
            {"deliveries": deliveries, "depots": depots},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _load_cache(self, key: str) -> Optional[Dict[str, Any]]:
        p = self._cache_path(key)
        if p.exists() and not FORCE_REFRESH:
            try:
                with p.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save_cache(self, key: str, payload: dict) -> None:
        p = self._cache_path(key)
        tmp = p.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(p)

    @sleep_and_retry
    @limits(calls=MAX_API_REQUESTS_PER_DAY, period=24 * PER_MINUTE * 60)
    def _distance_matrix_tile(
        self, origins: List[str], destinations: List[str]
    ) -> Dict[str, Any]:
        """Call Distance Matrix for a single tile (<=100 elements)."""
        if not self.client:
            raise MapsAPIError(
                "Distance Matrix requested in offline mode (USE_REAL_API=0)."
            )
        self.request_count += 1
        return self.client.distance_matrix(
            origins=origins,
            destinations=destinations,
            mode="driving",
            units="metric",
            # You can add departure_time & traffic_model if you want traffic-aware duration:
            # departure_time=int(time.time()) + 900,  # leave ~15 min from now
            # traffic_model="best_guess",
        )

    def _build_full_matrix(self, locations: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Builds the full distance and duration matrices for the given list of locations
        by querying the API and assembling the results. The function processes the
        locations in tiles of fixed size to optimize API calls, ensuring efficient
        computation even for large datasets. Each API response is parsed to extract
        distance and duration information between pairs of locations, while handling
        invalid API responses by penalizing them with a high value.

        :param locations: List of location identifiers for which the distance and
            duration matrices will be computed.
        :type locations: List[str]
        :return: A tuple containing two matrices:
            - The distance matrix (numpy.ndarray) where an element (i, j) represents the
              distance between the ith and jth locations.
            - The duration matrix (numpy.ndarray) where an element (i, j) represents the
              duration between the ith and jth locations.
        :rtype: Tuple[np.ndarray, np.ndarray]
        """
        n = len(locations)
        dm = np.zeros((n, n), dtype=int)
        tm = np.zeros((n, n), dtype=int)

        if n == 0:
            return dm, tm

        # Iterate over 10x10 tiles
        for i0 in range(0, n, TILE_SIZE):
            i1 = min(i0 + TILE_SIZE, n)
            origins = locations[i0:i1]
            for j0 in range(0, n, TILE_SIZE):
                j1 = min(j0 + TILE_SIZE, n)
                destinations = locations[j0:j1]

                # Call API for the tile
                resp = self._distance_matrix_tile(origins, destinations)
                rows = resp.get("rows", [])
                for oi, row in enumerate(rows):
                    elements = row.get("elements", [])
                    for dj, el in enumerate(elements):
                        i = i0 + oi
                        j = j0 + dj
                        if el.get("status") == "OK":
                            dm[i, j] = el.get("distance", {}).get("value", 0)
                            tm[i, j] = el.get("duration", {}).get("value", 0)
                        else:
                            # Penalize impossible legs (but keep diagonal 0)
                            dm[i, j] = 0 if i == j else 10**9
                            tm[i, j] = 0 if i == j else 10**9

        return dm, tm

    def get_distance_time_matrices(
        self, deliveries: List[str], depots: List[str]
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Return (distance_matrix_m, time_matrix_s, all_locations_order) including depot(s) first.
        Locations order: [depots..., deliveries...]
        """
        key = self._key(deliveries, depots)
        cached = self._load_cache(key)
        if cached:
            dm = np.array(cached["distance_matrix"], dtype=int)
            tm = np.array(cached["time_matrix"], dtype=int)
            locations = cached["locations"]
            return dm, tm, locations

        locations = list(depots) + list(deliveries)

        # Build matrices in chunks to respect the MAX_ELEMENTS limit
        dm, tm = self._build_full_matrix(locations)

        payload = {
            "distance_matrix": dm.tolist(),
            "time_matrix": tm.tolist(),
            "locations": locations,
        }
        self._save_cache(key, payload)
        return dm, tm, locations

    def get_remaining_daily_requests(self) -> int:
        return max(0, MAX_API_REQUESTS_PER_DAY - self.request_count)
