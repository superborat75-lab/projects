import argparse
import os
from datetime import date, timedelta

import polars as pl

from core import (
    HORIZON_DAYS,
    avg_daily_rate,
    daily_sales,
    fetch_availabilities,
    fetch_items,
    fetch_store_out_range,
    fetch_transactions_range,
    filter_sales_by_store_out,
    items_to_polars,
    onhand_total,
    project_depletion,
    render_report,
    store_out_to_polars,
    transactions_to_polars,
)

WINDOW_DAYS = 30


def main() -> int:
    parser = argparse.ArgumentParser(description="Stock Depletion Forecast")
    parser.add_argument(
        "--send-email", action="store_true", help="Send email with HTML report"
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL cert verification (dev only)",
    )
    args = parser.parse_args()

    today = date.today()
    start = today - timedelta(days=WINDOW_DAYS - 1)

    # 1) Items
    items = fetch_items()
    df_items = items_to_polars(items)

    # 2) Sales + StoreOut filter
    tx = fetch_transactions_range(start, today)
    df_sales_all = transactions_to_polars(tx)
    sto = fetch_store_out_range(start, today)
    df_sto = store_out_to_polars(sto)
    df_sales = filter_sales_by_store_out(df_sales_all, df_sto)

    # 3) Avg daily rate
    df_daily = daily_sales(df_sales)
    df_rate = avg_daily_rate(df_daily, window_days=WINDOW_DAYS, today_=today)

    # 4) On-hand
    avail = fetch_availabilities()
    df_avail = (
        pl.DataFrame(avail)
        if avail
        else pl.DataFrame(
            schema={"sku": pl.Utf8, "item_name": pl.Utf8, "qty": pl.Float64}
        )
    )
    df_onhand = onhand_total(df_avail)

    # 5) Forecast
    forecast = project_depletion(df_onhand, df_rate, df_items, today_=today)

    # 6) HTML
    html = render_report(forecast, horizon_days=HORIZON_DAYS)

    if args.send_email:
        from core import send_email

        subject = (
            f"📦 Прогноза за изчерпване на наличности – {date.today().isoformat()}"
        )
        send_email(html, subject=subject, insecure=args.insecure)
        print("Email sent.")
    else:
        out_dir = os.path.dirname(__file__)
        out_path = os.path.join(out_dir, "out.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Written: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
