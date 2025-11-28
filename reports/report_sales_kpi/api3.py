import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "").rstrip("/")
ERP_TOKEN = os.getenv("ERP_TOKEN", "")
TRANS_NAMESPACE = os.getenv("TRANS_NAMESPACE", "healthstore")

FOR_DATE = "2025-11-18"  # тук може да сменяш по желание


def main():
    if not ERP_BASE_URL or not ERP_TOKEN:
        raise SystemExit("ERP_BASE_URL или ERP_TOKEN липсват в .env")

    url = f"{ERP_BASE_URL}/api/RPC.{TRANS_NAMESPACE}.API.getTrans"
    params = {"token": ERP_TOKEN, "for_date": FOR_DATE}

    print(f"GET {url}")
    print("params =", params)

    resp = requests.get(url, params=params, timeout=60)
    print("HTTP status:", resp.status_code)
    resp.raise_for_status()

    body = resp.json()

    # печатаме ПЪЛНИЯ JSON, без рязане
    print("\n=== RAW JSON ===")
    print(json.dumps(body, ensure_ascii=False, indent=2))

    # записваме и във файл, за да го разглеждаш спокойно
    out_name = f"getTrans_{FOR_DATE}.json"
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)

    print(f"\nЗаписано в файл: {out_name}")


if __name__ == "__main__":
    main()
