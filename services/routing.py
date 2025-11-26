from math import radians, sin, cos, sqrt, atan2
from typing import Dict, List, Tuple

import googlemaps


# ---------------------------
# Utilities
# ---------------------------

def haversine(coord1, coord2) -> float:
    """Calculate distance between two lat/lon coords in km."""
    R = 6371.0
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    dlon = radians(lon2 - lon1)
    dlat = radians(lat2 - lat1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


# ---------------------------
# Phase 1 + Phase 2: preliminary assignment
# ---------------------------

def dynamic_no_crossing_routes(
    depots_coords: List[Tuple[float, float]],
    deliveries_coords: Dict[str, Tuple[float, float]],
) -> Dict[int, List[str]]:
    """
    Build preliminary routes for one or many vehicles (>=1):
    - If one depot: assign all deliveries to vehicle 0 in nearest-neighbor order.
    - If multiple depots: greedy round-robin from each depot, then light balancing by
      reassigning each stop to the vehicle whose current end is nearest.
    Returns {vehicle_index: [address,...]}
    """
    m = len(depots_coords)
    if m < 1:
        return {}

    deliveries_list = list(deliveries_coords.items())  # [(addr, (lat,lon)), ...]

    if m == 1:
        # Single vehicle: just take NN order from the depot
        current_pos = depots_coords[0]
        pool = deliveries_list.copy()
        ordered = []
        while pool:
            idx = min(range(len(pool)), key=lambda i: haversine(current_pos, pool[i][1]))
            addr, coord = pool.pop(idx)
            ordered.append(addr)
            current_pos = coord
        return {0: ordered}

    # m >= 2
    # Phase 1: greedy NN with alternating turns across m vehicles
    routes = {vid: [] for vid in range(m)}  # vehicle -> [(addr, coord), ...]
    current_pos = {vid: depots_coords[vid] for vid in range(m)}
    pool = deliveries_list.copy()
    turn = 0
    while pool:
        vid = turn % m
        nearest_idx = min(range(len(pool)), key=lambda i: haversine(current_pos[vid], pool[i][1]))
        addr, coord = pool.pop(nearest_idx)
        routes[vid].append((addr, coord))
        current_pos[vid] = coord
        turn += 1

    # Phase 2: re-check each stop and append to the closer vehicle's current end
    flattened = []
    for vid, lst in routes.items():
        flattened.extend((vid, a, c) for a, c in lst)

    new_routes = {vid: [] for vid in range(m)}
    ends = {vid: depots_coords[vid] for vid in range(m)}
    for _, addr, coord in flattened:
        # choose nearest current end among vehicles
        chosen = min(range(m), key=lambda v: haversine(ends[v], coord))
        new_routes[chosen].append((addr, coord))
        ends[chosen] = coord

    # Return address-only lists
    return {vid: [a for a, _ in new_routes[vid]] for vid in range(m)}


# ---------------------------
# Phase 3: per-vehicle reordering using Google Distance Matrix + 2-opt (no OR-Tools)
# ---------------------------

_TILE = 10  # 10x10 = 100 elements/request (fits standard plan cap)

def _distance_time_matrices_gmaps_chunked(
    gmaps_client: googlemaps.Client,
    locations: List[str]
) -> Tuple[List[List[int]], List[List[int]]]:
    """
    Build full NxN driving-time (seconds) and distance (meters) matrices
    using chunked Distance Matrix calls to respect the max elements per request (<=100).
    """
    n = len(locations)
    if n == 0:
        return [], []

    BIG = 10**9
    tm = [[0 if i == j else BIG for j in range(n)] for i in range(n)]
    dm = [[0 if i == j else BIG for j in range(n)] for i in range(n)]

    for i0 in range(0, n, _TILE):
        origins = locations[i0:i0 + _TILE]
        for j0 in range(0, n, _TILE):
            destinations = locations[j0:j0 + _TILE]

            resp = gmaps_client.distance_matrix(
                origins=origins,
                destinations=destinations,
                mode="driving",
                units="metric",
            )
            rows = resp.get("rows", [])
            for oi, row in enumerate(rows):
                elements = row.get("elements", [])
                for dj, el in enumerate(elements):
                    i = i0 + oi
                    j = j0 + dj
                    if el.get("status") == "OK":
                        tm[i][j] = int(el.get("duration", {}).get("value", BIG))
                        dm[i][j] = int(el.get("distance", {}).get("value", BIG))
                    else:
                        tm[i][j] = 0 if i == j else BIG
                        dm[i][j] = 0 if i == j else BIG
    return tm, dm


def _nearest_neighbor_order(time_matrix: List[List[int]]) -> List[int]:
    """
    Simple nearest-neighbor order for roundtrip starting at node 0.
    Returns a cycle like [0, a, b, c, 0].
    """
    n = len(time_matrix)
    if n <= 1:
        return list(range(n)) + ([0] if n == 1 else [])
    unvisited = set(range(1, n))
    order = [0]
    current = 0
    while unvisited:
        nxt = min(unvisited, key=lambda j: time_matrix[current][j])
        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    order.append(0)
    return order


def _route_cost(order: List[int], matrix: List[List[int]]) -> int:
    """Total cost along order edges, using provided matrix (time or distance)."""
    return sum(matrix[a][b] for a, b in zip(order, order[1:]))


def _two_opt(order: List[int], matrix: List[List[int]], max_passes: int = 20) -> List[int]:
    """
    2-opt improvement on a roundtrip order [0, ..., 0].
    Does not move the start/end depot (0). Improves by time-matrix by default.
    """
    best = order[:]
    best_cost = _route_cost(best, matrix)
    n = len(order)
    if n < 5:
        return best

    for _ in range(max_passes):
        improved = False
        # i from 1 to n-3, j from i+1 to n-2 (avoid indices 0 and last which are depot)
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                if j == i + 1:
                    continue  # no benefit reversing a segment of length 1
                new_order = best[:i] + best[i:j][::-1] + best[j:]
                new_cost = _route_cost(new_order, matrix)
                if new_cost < best_cost:
                    best, best_cost = new_order, new_cost
                    improved = True
        if not improved:
            break
    return best


def reorder_vehicle_with_google(
    api_key: str,
    depot_address: str,
    stop_addresses: List[str],
) -> Tuple[List[str], int, int]:
    """
    Reorder this vehicle's stop list using Google's driving-time matrix + NN + 2-opt.
    Returns (ordered_addresses, total_distance_m, total_duration_s),
    excluding the final return-to-depot in the address list.
    """
    if not stop_addresses:
        return [], 0, 0

    gmaps_client = googlemaps.Client(key=api_key)

    # Build location list: [depot, *stops]
    locations = [depot_address] + stop_addresses
    tmat, dmat = _distance_time_matrices_gmaps_chunked(gmaps_client, locations)

    # Initial route by nearest neighbor (roundtrip)
    order = _nearest_neighbor_order(tmat)
    # Improve with 2-opt (time-based)
    order = _two_opt(order, tmat, max_passes=25)

    # Convert to address order WITHOUT the final depot repeat
    seq = []
    total_dist = 0
    total_time = 0
    for a, b in zip(order, order[1:]):
        total_dist += dmat[a][b]
        total_time += tmat[a][b]
        if b == 0:
            break  # returned to depot; stop adding addresses
        seq.append(locations[b])

    return seq, total_dist, total_time
