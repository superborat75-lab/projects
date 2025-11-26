# services/route_output.py

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


def cleanup_old_routes(output_dir: str | Path = "data/output") -> None:
    """
    Триe всички стари map_route_*.csv в output_dir.
    Викаш го преди да запишеш нов маршрут.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for p in output_dir.glob("map_route_*.csv"):
        try:
            p.unlink()
        except OSError:
            # не се трия – ама и не ми пука, просто продължаваме
            pass


def get_today_route_path(output_dir: str | Path = "data/output") -> Path:
    """
    Връща път за днешния маршрут: map_route_YYYY-mm-dd.csv
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    today_str = date.today().strftime("%Y-%m-%d")
    return output_dir / f"map_route_{today_str}.csv"


def save_route_dataframe(
    df: pd.DataFrame,
    output_dir: str | Path = "data/output",
) -> Path:
    """
    Унифициран начин да запишеш маршрута:
    - чисти стари map_route_*.csv
    - записва df в map_route_YYYY-mm-dd.csv
    - връща пътя до файла
    """
    cleanup_old_routes(output_dir)
    path = get_today_route_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
