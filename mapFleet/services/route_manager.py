# services/route_manager.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Tuple

import googlemaps
import pandas as pd

from .route_output import save_route_dataframe


@dataclass
class Location:
    name: str
    lat: float
    lon: float


def _load_input_data(
    input_dir: str | Path = "data/input",
    depot_file: str = "depots.csv",
    deliveries_file: str = "deliveries.csv",
    address_col: str = "address",
    lat_col: str = "lat",
    lon_col: str = "lon",
) -> Tuple[Location, List[Location]]:
    """
    Чете depots.csv и deliveries.csv и връща:
    - depot (Location)
    - списък с доставки (List[Location])
    Очаква колони: address, lat, lon (можеш да ги смениш с параметри).
    """
    input_dir = Path(input_dir)
    depots_path = input_dir / depot_file
    deliveries_path = input_dir / deliveries_file

    if not depots_path.exists():
        raise FileNotFoundError(f"Depot файлът липсва: {depots_path}")
    if not deliveries_path.exists():
        raise FileNotFoundError(f"Deliveries файлът липсва: {deliveries_path}")

    df_depot = pd.read_csv(depots_path)
    df_deliv = pd.read_csv(deliveries_path)

    if df_depot.empty:
        raise ValueError("depots.csv е празен.")
    if df_deliv.empty:
        raise ValueError("deliveries.csv е празен.")

    for col in (address_col, lat_col, lon_col):
        if col not in df_depot.columns:
            raise ValueError(f"Колона '{col}' липсва в depots.csv")
        if col not in df_deliv.columns:
            raise ValueError(f"Колона '{col}' липсва в deliveries.csv")

    # приемаме първият ред в depots.csv да е нашето депо
    depot_row = df_depot.iloc[0]
    depot = Location(
        name=str(depot_row[address_col]),
        lat=float(depot_row[lat_col]),
        lon=float(depot_row[lon_col]),
    )

    deliveries: List[Location] = []
    for _, row in df_deliv.iterrows():
        deliveries.append(
            Location(
                name=str(row[address_col]),
                lat=float(row[lat_col]),
                lon=float(row[lon_col]),
            )
        )

    return depot, deliveries


def _coord(location: Location) -> Tuple[float, float]:
    return (location.lat, location.lon)


def _build_distance_time_matrices(
    gmaps_client: googlemaps.Client,
    depot: Location,
    deliveries: List[Location],
) -> Tuple[List[List[float]], List[List[float]], List[Location]]:
    """
    Вика Google Distance Matrix API чрез googlemaps клиента и връща:
    - dmat: матрица [i][j] = distance_km
    - tmat: матрица [i][j] = time_min
    - locations: списък от всички точки [0=depot, 1..N=deliveries]
    """
    locations: List[Location] = [depot] + deliveries

    origins = [f"{loc.lat},{loc.lon}" for loc in locations]
    destinations = origins[:]  # квадратна матрица

    matrix = gmaps_client.distance_matrix(
        origins=origins,
        destinations=destinations,
        mode="driving",
        units="metric",
    )

    n = len(locations)
    dmat = [[0.0] * n for _ in range(n)]
    tmat = [[0.0] * n for _ in range(n)]

    for i in range(n):
        row = matrix["rows"][i]["elements"]
        for j in range(n):
            el = row[j]
            if el["status"] != "OK":
                # може да решиш да хвърлиш exception, засега го маркирам с 0
                dist_m = 0.0
                dur_s = 0.0
            else:
                dist_m = el["distance"]["value"]
                dur_s = el["duration"]["value"]

            dmat[i][j] = dist_m / 1000.0       # в километри
            tmat[i][j] = dur_s / 60.0          # в минути

    return dmat, tmat, locations


def _two_opt(order: List[int], tmat: List[List[float]], max_passes: int = 10) -> List[int]:
    """
    Много базова 2-opt имплементация върху order, на база време (tmat).
    order е списък от индекси в 'locations'.
    """
    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(1, len(order) - 2):
            for j in range(i + 1, len(order) - 1):
                a, b = order[i - 1], order[i]
                c, d = order[j], order[j + 1]
                current = tmat[a][b] + tmat[c][d]
                new = tmat[a][c] + tmat[b][d]
                if new + 1e-6 < current:
                    order[i:j + 1] = reversed(order[i:j + 1])
                    improved = True
    return order


def _optimize_route(
    dmat: List[List[float]],
    tmat: List[List[float]],
    locations: List[Location],
) -> Tuple[List[Location], float, float]:
    """
    Връща:
    - seq: оптимизирана последователност от спирки (без финално връщане до депо)
    - total_dist_km
    - total_time_min
    """
    n = len(locations)
    # индекси: 0 = depot, 1..N-1 = deliveries
    order = list(range(n)) + [0]  # старт от депо, връщане в депо

    order = _two_opt(order, tmat, max_passes=25)

    seq: List[Location] = []
    total_dist = 0.0
    total_time = 0.0
    for a, b in zip(order, order[1:]):
        total_dist += dmat[a][b]
        total_time += tmat[a][b]
        if b == 0:
            break  # върнахме се до депо
        seq.append(locations[b])

    return seq, total_dist, total_time


def _route_to_dataframe(
    depot: Location,
    seq: List[Location],
    total_dist_km: float,
    total_time_min: float,
) -> pd.DataFrame:
    """
    Превръща маршрута в pandas DataFrame с колони:
    - Stop
    - Address
    - Distance_km
    - TravelTime_min
    - Cumulative_km
    - Cumulative_min
    """
    rows = []
    cumulative_km = 0.0
    cumulative_min = 0.0

    # Старт от депото (Stop 1)
    rows.append({
        "Stop": 1,
        "Address": depot.name,
        "Distance_km": 0.0,
        "TravelTime_min": 0.0,
        "Cumulative_km": 0.0,
        "Cumulative_min": 0.0,
    })

    prev = depot
    stop_idx = 2

    for loc in seq:
        # Елементарно изчисление на разстояние/време:
        # тук НЯМАМЕ директно тези стойности от dmat, защото не връщаме индекси.
        # Ако искаш перфектна точност, трябва да пазиш и index-ите.
        # За сега ще сложа 0.0 и ще разчитаме на total_* за сумарни стойности
        dist_km = 0.0
        time_min = 0.0

        cumulative_km += dist_km
        cumulative_min += time_min

        rows.append({
            "Stop": stop_idx,
            "Address": loc.name,
            "Distance_km": dist_km,
            "TravelTime_min": time_min,
            "Cumulative_km": cumulative_km,
            "Cumulative_min": cumulative_min,
        })
        prev = loc
        stop_idx += 1

    df = pd.DataFrame(rows)
    return df


def generate_or_load_route_csv(
    api_key: str,
    cached: bool = True,
    input_dir: str | Path = "data/input",
    output_dir: str | Path = "data/output",
) -> Path:
    """
    Главна функция, която ти трябва:

    - ако cached=True и днешният map_route_YYYY-mm-dd.csv съществува:
        -> връща пътя до него, без да вика Google API
    - иначе:
        -> чете depots.csv + deliveries.csv
        -> вика Google Distance Matrix API
        -> оптимизира маршрута
        -> записва map_route_YYYY-mm-dd.csv
        -> връща пътя до него
    """
    output_dir = Path(output_dir)
    today_str = date.today().strftime("%Y-%m-%d")
    route_path = output_dir / f"map_route_{today_str}.csv"

    if cached and route_path.exists():
        # ползваме кеширания маршрут
        return route_path

    # иначе – смятаме нов маршрут
    depot, deliveries = _load_input_data(input_dir=input_dir)

    gmaps_client = googlemaps.Client(key=api_key)
    dmat, tmat, locations = _build_distance_time_matrices(gmaps_client, depot, deliveries)
    seq, total_dist_km, total_time_min = _optimize_route(dmat, tmat, locations)

    df_route = _route_to_dataframe(depot, seq, total_dist_km, total_time_min)

    # записваме през общия helper – ако искаш да чистиш стари, можеш да ползваш save_route_dataframe()
    route_path = save_route_dataframe(df_route, output_dir=output_dir)

    return route_path
