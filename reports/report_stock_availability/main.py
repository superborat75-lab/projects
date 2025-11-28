import argparse
import os
from datetime import date, datetime

import polars as pl
from dotenv import load_dotenv
from premailer import transform as inline_css

from core import (
    HTML_TMPL,
    add_status,
    fetch_labels,
    fmt_money,
    fmt_qty,
    send_email,
    summary_cards,
    to_df,
)

load_dotenv()


def env_list(key: str):
    val = os.getenv(key)
    if not val:
        return None
    val = val.strip()
    if val in ("*", "ALL", "all", "All"):
        return None
    items = [x.strip() for x in val.split(",") if x.strip()]
    return items or None


def apply_filters(df: pl.DataFrame, args: argparse.Namespace) -> pl.DataFrame:
    out = df

    # Филтър по магазин
    if args.store:
        wanted = []
        for s in args.store:
            wanted.extend([x.strip() for x in s.split(",") if x.strip()])
        lowered = {w.lower() for w in wanted}
        if wanted and not (lowered & {"*", "all", "всички"}):
            out = out.filter(pl.col("store_name").is_in(wanted))

    # Филтър по SKU
    if args.sku:
        wanted = []
        for s in args.sku:
            wanted.extend([x.strip() for x in s.split(",") if x.strip()])
        if wanted:
            out = out.filter(pl.col("sku").is_in(wanted))

    # Филтър по бранд (substring, case-insensitive)
    if args.brand:
        wanted = []
        for s in args.brand:
            wanted.extend([x.strip() for x in s.split(",") if x.strip()])
        if wanted:
            pat = "|".join([w.replace(" ", ".*") for w in wanted])
            out = out.filter(
                pl.col("brand").str.to_lowercase().str.contains(pat.lower())
            )

    # Минимално количество
    if args.min_qty is not None:
        out = out.filter(pl.col("qty") >= float(args.min_qty))

    # Ако не е включено include-oos – махаме qty <= 0
    if not args.include_oos:
        out = out.filter(pl.col("qty") > 0)

    return out


def sort_df(df: pl.DataFrame, sort_by: str, desc: bool) -> pl.DataFrame:
    key_map = {
        "sku": "sku",
        "name": "item_name",
        "expiry": "expiry",
        "qty": "qty",
    }
    col = key_map.get(sort_by, "sku")
    return df.sort(by=[col, "sku", "item_name"], descending=[desc, desc, desc])


def main():
    parser = argparse.ArgumentParser(
        description="Stock availability by batches → HTML (+ optional email)"
    )
    parser.add_argument(
        "--include-oos", action="store_true", help="Включи и партиди с qty=0"
    )
    parser.add_argument(
        "--send-email", action="store_true", help="Изпрати резултата по email"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не изпращай email, само генерирай HTML (ползва се с --send-email за тест)",
    )
    parser.add_argument(
        "--store",
        action="append",
        help="Филтър по магазин (може многократно, може списък разделен със запетая)",
    )
    parser.add_argument(
        "--sku",
        action="append",
        help="Филтър по SKU (точни кодове, може многократно, може със запетая)",
    )
    parser.add_argument(
        "--brand",
        action="append",
        help="Филтър по марка (substring, case-insensitive, може многократно)",
    )
    parser.add_argument(
        "--min-qty",
        type=float,
        help="Минимално количество (филтър за qty)",
    )
    parser.add_argument(
        "--crit-days", type=int, default=30, help="Критичен праг за дни до годност"
    )
    parser.add_argument(
        "--warn-days",
        type=int,
        default=60,
        help="Предупредителен праг за дни до годност",
    )
    parser.add_argument(
        "--sort-by",
        choices=["sku", "name", "expiry", "qty"],
        default="sku",
        help="Колона за сортиране",
    )
    parser.add_argument("--desc", action="store_true", help="Обърнат ред на сортиране")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="По-слаб TLS за SMTP (ако мейл сървърът е развален)",
    )

    args = parser.parse_args()

    base = os.getenv("ERP_BASE_URL", "").strip()
    token = os.getenv("ERP_TOKEN", "").strip()
    if not base or not token:
        raise RuntimeError("Missing ERP_BASE_URL or ERP_TOKEN in .env")

    stores = env_list("STORES")
    skus = env_list("SKUS")

    # semantics на STORES: ако има STORES и няма --store → STORES е blacklist
    exclude_stores = stores if (stores and not args.store) else None

    rows = fetch_labels(
        base,
        token,
        stores=None if exclude_stores else (stores if not args.store else None),
        skus=skus if not args.sku else None,
        include_oos=args.include_oos,
    )

    df = to_df(rows)

    if exclude_stores:
        df = df.filter(~pl.col("store_name").is_in(exclude_stores))

    df = add_status(df, crit_days=args.crit_days, warn_days=args.warn_days)
    df = apply_filters(df, args)
    df = sort_df(df, sort_by=args.sort_by, desc=args.desc)

    groups = []
    if df.height:
        for store in df.select(pl.col("store_name")).unique().to_series().to_list():
            part = df.filter(pl.col("store_name") == store)
            group_rows = part.to_dicts()
            group_qty = part.select(pl.col("qty").sum()).item()
            group_cost = (
                part.select(pl.col("inventory_value").sum()).item()
                if "inventory_value" in part.columns
                else 0.0
            )
            group_sales = (
                part.select(pl.col("sales_value").sum()).item()
                if "sales_value" in part.columns
                else 0.0
            )
            groups.append((store, group_rows, group_qty, group_cost, group_sales))

    cards = summary_cards(df)
    title = f"Складови наличности по партиди – {date.today().isoformat()}"

    html_raw = HTML_TMPL.render(
        title=title,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        cards=cards,
        groups=groups,
        fmt_qty=fmt_qty,
        fmt_money=fmt_money,
    )
    html = inline_css(html_raw)

    subject = f"Наличности по партиди – {date.today().isoformat()}"

    # --- Първо винаги записваме HTML локално ---
    out_path = os.path.join(os.path.dirname(__file__), "out.html")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML saved to {out_path}")
    except Exception as e:
        print(f"WARN: failed to write out.html: {e}")

    # --- После опитваме да изпратим email (ако е поискано) ---
    if args.send_email and not args.dry_run:
        try:
            send_email(html, subject=subject, insecure=args.insecure)
            print("OK: email sent")
        except Exception as e:
            # Ключовото: НЕ чупим процеса, само логваме.
            print(f"WARN: failed to send email: {e!r}")

    # Никакъв raise тук → exit code 0, service не пада.


if __name__ == "__main__":
    main()
