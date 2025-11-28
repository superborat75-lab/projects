# services/gmaps_links_multi.py

from __future__ import annotations

import time
import webbrowser
from pathlib import Path
from typing import List, Dict

import pandas as pd


# ----------------------------------------------------------
# Helpers: адреси и линкове
# ----------------------------------------------------------

def _clean_addresses(series: pd.Series) -> List[str]:
    """
    Почиства колоната с адреси:
    - маха NaN
    - маха празни низове
    - маха 'nan' текстово
    """
    s = series.astype(str).str.strip()
    s = s[(s != "") & (s.str.lower() != "nan")]
    return s.tolist()


def _encode_addr(addr: str) -> str:
    """
    Енкод за Google Maps URL:
    - кирилицата остава както си е
    - space -> +
    - '|' -> %7C
    """
    return addr.strip().replace(" ", "+").replace("|", "%7C")


def _build_gmaps_url_from_segment(addresses: List[str]) -> str:
    """
    Прави един Google Maps URL от дадена последователност адреси.
    origin = първият, destination = последният, останалите -> waypoints.
    """
    if len(addresses) < 2:
        raise ValueError("Нужни са поне 2 адреса (origin + destination).")

    origin = addresses[0]
    destination = addresses[-1]
    waypoints = addresses[1:-1]

    origin_q = _encode_addr(origin)
    dest_q = _encode_addr(destination)
    wp_q = [_encode_addr(a) for a in waypoints]

    base = "https://www.google.com/maps/dir/?api=1"
    url = f"{base}&origin={origin_q}&destination={dest_q}&travelmode=driving"

    if wp_q:
        url += "&waypoints=" + "|".join(wp_q)

    return url


def _split_addresses(addresses: List[str], max_addrs: int) -> List[List[str]]:
    """
    Реже маршрута на сегменти, за да не надхвърлим лимита на Google URL-а.
    max_addrs = origin + waypoints + destination в ЕДИН линк.
    Правим overlap от 1 адрес между сегментите.
    """
    if max_addrs < 2:
        raise ValueError("max_addrs трябва да е >= 2.")

    n = len(addresses)
    if n <= max_addrs:
        return [addresses]

    segments: List[List[str]] = []
    step = max_addrs - 1  # overlap 1

    start = 0
    while start < n - 1:
        end = start + max_addrs
        seg = addresses[start:end]
        if len(seg) >= 2:
            segments.append(seg)
        start += step

    return segments


# ----------------------------------------------------------
# Public API
# ----------------------------------------------------------

def generate_gmaps_links_for_csv(
    csv_path: str | Path,
    address_col: str = "Address",
    max_addresses_per_link: int = 8,
) -> List[str]:
    """
    Връща списък от Google Maps URL-и за ЕДИН CSV на кола.
    Ако има повече от max_addresses_per_link адреса, прави няколко линка.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    df = pd.read_csv(csv_path)

    if address_col not in df.columns:
        raise ValueError(f"Колоната '{address_col}' не е намерена в {csv_path.name}")

    addresses = _clean_addresses(df[address_col])
    segments = _split_addresses(addresses, max_addresses_per_link)
    urls = [_build_gmaps_url_from_segment(seg) for seg in segments]
    return urls


def generate_gmaps_links_for_all_vehicles(
    output_dir: str | Path = "data/output",
    pattern: str = "vehicle_*_*.csv",
    address_col: str = "Address",
    max_addresses_per_link: int = 8,
    write_txt: bool = True,
    open_in_browser: bool = True,
    open_delay_seconds: float = 0.0,
    open_all_links: bool = False,
) -> Dict[str, List[str]]:
    """
    Намира всички vehicle_X_YYYY-mm-dd.csv и за всяка кола:
      - генерира 1..N Google Maps линка
      - по желание ги записва в .txt файлове
      - по желание отваря линковете в браузър:
          * ако open_all_links=False -> само първия линк
          * ако open_all_links=True  -> всички линкове със закъснение open_delay_seconds

    Връща dict:
        { "vehicle_1": [url1, url2, ...], ... }
    """
    output_dir = Path(output_dir)
    csv_paths = sorted(output_dir.glob(pattern))
    if not csv_paths:
        raise FileNotFoundError("Не са намерени vehicle_*.csv файлове в output_dir.")

    results: Dict[str, List[str]] = {}

    for csv_path in csv_paths:
        stem_parts = csv_path.stem.split("_")   # vehicle_1_2025-...
        vehicle_name = "_".join(stem_parts[:2]) # vehicle_1

        urls = generate_gmaps_links_for_csv(
            csv_path,
            address_col=address_col,
            max_addresses_per_link=max_addresses_per_link,
        )
        results[vehicle_name] = urls

        if write_txt:
            for i, url in enumerate(urls, start=1):
                txt_name = f"{vehicle_name}_google_map_link_{i}.txt"
                txt_path = output_dir / txt_name
                txt_path.write_text(url, encoding="utf-8")

        if open_in_browser and urls:
            if open_all_links:
                # отваряме ВСИЧКИ линкове със закъснение
                for url in urls:
                    webbrowser.open(url)
                    if open_delay_seconds > 0:
                        time.sleep(open_delay_seconds)
            else:
                # само първия линк (както преди)
                webbrowser.open(urls[0])

    return results
