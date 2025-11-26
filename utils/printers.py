from typing import Dict, List
from urllib.parse import quote


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def format_distance(meters: int) -> str:
    if meters >= 1000:
        return f"{meters/1000:.1f} km"
    return f"{meters} m"


def build_google_maps_link(stops: List[str]) -> str:
    if not stops:
        return ""
    origin = quote(stops[0])
    destination = quote(stops[-1])
    waypoints = "|".join(quote(s) for s in stops[1:-1]) if len(stops) > 2 else ""
    url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&travelmode=driving"
    if waypoints:
        url += f"&waypoints={waypoints}"
    return url


def print_routes(routes: List[Dict]):
    for route in routes:
        print(f"\nVehicle #{route['vehicle_id']}")
        print("=" * 30)
        print(f"Stops: {len(route['stops'])}")
        for i, stop in enumerate(route["stops"], 1):
            print(f"{i:02d}. {stop}")
        print(f"Distance: {format_distance(route['distance'])}")
        print(f"Time:     {format_duration(route['time'])}")


def print_summary(routes: List[Dict]):
    total_distance = sum(r.get("distance", 0) for r in routes)
    total_time = sum(r.get("time", 0) for r in routes)
    print("\nSummary")
    print("=" * 30)
    print(f"Vehicles:       {len(routes)}")
    print(f"Total distance: {format_distance(total_distance)}")
    print(f"Total time:     {format_duration(total_time)}")
