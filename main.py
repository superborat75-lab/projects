import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

import googlemaps

from config import GOOGLE_MAPS_API_KEY
from services.geocoder import Geocoder
from services.routing import dynamic_no_crossing_routes, reorder_vehicle_with_google
from utils.printers import format_distance, format_duration  # reuse nice formatters

# Paths
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"
DEPOTS_FILE = INPUT_DIR / "depots.csv"
DELIVERIES_FILE = INPUT_DIR / "deliveries.csv"


# ---------------------------
# Helpers
# ---------------------------

def load_addresses(file_path: Path):
    """
    Reads a CSV file where each row is: name,address
    Returns dict {name: address}
    """
    if not file_path.exists():
        print(f"❌ ERROR: File not found -> {file_path}")
        sys.exit(1)

    addresses = {}
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name") or row.get("Name") or f"Stop_{len(addresses)+1}"
            addr = row.get("address") or row.get("Address")
            if addr:
                addresses[name] = addr

    if not addresses:
        print(
            f"⚠️ ERROR: No addresses found in {file_path.name} — please add at least 1 row."
        )
        sys.exit(1)

    return addresses


def build_expected_route_files(num_vehicles: int, output_dir: Path) -> list[Path]:
    """
    For N vehicles, expect files:
      vehicle_1_YYYY-mm-dd.csv, vehicle_2_YYYY-mm-dd.csv, ...
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    files = []
    for vid in range(1, num_vehicles + 1):
        label = f"vehicle_{vid}"
        filename = f"{label}_{today_str}.csv"
        files.append(output_dir / filename)
    return files


def check_cached_routes(num_vehicles: int, output_dir: Path) -> list[Path] | None:
    """
    If all expected CSVs for today exist → return them, else None.
    """
    expected_files = build_expected_route_files(num_vehicles, output_dir)
    missing = [p for p in expected_files if not p.exists()]

    if missing:
        return None

    return expected_files


def cleanup_output_dir(output_dir: Path):
    """
    Чистим ВСИЧКО в output/ (CSV, TXT, PNG, PDF и т.н.)
    Ползва се само при FULL recompute (cached=False).
    """
    if not output_dir.exists():
        return

    print(f"🧹 Cleaning output dir: {output_dir}")
    for child in output_dir.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def save_routes_to_csv(routes: dict, api_key: str, output_dir: Path):
    """
    Save each vehicle's route (including depot as first row) to a date-based CSV with
    per-leg distance/time and cumulative totals.

    routes: {vehicle_label: [depot, stop1, stop2, ...]}

    File naming:
        vehicle_1_YYYY-mm-dd.csv
        vehicle_2_YYYY-mm-dd.csv
        ...
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    gmaps_client = googlemaps.Client(key=api_key)

    created_files = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for vehicle_label, stops in routes.items():
        filename = f"{vehicle_label}_{today_str}.csv"
        filepath = output_dir / filename

        cumulative_km = 0.0
        cumulative_min = 0.0
        rows = [
            (
                "Stop",
                "Address",
                "Distance_km",
                "TravelTime_min",
                "Cumulative_km",
                "Cumulative_min",
            )
        ]

        for i, stop in enumerate(stops, start=1):
            if i == 1:
                dist_km = 0.0
                time_min = 0.0
            else:
                # Distance/time from previous stop to current stop
                try:
                    resp = gmaps_client.distance_matrix(
                        origins=[stops[i - 2]],
                        destinations=[stop],
                        mode="driving",
                        units="metric",
                    )
                    element = resp.get("rows", [{}])[0].get("elements", [{}])[0]
                    ok = element.get("status") == "OK"
                    dist_km = (
                        (element.get("distance", {}).get("value", 0) / 1000.0)
                        if ok
                        else 0.0
                    )
                    time_min = (
                        (element.get("duration", {}).get("value", 0) / 60.0)
                        if ok
                        else 0.0
                    )
                except Exception:
                    # Fail soft on per-leg errors
                    dist_km = 0.0
                    time_min = 0.0

            cumulative_km += dist_km
            cumulative_min += time_min
            rows.append(
                (
                    i,
                    stop,
                    round(dist_km, 2),
                    round(time_min, 1),
                    round(cumulative_km, 2),
                    round(cumulative_min, 1),
                )
            )

        # Add the total row
        rows.append(
            ("Total", "", "", "", round(cumulative_km, 2), round(cumulative_min, 1))
        )

        with open(filepath, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        created_files.append(filepath)

    print("\n💾 CSV files saved:")
    for p in created_files:
        print(f"   • {p}")

    return created_files


# ---------------------------
# Core pipeline
# ---------------------------

def generate_routes(cached: bool = True):
    """
    1) Чете depots.csv и deliveries.csv
    2) Ако cached=True и всички vehicle_X_YYYY-mm-dd.csv ги има:
        -> ползва тях, не вика Google API
    3) Ако cached=False:
        -> чисти output/
        -> геокодира, оптимизира, пише нови CSV
    """
    print("📍 Loading depots and deliveries...")
    depots_dict = load_addresses(DEPOTS_FILE)       # {name: address}
    deliveries_dict = load_addresses(DELIVERIES_FILE)  # {name: address}

    if len(depots_dict) < 1:
        print(f"❌ ERROR: Provide at least one depot in {DEPOTS_FILE}.")
        sys.exit(1)

    if not GOOGLE_MAPS_API_KEY:
        print(
            "❌ ERROR: GOOGLE_MAPS_API_KEY is missing. Create a .env file with GOOGLE_MAPS_API_KEY=YOUR_KEY \n"
            "   or export it in your environment before running."
        )
        sys.exit(1)

    num_vehicles = len(depots_dict)

    # ---------- CACHE CHECK ----------
    if cached:
        cached_files = check_cached_routes(num_vehicles, OUTPUT_DIR)
        if cached_files:
            print("✅ Using cached routes for today (no new Google API calls).")
            print("   Cached CSV files:")
            for p in cached_files:
                print(f"   • {p}")
            return cached_files

    # ---------- FULL RECOMPUTE ----------
    # почваме на чисто – махаме стария боклук
    cleanup_output_dir(OUTPUT_DIR)

    geocoder = Geocoder()  # uses the same key from .env for geocoding (and cache)

    print("📍 Geocoding depots...")
    depots_coords_map = geocoder.bulk_geocode(depots_dict.values())  # {addr: (lat,lon)}
    depots_coords = list(depots_coords_map.values())  # [(lat,lon), (lat,lon)]

    print("📍 Geocoding deliveries...")
    deliveries_coords = geocoder.bulk_geocode(
        deliveries_dict.values()
    )  # {addr: (lat,lon)}

    print("🚚 Building preliminary routes (balanced, nearest-neighbor)...")
    prelim_routes = dynamic_no_crossing_routes(depots_coords, deliveries_coords)
    # prelim_routes: {0: [addr,...], 1: [addr,...]}

    print(
        "🧭 Reordering each vehicle by Google driving times (TSP roundtrip) and computing totals..."
    )
    depot_names = list(depots_dict.keys())
    depot_addrs = list(depots_dict.values())

    final_routes = {}
    totals = {}
    for vid in sorted(prelim_routes.keys()):
        stops = prelim_routes[vid]
        depot_addr = depot_addrs[vid]
        ordered, total_m, total_s = reorder_vehicle_with_google(
            api_key=GOOGLE_MAPS_API_KEY,
            depot_address=depot_addr,
            stop_addresses=stops,
        )
        final_routes[vid] = ordered
        totals[vid] = (total_m, total_s)

    print("\n✅ Optimized Routes (after per-vehicle TSP reorder):")
    for vid, stop_list in final_routes.items():
        vehicle_name = depot_names[vid]
        print(f"\nVehicle {vid+1} ({vehicle_name}):")
        for idx, addr in enumerate(stop_list, start=1):
            print(f"  {idx}. {addr}")
        dist_m, dur_s = totals[vid]
        print(f"  ─ Totals: {format_distance(dist_m)} • {format_duration(dur_s)}")

    # ------- Save CSVs -------
    ordered_routes = {}
    for vid, stops in final_routes.items():
        label = f"vehicle_{vid+1}"
        ordered_routes[label] = [depot_addrs[vid]] + stops

    created_files = save_routes_to_csv(ordered_routes, GOOGLE_MAPS_API_KEY, OUTPUT_DIR)
    return created_files


def main():
    """
    python main.py          -> cached=True (ползва стари, ако ги има)
    python main.py --no-cache -> форсира нови маршрути, чисти output/
    """
    cached = True
    if len(sys.argv) > 1 and sys.argv[1] == "--no-cache":
        cached = False

    files = generate_routes(cached=cached)

    print("\n✅ Done. Route CSV files:")
    for p in files:
        print(f"   • {p}")


if __name__ == "__main__":
    main()
