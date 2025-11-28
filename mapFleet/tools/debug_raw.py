from services.erp_client import erp_post, ERPClientError

DOC_ID = 81000145966287  # същото ID, което гледахме в JSON-а 81000143938094

try:
    raw = erp_post("DocInfo.get", {"data": [{"id": DOC_ID}]})
except ERPClientError as e:
    print("❌ ERPClientError:", e)
    exit()

print("\nRAW ERP RESPONSE:")
print(raw)

# опитаме да извадим rows ръчно
try:
    print("\nTRYING: raw['result'][0]['rows']")
    print(raw["result"][0]["rows"])
except Exception as e:
    print("❌ Error extracting rows manually:", e)
