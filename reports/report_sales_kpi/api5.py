import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "").rstrip("/")
ERP_TOKEN = os.getenv("ERP_TOKEN", "")

STOREOUT_ID = 81000143938094   # това е StoreOut trans_id

def pretty(x):
    return json.dumps(x, ensure_ascii=False, indent=2)

def main():
    url = f"{ERP_BASE_URL}/api/RPC.common.Api.DocInfo.get?token={ERP_TOKEN}"
    payload = {"data": [{"id": STOREOUT_ID}]}

    print("POST", url)
    print("payload =", payload)

    resp = requests.post(url, json=payload, timeout=60)
    print("HTTP", resp.status_code)
    resp.raise_for_status()

    data = resp.json()
    print("\n=== RAW JSON ===")
    print(pretty(data))

    print("\n=== ВСИЧКИ КЛЮЧОВЕ В rows[] ===")
    rows = data["data"]["result"][0].get("rows", [])
    if rows:
        for k in rows[0].keys():
            print(k)

if __name__ == "__main__":
    main()
