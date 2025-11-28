# test_docinfo.py
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "").rstrip("/")
ERP_TOKEN = os.getenv("ERP_TOKEN", "")

DOC_ID = 81000143938094   # тук слагаш реално id от StoreOut.get

def pretty(x):
    return json.dumps(x, ensure_ascii=False, indent=2)

def main():
    url = f"{ERP_BASE_URL}/api/RPC.common.Api.DocInfo.get?token={ERP_TOKEN}"
    payload = {
        "data": [
            {"id": DOC_ID}
        ]
    }
    print("POST", url)
    print("payload =", payload)

    resp = requests.post(url, json=payload, timeout=60)
    print("HTTP status:", resp.status_code)
    resp.raise_for_status()
    body = resp.json()
    print("\nRAW JSON:")
    print(pretty(body))

if __name__ == "__main__":
    main()
