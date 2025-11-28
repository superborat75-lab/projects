import json
import os
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "").rstrip("/")
ERP_TOKEN = os.getenv("ERP_TOKEN", "")
TRANS_NAMESPACE = os.getenv("TRANS_NAMESPACE", "healthstore")


def pretty(obj, max_len=1000):
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(txt) > max_len:
        return txt[:max_len] + "\n... (truncated) ..."
    return txt


def test_transactions(for_date: date):
    """Тества /api/RPC.{NS}.API.getTrans"""
    url = f"{ERP_BASE_URL}/api/RPC.{TRANS_NAMESPACE}.API.getTrans"
    params = {"token": ERP_TOKEN, "for_date": for_date.isoformat()}
    print(f"\n=== Transactions for {for_date} ===")
    print("GET", url, "params=", params)
    r = requests.get(url, params=params, timeout=60)
    print("Status:", r.status_code)
    body = r.json()
    # пробваме да вземем списъка с транзакции
    data = body.get("data") if isinstance(body, dict) else body
    if not data:
        print("No data")
        return
    print("Items:", len(data))
    print("First item raw:")
    print(pretty(data[0]))


def test_store_out(for_date: date):
    """Тества /api/RPC.common.Api.StoreOut.get"""
    url = f"{ERP_BASE_URL}/api/RPC.common.Api.StoreOut.get"
    payload = {"data": [{"for_date": for_date.isoformat()}]}
    params = {"token": ERP_TOKEN}
    print(f"\n=== StoreOut for {for_date} ===")
    print("POST", url, "params=", params, "payload=", payload)
    r = requests.post(f"{url}?token={ERP_TOKEN}", json={"data": [{"for_date": for_date.isoformat()}]}, timeout=60)
    print("Status:", r.status_code)
    body = r.json()
    # result може да е в body["data"]["result"] или body["result"]
    if isinstance(body, dict):
        data = body.get("result")
        if data is None and isinstance(body.get("data"), dict):
            data = body["data"].get("result")
    else:
        data = body
    if not data:
        print("No data")
        return
    print("Items:", len(data))
    print("First item raw:")
    print(pretty(data[0]))


def test_availabilities():
    """Тества /api/RPC.common.Api.AvailabilitiesByLabels.get"""
    url = f"{ERP_BASE_URL}/api/RPC.common.Api.AvailabilitiesByLabels.get?token={ERP_TOKEN}"
    payload = {
        "data": {
            "stores_names": None,  # всички
            "skus_codes": None,    # всички
            "labels": [],
            "have_availability": True,
        }
    }
    print("\n=== Availabilities (sample) ===")
    print("POST", url)
    r = requests.post(url, json=payload, timeout=60)
    print("Status:", r.status_code)
    body = r.json()
    if isinstance(body, dict):
        data = body.get("data", {}).get("result") or body.get("result")
    else:
        data = body
    if not data:
        print("No data")
        return
    print("Items:", len(data))
    print("First item raw:")
    print(pretty(data[0]))


if __name__ == "__main__":
    # Вземаме вчера, за да има по-голям шанс да има транзакции
    d = date.today() - timedelta(days=1)

    test_transactions(d)
    test_store_out(d)
    test_availabilities()
