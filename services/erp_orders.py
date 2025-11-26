# services/erp_orders.py

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.erp_client import (
    erp_post,
    ERPClientError,
    get_doc_info,
    log_info,
    log_debug,
    log_error,
)


class ERPOrdersError(Exception):
    """Грешка в по-високото ниво (продажби/спирки)."""
    pass


@dataclass
class OrderRow:
    """Един вътрешен ред от DocInfo.get – артикул към адрес/клиент."""
    id: int
    client: str
    address: str
    sku: str
    product: str
    qty: float
    for_date: str


# ───────────────────────────────
# So.get — продажби по дата
# ───────────────────────────────

def fetch_so_docs(for_date: date) -> List[Dict[str, Any]]:
    """
    Вика So.get по for_date и връща пълните SO документи (dict-ове).

    Очакван формат на отговора от ERP:

      {
        "status": "ok",
        "data": {
          "result": [ {...}, {...} ],
          "count": 7
        }
      }

      или по-стария вариант:
      {
        "result": [ {...}, {...} ],
        "count": 7
      }
    """
    payload = {"data": [{"for_date": for_date.isoformat()}]}
    try:
        raw = erp_post("So.get", payload)
        log_debug(f"[SO] RAW от So.get: {raw}")
    except ERPClientError as e:
        raise ERPOrdersError(f"Грешка при So.get: {e}")

    docs: List[Dict[str, Any]] = []

    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, dict) and isinstance(data.get("result"), list):
            result = data["result"]
        elif isinstance(raw.get("result"), list):
            result = raw["result"]
        else:
            result = []
    else:
        result = []

    for doc in result:
        if isinstance(doc, dict):
            docs.append(doc)

    log_info(f"🔍 Извлякохме {len(docs)} продажби (SO документи) от So.get за дата {for_date.isoformat()}")
    return docs


def fetch_sales_rows_for_date(for_date: date) -> List[Dict[str, Any]]:
    """
    High-level:
      1) So.get(for_date) -> SO документи
      2) Вадим от тях всички store_out.rel_trans_id
      3) DocInfo.get(store_out_id) ПО ЕДИН → rows
      4) Събираме всички rows
    """
    so_docs = fetch_so_docs(for_date)

    store_out_ids: List[int] = []
    for doc in so_docs:
        so_id = doc.get("id")
        rels = doc.get("rel_trans")
        if not isinstance(rels, list):
            log_debug(f"[SO] Документ {so_id} няма rel_trans или не е списък.")
            continue
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            if rel.get("type") == "store_out":
                try:
                    sid = int(rel.get("rel_trans_id"))
                    store_out_ids.append(sid)
                    log_debug(f"[SO] SO {so_id} → store_out rel_trans_id={sid}")
                except (TypeError, ValueError):
                    log_error(f"[SO] Невалидно store_out rel_trans_id в {rel}")
                    continue

    log_info(f"📦 Извлякохме {len(store_out_ids)} store_out ID-та от So.get: {store_out_ids}")

    if not store_out_ids:
        log_info("⚠️ Няма нито едно store_out.rel_trans_id – няма какво да дадем на DocInfo.get")
        return []

    all_rows: List[Dict[str, Any]] = []

    # ВАЖНО: викаме DocInfo.get по ЕДИН id, защото batch явно не връща rows
    for sid in store_out_ids:
        try:
            rows = get_doc_info([sid])
        except ERPClientError as e:
            log_error(f"[DocInfo] Грешка при DocInfo.get за store_out {sid}: {e}")
            continue

        if not isinstance(rows, list):
            log_error(f"[DocInfo] DocInfo.get за {sid} не върна списък (rows) → {rows}")
            continue

        log_info(f"   ↳ store_out {sid} върна {len(rows)} rows")
        all_rows.extend(rows)

    log_info(f"🧾 Общо DocInfo rows за дата {for_date.isoformat()}: {len(all_rows)}")
    if all_rows:
        sample = all_rows[0]
        log_debug("🔎 Примерен row от DocInfo: " + str({
            "delivery_full_address": sample.get("delivery_full_address"),
            "to_nm": sample.get("to_nm"),
            "num": sample.get("num"),
            "qty/confirmed_quantity": sample.get("qty") or sample.get("confirmed_quantity"),
        }))

    return all_rows


# ───────────────────────────────
# Мапване към вътрешна структура
# ───────────────────────────────

def _to_order_row(raw: Dict[str, Any]) -> Optional[OrderRow]:
    """
    Мапва един raw row от DocInfo.get към удобен OrderRow.
    Очакваме полета:
      - delivery_full_address / delivery_address_nm
      - to_nm / partner_nm
      - num (SKU)
      - nm (product name)
      - confirmed_quantity / qty / quantity
      - for_date
    """
    address = (
        raw.get("delivery_full_address")
        or raw.get("delivery_address_nm")
        or ""
    )
    if not address:
        # без адрес няма спирка
        log_debug(f"[MAP] Пропускам row без адрес: {raw}")
        return None

    client = (
        (raw.get("to_nm") or raw.get("partner_nm") or "").strip()
        or "UNKNOWN_CLIENT"
    )

    sku = str(raw.get("num") or "").strip()
    product = str(raw.get("nm") or "").strip()

    qty_str = (
        raw.get("confirmed_quantity")
        or raw.get("qty")
        or raw.get("quantity")
        or "0"
    )
    try:
        qty = float(str(qty_str).replace(",", "."))
    except Exception:
        qty = 0.0

    for_date = str(raw.get("for_date") or "")

    try:
        row_id = int(raw.get("id"))
    except Exception:
        row_id = 0

    return OrderRow(
        id=row_id,
        client=client,
        address=address.strip(),
        sku=sku,
        product=product,
        qty=qty,
        for_date=for_date,
    )


def normalize_address(addr: str) -> str:
    addr = (addr or "").strip().lower()
    while "  " in addr:
        addr = addr.replace("  ", " ")
    return addr


def build_stops_from_rows(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Групира ERP rows по адрес:
      - 1 адрес = 1 спирка (stop)
      - вътре пазим всички артикули/продажби за този адрес
    """
    grouped: Dict[str, Dict[str, Any]] = {}

    for raw in raw_rows:
        row = _to_order_row(raw)
        if row is None:
            continue

        key = normalize_address(row.address)

        stop = grouped.setdefault(
            key,
            {
                "client": row.client,
                "address": row.address,
                "orders": [],
            },
        )

        stop["orders"].append(
            {
                "sku": row.sku,
                "product": row.product,
                "qty": row.qty,
                "id": row.id,
                "for_date": row.for_date,
            }
        )

    stops: List[Dict[str, Any]] = []
    for key, stop in grouped.items():
        orders = stop["orders"]
        client = stop["client"]
        order_count = len(orders)

        if order_count == 1:
            name = client
        else:
            name = f"{client} ({order_count} продажби)"

        stops.append(
            {
                "name": name,
                "address": stop["address"],
                "client": client,
                "orders": orders,
            }
        )

    log_info(f"📦 Сглобихме {len(stops)} спирки (уникални адреси) от {len(raw_rows)} DocInfo rows.")
    return stops


# ───────────────────────────────
# Генериране на deliveries.csv
# ───────────────────────────────

def write_deliveries_csv_from_stops(stops: List[Dict[str, Any]], path: Path) -> None:
    """
    Пише deliveries.csv във формат:
      name,address
    Това е форматът, който main.py очаква.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "address"])
        for stop in stops:
            writer.writerow([stop["name"], stop["address"]])

    log_info(f"📄 Записах deliveries.csv ({len(stops)} реда) в {path}")


def generate_deliveries_for_date(for_date: date, deliveries_csv_path: Path) -> List[Dict[str, Any]]:
    """
    High-level:
      1) So.get(for_date)           -> SO документи
      2) store_out.rel_trans_id     -> ID-та за DocInfo.get
      3) DocInfo.get(store_out_id)  -> rows за доставките (по един)
      4) Групиране по адрес         -> спирки
      5) Писане на deliveries.csv   -> вход за mapFleet
    """
    raw_rows = fetch_sales_rows_for_date(for_date)
    stops = build_stops_from_rows(raw_rows)
    write_deliveries_csv_from_stops(stops, deliveries_csv_path)
    return stops
