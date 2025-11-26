# services/erp_client.py

from __future__ import annotations

from typing import Any, Dict, List

import requests

from config import ERP_BASE_URL, ERP_TOKEN


class ERPClientError(Exception):
    """Грешка при работа с ERP API."""
    pass


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

    try:
        resp = requests.post(url, params=params, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise ERPClientError(f"Грешка при връзка към ERP API: {e}")

    if not resp.ok:
        raise ERPClientError(
            f"ERP HTTP {resp.status_code}: {resp.text[:500]}"
        )

    try:
        data = resp.json()
    except ValueError:
        raise ERPClientError(
            f"ERP върна невалиден JSON: {resp.text[:500]}"
        )

    return data


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
    raw = erp_post("DocInfo.get", payload)

    rows: List[Dict[str, Any]] = []

    if not isinstance(raw, dict):
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

    return rows
