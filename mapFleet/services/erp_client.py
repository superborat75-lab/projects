# services/erp_client.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import ERP_BASE_URL, ERP_TOKEN


class ERPClientError(Exception):
    """Грешка при работа с ERP API."""
    pass


# ───────────────────────────────
# Прост логер за ERP слоя
# ───────────────────────────────

_LOG_VERBOSE: bool = False
_LOG_FILE_PATH: Optional[Path] = None


def configure_erp_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """
    Конфигурира логването за ERP слоя.

    :param verbose: ако е True → показва подробни (debug) логове
    :param log_file: ако е подаден път → записва логовете и в този файл
    """
    global _LOG_VERBOSE, _LOG_FILE_PATH
    _LOG_VERBOSE = bool(verbose)
    _LOG_FILE_PATH = Path(log_file) if log_file else None


def _log_write(line: str, *, force: bool = False) -> None:
    """
    Вътрешна функция за писане на един ред лог.

    :param line: текстът за лог
    :param force: ако е True → пишем винаги (info/error),
                  ако е False → само при включен verbose.
    """
    from datetime import datetime

    if not force and not _LOG_VERBOSE:
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {line}"

    # към конзолата
    print(formatted)

    # към файл, ако има
    if _LOG_FILE_PATH is not None:
        _LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with _LOG_FILE_PATH.open("a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception:
            # не чупим програмата, ако лог файла не може да се запише
            pass


def log_info(msg: str) -> None:
    """Информационен лог (винаги се показва)."""
    _log_write(f"[INFO] {msg}", force=True)


def log_error(msg: str) -> None:
    """Грешка (винаги се показва)."""
    _log_write(f"[ERROR] {msg}", force=True)


def log_debug(msg: str) -> None:
    """Подробен лог (само при verbose)."""
    _log_write(f"[DEBUG] {msg}", force=False)


# ───────────────────────────────
# Конфигурация
# ───────────────────────────────

def _check_config() -> None:
    """
    Проверява дали ERP_BASE_URL и ERP_TOKEN са зададени.
    """
    if not ERP_BASE_URL:
        raise ERPClientError("ERP_BASE_URL не е зададен (виж .env / config.py).")
    if not ERP_TOKEN:
        raise ERPClientError("ERP_TOKEN не е зададен (виж .env / config.py).")


def _build_base_url() -> str:
    """
    Връща базовия URL за RPC повикванията.

    Поддържа и двата варианта в .env:

      ERP_BASE_URL=https://dimkat.prim.io
      или
      ERP_BASE_URL=https://dimkat.prim.io/api

    И в двата случая крайният резултат ще е:

      https://dimkat.prim.io/api
    """
    base = (ERP_BASE_URL or "").rstrip("/")

    if not base.endswith("/api"):
        base = base + "/api"

    return base


# ───────────────────────────────
# Основен HTTP клиент към ERP
# ───────────────────────────────

def erp_post(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Вика ERP RPC метод:

        POST <BASE>/RPC.common.Api.<method>?token=<ERP_TOKEN>

    Пример с So.get:
        POST https://dimkat.prim.io/api/RPC.common.Api.So.get?token=...

    payload се подава като JSON (json=payload).
    """
    _check_config()

    base = _build_base_url()
    url = f"{base}/RPC.common.Api.{method}"
    params = {"token": ERP_TOKEN}
    headers = {"Content-Type": "application/json; charset=utf-8"}

    log_debug(f"[ERP] POST {url}")
    log_debug(f"[ERP] Params: {params}")
    log_debug(f"[ERP] Payload: {payload}")

    try:
        resp = requests.post(url, params=params, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        log_error(f"Грешка при връзка към ERP API: {e}")
        raise ERPClientError(f"Грешка при връзка към ERP API: {e}")

    log_debug(f"[ERP] HTTP {resp.status_code}")
    log_debug(f"[ERP] RAW response: {resp.text[:1500]}")

    if not resp.ok:
        msg = f"ERP HTTP {resp.status_code}: {resp.text[:500]}"
        log_error(msg)
        raise ERPClientError(msg)

    try:
        data = resp.json()
    except ValueError:
        msg = f"ERP върна невалиден JSON: {resp.text[:500]}"
        log_error(msg)
        raise ERPClientError(msg)

    return data


# ───────────────────────────────
# DocInfo.get helper
# ───────────────────────────────

def get_doc_info(ids: List[int]) -> List[Dict[str, Any]]:
    """
    Обвивка за RPC.common.Api.DocInfo.get.

    payload:
        {"data":[{"id":ID1},{"id":ID2}, ...]}

    Връща списък с вътрешните "rows" (артикулните редове) за
    всички подадени документи (store_out, invoice, so и т.н.).
    """
    if not ids:
        return []

    payload = {"data": [{"id": int(i)} for i in ids]}
    log_debug(f"[ERP] DocInfo.get payload: {payload}")

    raw = erp_post("DocInfo.get", payload)

    rows: List[Dict[str, Any]] = []

    if not isinstance(raw, dict):
        log_error(f"[ERP] DocInfo.get върна не-dict: {raw}")
        return rows

    # Двата възможни формата:
    # 1) { "data": { "result": [ {...}, ... ] }, ... }
    # 2) { "result": [ {...}, ... ], ... }
    data = raw.get("data")
    if isinstance(data, dict) and isinstance(data.get("result"), list):
        result = data["result"]
    elif isinstance(raw.get("result"), list):
        result = raw["result"]
    else:
        result = []

    for doc in result:
        if not isinstance(doc, dict):
            continue
        inner_rows = doc.get("rows")
        if isinstance(inner_rows, list):
            rows.extend(inner_rows)

    log_debug(f"[ERP] DocInfo.get ids={ids} → {len(rows)} rows")
    return rows
