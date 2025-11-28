import json
import os
import sys
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv

# Зареждаме .env от текущата директория
load_dotenv()

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "").rstrip("/")
ERP_TOKEN = os.getenv("ERP_TOKEN", "")
TRANS_NAMESPACE = os.getenv("TRANS_NAMESPACE", "healthstore")


def pretty(obj, max_len=1500):
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(txt) > max_len:
        return txt[:max_len] + "\n... (truncated) ..."
    return txt


def parse_date_arg() -> date:
    """Чете дата от аргументите или връща вчера."""
    if len(sys.argv) < 2:
        # по подразбиране – вчера
        return date.today() - timedelta(days=1)

    raw = sys.argv[1].strip()
    # опит 1: YYYY-MM-DD
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        pass

    # опит 2: DD.MM.YYYY (по-човешки формат)
    try:
        return datetime.strptime(raw, "%d.%m.%Y").date()
    except ValueError:
        pass

    raise SystemExit(f"Невалидна дата: {raw} (очаквам YYYY-MM-DD или DD.MM.YYYY)")


def api_get_trans(for_date: date):
    """Тест на /api/RPC.{namespace}.API.getTrans (GET)."""
    if not ERP_BASE_URL or not ERP_TOKEN:
        raise SystemExit("ERP_BASE_URL или ERP_TOKEN липсват в .env")

    url = f"{ERP_BASE_URL}/api/RPC.{TRANS_NAMESPACE}.API.getTrans"
    params = {"token": ERP_TOKEN, "for_date": for_date.isoformat()}

    print(f"\n=== getTrans за дата {for_date} ===")
    print("GET", url)
    print("params =", params)

    r = requests.get(url, params=params, timeout=60)
    print("HTTP status:", r.status_code)
    r.raise_for_status()

    body = r.json()
    data = body.get("data") if isinstance(body, dict) else body
    if not data:
        print("Няма данни.")
        return

    print("Брой записи:", len(data))
    print("Първи елемент:")
    print(pretty(data[0]))


def api_store_out(for_date: date):
    """Тест на StoreOut (POST)."""
    if not ERP_BASE_URL or not ERP_TOKEN:
        raise SystemExit("ERP_BASE_URL или ERP_TOKEN липсват в .env")

    url = f"{ERP_BASE_URL}/api/RPC.common.Api.StoreOut.get?token={ERP_TOKEN}"
    payload = {"data": [{"for_date": for_date.isoformat()}]}

    print(f"\n=== StoreOut за дата {for_date} ===")
    print("POST", url)
    print("payload =", payload)

    r = requests.post(url, json=payload, timeout=60)
    print("HTTP status:", r.status_code)
    r.raise_for_status()

    body = r.json()
    data = None

    if isinstance(body, dict):
        data = body.get("result")
        if data is None and isinstance(body.get("data"), dict):
            data = body["data"].get("result")

    if not data:
        print("Няма резултати.")
        return

    print("Брой записи:", len(data))
    print("Първи елемент:")
    print(pretty(data[0]))


def api_availabilities():
    """Тест на Availabilities."""
    if not ERP_BASE_URL or not ERP_TOKEN:
        raise SystemExit("ERP_BASE_URL или ERP_TOKEN липсват в .env")

    url = f"{ERP_BASE_URL}/api/RPC.common.Api.AvailabilitiesByLabels.get?token={ERP_TOKEN}"
    payload = {
        "data": {
            "stores_names": None,
            "skus_codes": None,
            "labels": [],
            "have_availability": True,
        }
    }

    print("\n=== Availabilities (sample) ===")
    print("POST", url)
    print("payload =", payload)

    r = requests.post(url, json=payload, timeout=60)
    print("HTTP status:", r.status_code)
    r.raise_for_status()

    body = r.json()
    data = None

    if isinstance(body, dict):
        data = body.get("data", {}).get("result") or body.get("result")

    if not data:
        print("Няма резултати.")
        return

    print("Брой записи:", len(data))
    print("Първи елемент:")
    print(pretty(data[0]))


if __name__ == "__main__":
    d = parse_date_arg()
    print(f"Използвам дата: {d}")

    api_get_trans(d)
    api_store_out(d)
    api_availabilities()
