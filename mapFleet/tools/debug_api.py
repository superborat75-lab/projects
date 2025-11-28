from services.erp_client import erp_post, ERPClientError

DOC_ID = 81000146071799  # store_out ID от So.get / StoreOut.get

try:
    raw = erp_post(
        "DocInfo.get",
        {
            "data": [
                {
                    "id": DOC_ID,
                    "type": "store_out",      # <-- добавяме тип
                    # евентуално:
                    # "type_action": "store_out"
                }
            ]
        },
    )
except ERPClientError as e:
    print("❌ ERPClientError:", e)
    exit()

print("\nRAW ERP RESPONSE:")
print(raw)
