"""
addresses.py - Load and manage delivery addresses from CSV files.

Expected CSVs in ./data/input/:
- deliveries.csv with column: address
- depots.csv with column: address
"""

import csv
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

INPUT_DIR = Path(__file__).parent / "input"
DELIVERIES_CSV = INPUT_DIR / "deliveries.csv"
DEPOTS_CSV = INPUT_DIR / "depots.csv"


def _ensure_file(path: Path, header: str):
    """
    Validates the existence of a CSV file and ensures the specified header exists as
    a column in the file. If the file does not exist or the header is not found,
    an exception is raised.

    :param path: The path to the CSV file to validate.
    :type path: Path
    :param header: The column header to validate in the CSV file.
    :type header: str
    :raises FileNotFoundError: If the file at the given path does not exist.
    :raises ValueError: If the specified header is not present in the CSV's
        column headers.
    """
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV file: {path}")
    # Validate header
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or header not in reader.fieldnames:
            raise ValueError(
                f"CSV '{path.name}' must contain column '{header}'. Found: {reader.fieldnames}"
            )


def _load_column(path: Path, header: str, dedupe: bool = True) -> List[str]:
    _ensure_file(path, header)
    seen = set()
    out: List[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            addr = (row.get(header) or "").strip()
            if not addr:
                continue
            if dedupe:
                if addr in seen:
                    continue
                seen.add(addr)
            out.append(addr)
    if not out:
        raise ValueError(f"CSV '{path.name}' contains no values in '{header}'.")
    return out


def get_deliveries() -> List[str]:
    return _load_column(DELIVERIES_CSV, "address", dedupe=True)


def get_depots() -> List[str]:
    return _load_column(DEPOTS_CSV, "address", dedupe=True)
