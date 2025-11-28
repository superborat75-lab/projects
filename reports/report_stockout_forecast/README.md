report_stockout_forecast

Purpose
- Generate a stock-out forecast (when each SKU will run out) based on recent sales velocity and current on-hand inventory from the ERP.
- Produce a simple HTML report highlighting urgency with colors and suggested order dates based on lead times.

What it does
1. Loads configuration from .env (ERP URL/token, lead times, filters, etc.).
2. Pulls sales transactions for the last 30 days and aggregates to daily sales per SKU.
3. Computes average daily sales rate per SKU (window = last 30 sales days up to today).
4. Pulls store-level availabilities and aggregates on-hand quantity per SKU.
5. Optionally fetches items list to filter out inactive SKUs.
6. Calculates:
   - days_of_stock = on_hand / avg_daily
   - depletion_date (today + ceil(days_of_stock)) when avg_daily > 0
   - order_date = depletion_date − (LEAD_DELIVERY_DAYS + LEAD_PRODUCTION_DAYS)
   - status: urgent | need attention | ok
7. Renders templates/report.html.j2 into out.html inside reports/report_stockout_forecast (next to this module), regardless of current working directory.

Project layout
- main.py — CLI entrypoint orchestrating the pipeline and saving out.html
- core.py — ERP calls, transformations (Polars), forecasting, and HTML rendering
- templates/report.html.j2 — Jinja2 HTML template (Bulgarian labels)
- requirements.txt — runtime dependencies
- tests/test_core.py — simple API connectivity check (not a formal unit test)

Prerequisites
- Python 3.10+
- Access to an ERP endpoint that supports the RPC calls used here (see .env example)

Installation
1. Create and activate a virtual environment (recommended):
   - python -m venv .venv
   - source .venv/bin/activate  (Linux/macOS)
     or .venv\\Scripts\\activate  (Windows)
2. Install dependencies:
   - pip install -r requirements.txt
3. Prepare .env file (see below).

Environment variables (.env)
Required
- ERP_BASE_URL — Base ERP URL, e.g. https://example.com (no trailing slash is fine; code strips it).
- ERP_TOKEN — API access token for the ERP.

Common/Optional
- TRANS_NAMESPACE — Namespace for the sales transactions endpoint. Default: healthstore
- LEAD_DELIVERY_DAYS — Days for delivery lead time. Default: 30 (unless LEAD_TIME_DAYS is set)
- LEAD_PRODUCTION_DAYS — Days for production lead time. Default: 0
- LEAD_TIME_DAYS — Backward-compatible alias for delivery lead time; used if LEAD_DELIVERY_DAYS is not set
- ITEMS_CACHE — true/false to enable caching fetched items to JSON. Default: false
- ITEMS_CACHE_PATH — Path to items cache file. Default: items.json
- ERP_EXCLUDE_STORES — Comma-separated store names to exclude from availability aggregation
- STORES — Comma-separated store names to include, or ALL to include all stores. Default: ALL
- SKUS — Comma-separated SKU codes to include, or ALL to include all SKUs. Default: ALL
- HORIZON_DAYS — Planning horizon affecting the "need attention" classification. Default: 30
- INCLUDE_OOS — If true, include out-of-stock items when fetching availabilities. Default: false

Notes on behavior
- Sales window: The average daily rate is computed over the last 30 calendar days up to today, dividing total sold quantity in that window by the full window length (including zero-sale days). If there are no sales in the window, the rate is 0.
- Active items filtering: If the items API returns activity indicators (status/active/is_active/IsActive/item_status), the code attempts to infer active = true when the value is in {1, true, yes, active}. Non-truthy values explicitly present imply inactive. If no flag is present, the item defaults to active.
- Lead time and status:
  - total_lead = LEAD_DELIVERY_DAYS + LEAD_PRODUCTION_DAYS
  - status = urgent if days_of_stock <= total_lead
  - status = need attention if total_lead < days_of_stock <= total_lead + HORIZON_DAYS
  - status = ok otherwise or when average daily rate is zero/unknown

How to run
1. Ensure .env is configured and virtualenv is active.
2. From reports/report_stockout_forecast directory (or repository root), run:
   - python reports/report_stockout_forecast/main.py
   or if your CWD is the project folder:
   - python main.py
3. On success, the report is written to reports/report_stockout_forecast/out.html. Open it in a browser.

Sample .env
See reports/report_stockout_forecast/.env in the repository for a filled example (includes dummy values). Variables include:
- ERP_BASE_URL, ERP_TOKEN, TRANS_NAMESPACE
- SMTP_* and MAIL_* variables are present in the sample for compatibility with other tools, but this project does not send emails by itself.
- LEAD_* controls
- STORES, SKUS filters, ERP_EXCLUDE_STORES

Endpoints used (expected ERP API)
- Transactions (per day): GET {ERP_BASE_URL}/api/RPC.{TRANS_NAMESPACE}.API.getTrans?token=...&for_date=YYYY-MM-DD
- Availabilities: POST {ERP_BASE_URL}/api/RPC.common.Api.AvailabilitiesByLabels.get?token=...
  payload: {"data": {"stores_names": [..] | null, "skus_codes": [..] | null, "labels": [], "have_availability": true/false}}
- Items: POST {ERP_BASE_URL}/api/RPC.common.Api.Items.get?token=... with payload {"data": {}}

Troubleshooting
- Missing ERP credentials: core.py raises RuntimeError if ERP_BASE_URL or ERP_TOKEN are absent.
- Empty report: If no transactions or availabilities are returned, the table may be empty. Verify filters and ERP connectivity.
- Unexpected items shape: items normalization in core.py handles several common API response shapes. If still failing, capture the payload and extend normalization logic.

Testing
- tests/test_core.py performs a simple POST call to the Items endpoint using your .env and prints the response. It is not a pytest test and serves as a connectivity sanity check.

Technology stack
- Polars for data processing; Jinja2 for HTML templating; requests for HTTP; python-dotenv for config.

License
- Internal use. Add a license section here if you plan to distribute.
