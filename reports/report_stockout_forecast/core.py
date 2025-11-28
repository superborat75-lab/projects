import os
import smtplib
import ssl
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from typing import List, Optional

import polars as pl
import requests
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

# ────────────────────────────────
# ENV
# ────────────────────────────────
load_dotenv()
ERP_BASE_URL = os.getenv("ERP_BASE_URL", "").rstrip("/")
ERP_TOKEN = os.getenv("ERP_TOKEN", "")
TRANS_NAMESPACE = os.getenv("TRANS_NAMESPACE", "healthstore")
# Lead times
LEAD_DELIVERY_DAYS = int(
    os.getenv("LEAD_DELIVERY_DAYS", os.getenv("LEAD_TIME_DAYS", "30"))
)
LEAD_PRODUCTION_DAYS = int(os.getenv("LEAD_PRODUCTION_DAYS", "0"))
# Filters
EXCLUDE_STORES = [
    s.strip() for s in os.getenv("ERP_EXCLUDE_STORES", "").split(",") if s.strip()
]
HORIZON_DAYS = int(os.getenv("HORIZON_DAYS", "30"))

if not ERP_BASE_URL or not ERP_TOKEN:
    raise RuntimeError("Missing ERP_BASE_URL or ERP_TOKEN in .env")

# ────────────────────────────────
# Helpers
# ────────────────────────────────


def _to_float(x) -> float:
    try:
        return float(Decimal(str(x)))
    except (InvalidOperation, TypeError, ValueError):
        try:
            return float(x)
        except Exception:
            return 0.0


def _json_get(url: str, params: dict, timeout: int = 60) -> dict:
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _json_post(url: str, payload: dict, timeout: int = 60) -> dict:
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ────────────────────────────────
# Transactions (SO)
# ────────────────────────────────


def fetch_transactions_for_date(for_date: date) -> list[dict]:
    url = f"{ERP_BASE_URL}/api/RPC.{TRANS_NAMESPACE}.API.getTrans"
    params = {"token": ERP_TOKEN, "for_date": for_date.isoformat()}
    body = _json_get(url, params)
    return body.get("data", []) if isinstance(body, dict) else (body or [])


def fetch_transactions_range(start: date, end: date) -> list[dict]:
    out = []
    cur = start
    while cur <= end:
        out.extend(fetch_transactions_for_date(cur))
        cur += timedelta(days=1)
    return out


def transactions_to_polars(transactions: list[dict]) -> pl.DataFrame:
    flat = []
    for t in transactions:
        if str(t.get("type_action", "")).lower() != "so":
            continue
        if (
            str(t.get("status", "")).lower() == "annul"
            or int(t.get("active", 1) or 0) == 0
        ):
            continue
        for r in t.get("rows") or []:
            flat.append(
                {
                    "for_date": (t.get("for_date") or "")[:10],
                    "doc_num": t.get("num") or "",
                    "sku": str(r.get("item_num") or ""),
                    "item_name": r.get("item_nm") or "",
                    "qty": _to_float(r.get("quantity")),
                }
            )
    return (
        pl.DataFrame(flat)
        if flat
        else pl.DataFrame(
            schema={
                "for_date": pl.Utf8,
                "doc_num": pl.Utf8,
                "sku": pl.Utf8,
                "item_name": pl.Utf8,
                "qty": pl.Float64,
            }
        )
    )


# ────────────────────────────────
# Store-out (реално изписване)
# ────────────────────────────────


def fetch_store_out_for_date(for_date: date) -> list[dict]:
    url = f"{ERP_BASE_URL}/api/RPC.common.Api.StoreOut.get?token={ERP_TOKEN}"
    body = _json_post(url, {"data": [{"for_date": for_date.isoformat()}]})
    if isinstance(body, dict):
        if "result" in body:
            return body.get("result") or []
        data = body.get("data")
        if isinstance(data, dict) and "result" in data:
            return data.get("result") or []
    return []


def fetch_store_out_range(start: date, end: date) -> list[dict]:
    out = []
    cur = start
    while cur <= end:
        out.extend(fetch_store_out_for_date(cur))
        cur += timedelta(days=1)
    return out


def store_out_to_polars(store_out: list[dict]) -> pl.DataFrame:
    rows = []
    for sto in store_out:
        for rel in sto.get("rel_trans") or []:
            if str(rel.get("type", "")).lower() == "so":
                rows.append(
                    {
                        "sto_num": sto.get("num"),
                        "sto_date": (sto.get("for_date") or "")[:10],
                        "so_num": rel.get("num"),
                        "so_date": rel.get("for_date"),
                    }
                )
    return (
        pl.DataFrame(rows)
        if rows
        else pl.DataFrame(
            schema={
                "sto_num": pl.Utf8,
                "sto_date": pl.Utf8,
                "so_num": pl.Utf8,
                "so_date": pl.Utf8,
            }
        )
    )


def filter_sales_by_store_out(
    df_sales: pl.DataFrame, df_sto: pl.DataFrame
) -> pl.DataFrame:
    if df_sales.height == 0 or df_sto.height == 0:
        return pl.DataFrame(schema=df_sales.schema)
    valid = df_sto.select("so_num").unique().rename({"so_num": "doc_num"})
    return df_sales.join(valid, on="doc_num", how="inner")


# ────────────────────────────────
# Availabilities + Items
# ────────────────────────────────


def fetch_availabilities(
    *,
    stores: Optional[List[str]] = None,
    skus: Optional[List[str]] = None,
    include_oos: bool = False,
) -> list[dict]:
    url = f"{ERP_BASE_URL}/api/RPC.common.Api.AvailabilitiesByLabels.get?token={ERP_TOKEN}"
    payload = {
        "data": {
            "stores_names": stores or None,
            "skus_codes": skus or None,
            "labels": [],
            "have_availability": (not include_oos),
        }
    }
    root = _json_post(url, payload)
    rows = (root.get("data", {}) or {}).get("result", []) or []

    out = []
    for r in rows:
        if r.get("store_name") in EXCLUDE_STORES:
            continue
        out.append(
            {
                "store_name": r.get("store_name") or "",
                "sku": str(r.get("sku") or "").strip(),
                "item_name": r.get("item_name") or "",
                # нормализирай към qty
                "qty": _to_float(
                    r.get("qty") or r.get("quantity") or r.get("quantity_on_stock") or 0
                ),
            }
        )
    return out


def onhand_total(df_avail: pl.DataFrame) -> pl.DataFrame:
    if df_avail.height == 0:
        return pl.DataFrame(
            schema={"sku": pl.Utf8, "item_name": pl.Utf8, "on_hand": pl.Float64}
        )
    return df_avail.group_by("sku").agg(
        [
            pl.col("qty").sum().alias("on_hand"),
            pl.col("item_name").first().alias("item_name"),
        ]
    )


# ────────────────────────────────
# Items
# ────────────────────────────────


def _fetch_items_page(limit: int = 1000, offset: int = 0) -> dict:
    url = f"{ERP_BASE_URL}/api/RPC.common.Api.Items.get?token={ERP_TOKEN}"
    payload = {"data": [{}], "get_all": 1, "limit": limit, "offset": offset}
    return _json_post(url, payload)


def fetch_items(page_size: int = 1000) -> list[dict]:
    results: list[dict] = []
    offset = 0
    while True:
        root = _fetch_items_page(limit=page_size, offset=offset)
        data = root.get("data", {}) if isinstance(root, dict) else {}
        page = data.get("result", []) if isinstance(data, dict) else []
        if page:
            results.extend(page)
        count = int(data.get("count", len(page)) or 0)
        if count < page_size:
            break
        offset += page_size
    return results


def items_to_polars(items: list) -> pl.DataFrame:
    if not items:
        return pl.DataFrame(schema={"sku": pl.Utf8, "active": pl.Boolean})
    rows = []
    for it in items:
        sku = str(it.get("sku") or "").strip()
        if not sku:
            continue
        status_val = str(it.get("status") or "").strip().lower()
        active = (status_val == "work") if status_val else True
        rows.append({"sku": sku, "active": active})
    return pl.DataFrame(rows).unique("sku")


# ────────────────────────────────
# Rates / Forecast
# ────────────────────────────────


def daily_sales(df_sales: pl.DataFrame) -> pl.DataFrame:
    if df_sales.height == 0:
        return pl.DataFrame(
            schema={"for_date": pl.Utf8, "sku": pl.Utf8, "qty_sold": pl.Float64}
        )
    return df_sales.group_by(["for_date", "sku"]).agg(
        pl.col("qty").sum().alias("qty_sold")
    )


def avg_daily_rate(
    df_daily: pl.DataFrame, window_days: int = 30, today_: Optional[date] = None
) -> pl.DataFrame:
    if df_daily.height == 0:
        return pl.DataFrame(schema={"sku": pl.Utf8, "avg_daily": pl.Float64})
    today_ = today_ or date.today()
    min_date = (today_ - timedelta(days=window_days - 1)).isoformat()
    recent = df_daily.filter(pl.col("for_date") >= min_date)
    if recent.height == 0:
        return pl.DataFrame(schema={"sku": pl.Utf8, "avg_daily": pl.Float64})
    sums = recent.group_by("sku").agg(pl.col("qty_sold").sum().alias("sum_qty"))
    # Average over the full calendar window to account for zero-sale days
    return sums.with_columns(
        (pl.col("sum_qty") / pl.lit(window_days)).alias("avg_daily")
    ).select(["sku", "avg_daily"])


def project_depletion(
    df_onhand: pl.DataFrame,
    df_rate: pl.DataFrame,
    df_items: pl.DataFrame,
    today_: Optional[date] = None,
) -> pl.DataFrame:
    """
    Комбинира наличности + среднодневни продажби и изчислява:
    - days_of_stock (дни до изчерпване)
    - depletion_date (дата на изчерпване)
    - order_date (дата за поръчка)
    - status (urgent / attention / ok)
    """
    today_ = today_ or date.today()
    total_lead = LEAD_DELIVERY_DAYS + LEAD_PRODUCTION_DAYS

    # join: наличности + среднодневни продажби + данни за артикули
    merged = (
        df_onhand.join(df_rate, on="sku", how="left")
        .with_columns(pl.col("avg_daily").fill_null(0.0))
        .join(df_items, on="sku", how="left")
    )

    # само активни артикули (или без флаг -> приемаме активен)
    merged = merged.filter((pl.col("active") == True) | (pl.col("active").is_null()))

    # on_hand > 0
    merged = merged.filter(pl.col("on_hand") > 0)

    # ако avg_daily ~ 0, не искаме безкрайни дни на запас
    EPS = 1e-9

    # 1) дни на запас
    merged = merged.with_columns(
        pl.when(pl.col("avg_daily") <= EPS)
        .then(pl.lit(None))
        .otherwise(pl.col("on_hand") / pl.col("avg_daily"))
        .alias("days_of_stock")
    )

    # 2) дата на изчерпване = today + days_of_stock (float дни)
    merged = merged.with_columns(
        pl.when(pl.col("days_of_stock").is_null())
        .then(pl.lit(None, dtype=pl.Date))
        .otherwise(pl.lit(today_) + (pl.col("days_of_stock") * pl.duration(days=1)))
        .alias("depletion_date")
    )

    # 3) дата за поръчка = дата на изчерпване - общ lead time
    merged = merged.with_columns(
        pl.when(pl.col("depletion_date").is_null())
        .then(pl.lit(None, dtype=pl.Date))
        .otherwise(pl.col("depletion_date") - pl.duration(days=total_lead))
        .alias("order_date")
    )

    # 4) статус според дни на запас
    merged = merged.with_columns(
        pl.when(pl.col("days_of_stock").is_null())
        .then(pl.lit("ok"))
        .when(pl.col("days_of_stock") <= total_lead)
        .then(pl.lit("urgent"))
        .when(pl.col("days_of_stock") <= total_lead + HORIZON_DAYS)
        .then(pl.lit("attention"))
        .otherwise(pl.lit("ok"))
        .alias("status")
    )

    # 5) приоритет за сортиране: urgent (0), attention (1), ok (2)
    merged = merged.with_columns(
        pl.when(pl.col("status") == "urgent")
        .then(pl.lit(0))
        .when(pl.col("status") == "attention")
        .then(pl.lit(1))
        .otherwise(pl.lit(2))
        .alias("_prio")
    )

    # финален изглед за репорта
    return (
        merged.select(
            [
                "sku",
                "item_name",
                "on_hand",
                "avg_daily",
                "days_of_stock",
                "depletion_date",
                "order_date",
                "status",
                "_prio",
            ]
        )
        .sort(["_prio", "order_date", "depletion_date"], nulls_last=True)
        .drop(["_prio"])
    )


# ────────────────────────────────
# HTML render (добавено)
# ────────────────────────────────


def render_report(
    df_forecast: pl.DataFrame,
    *,
    horizon_days: int = HORIZON_DAYS,
    template_dir: Optional[str] = None,
) -> str:
    base_dir = template_dir or os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(base_dir))

    def int_space(value):
        try:
            n = int(round(float(value or 0)))
            return f"{n:,}".replace(",", " ")
        except Exception:
            return str(value)

    def fmt_rate(value):
        try:
            return f"{float(value or 0):.2f}"
        except Exception:
            return "0.00"

    def fmt_int(value):
        try:
            from math import floor

            n = floor(float(value or 0))
            return f"{n}"
        except Exception:
            return "0"

    def fmt_date(value):
        if value is None:
            return "—"
        try:
            from datetime import date as _d
            from datetime import datetime as _dt

            if isinstance(value, str):
                s = value[:10]
                # Expecting YYYY-MM-DD or similar
                try:
                    dt = _dt.strptime(s, "%Y-%m-%d")
                    return dt.strftime("%d.%m.%Y")
                except Exception:
                    # fallback: if already dd.mm.YYYY or other, return as is
                    return s
            if isinstance(value, _dt):
                return value.strftime("%d.%m.%Y")
            if isinstance(value, _d):
                return value.strftime("%d.%m.%Y")
        except Exception:
            pass
        return str(value)

    def days_to_months(value):
        try:
            from math import floor

            v = float(value)
            if v < 0:
                # Treat negative as 0 months for display purposes
                return "0"
            return f"{floor(v / 30)}"
        except Exception:
            return "0"

    env.filters["int_space"] = int_space
    env.filters["fmt_rate"] = fmt_rate
    env.filters["fmt_int"] = fmt_int
    env.filters["fmt_date"] = fmt_date
    env.filters["days_to_months"] = days_to_months

    template = env.get_template("report.html.j2")
    rows = df_forecast.to_dicts()
    counts = {"urgent": 0, "attention": 0, "ok": 0}
    for r in rows:
        s = (r.get("status") or "ok").lower()
        if s in counts:
            counts[s] += 1
        else:
            counts["ok"] += 1
    total = len(rows)
    return template.render(
        forecast=rows,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        horizon_days=horizon_days,
        lead_delivery_days=LEAD_DELIVERY_DAYS,
        lead_production_days=LEAD_PRODUCTION_DAYS,
        lead_total_days=(LEAD_DELIVERY_DAYS + LEAD_PRODUCTION_DAYS),
        count_urgent=counts["urgent"],
        count_attention=counts["attention"],
        count_ok=counts["ok"],
        count_total=total,
    )


def send_email(html: str, *, subject: str, insecure: bool = False) -> None:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER", "")
    pwd = os.getenv("SMTP_PASS", "")
    mail_from = os.getenv("EMAIL_FROM", user)
    to_list = [x.strip() for x in os.getenv("EMAIL_TO", "").split(",") if x.strip()]
    cc_list = [x.strip() for x in os.getenv("EMAIL_CC", "").split(",") if x.strip()]
    bcc_list = [x.strip() for x in os.getenv("EMAIL_BCC", "").split(",") if x.strip()]

    if not to_list:
        raise ValueError("EMAIL_TO is empty")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    # Provide plain-text fallback for clients that do not render HTML (many mobile apps show empty body without it)
    # Create a naive text version by stripping tags and collapsing whitespace.
    try:
        import re as _re

        text_fallback = _re.sub(r"<[^>]+>", " ", html or "")
        text_fallback = _re.sub(r"\s+", " ", text_fallback).strip()
        if not text_fallback:
            text_fallback = "(виж текущата прогноза в HTML изглед)"
    except Exception:
        text_fallback = "(виж текущата прогноза в HTML изглед)"

    msg.set_content(text_fallback, charset="utf-8")
    msg.add_alternative(html, subtype="html", charset="utf-8")

    context = (
        ssl._create_unverified_context() if insecure else ssl.create_default_context()
    )

    with smtplib.SMTP_SSL(host, port, context=context) as server:
        server.login(user, pwd)
        all_recipients = to_list + cc_list + bcc_list
        server.send_message(msg, to_addrs=all_recipients)
