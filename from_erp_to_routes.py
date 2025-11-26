# from_erp_to_routes.py

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import subprocess
import sys

from services.erp_orders import generate_deliveries_for_date


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "data" / "input"
DELIVERIES_FILE = INPUT_DIR / "deliveries.csv"


def run(cmd: list[str]) -> None:
    print(f"\n➡️  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"❌ Command failed with code {result.returncode}: {result.returncode}")
        sys.exit(result.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Генерира доставки от ERP за дадена дата и пуска mapFleet маршрутизацията."
    )
    parser.add_argument(
        "--date",
        dest="date_str",
        help="Дата за маршрута във формат YYYY-MM-DD (пример: 2025-11-25). "
             "Ако не е подадена, се използва днешната дата.",
    )
    return parser.parse_args()


def parse_route_date(date_str: str | None) -> date:
    if not date_str:
        # няма подадена дата -> днес
        return date.today()

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.date()
    except ValueError:
        print(f"❌ Невалиден формат за --date: {date_str}. Очаквам YYYY-MM-DD (пример: 2025-11-25).")
        sys.exit(1)


def main():
    args = parse_args()
    route_date = parse_route_date(args.date_str)

    print(f"📅 Генерирам доставки от ERP за дата: {route_date.isoformat()}")

    stops = generate_deliveries_for_date(route_date, DELIVERIES_FILE)
    print(f"📦 От ERP извадихме {len(stops)} спирки (уникални адреси).")
    print(f"📄 deliveries.csv -> {DELIVERIES_FILE}")

    if not stops:
        print("❌ Няма нито една спирка за тази дата – прекратявам, без да пускам main.py.")
        return

    # пускаме твоя pipeline: main.py + generate_links.py
    run(["python", "run_all.py", "--no-cache"])


if __name__ == "__main__":
    main()
