import os
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional

import polars as pl
import requests
from babel.numbers import format_decimal
from dotenv import load_dotenv
from jinja2 import Template

load_dotenv()

HTML_TMPL = Template(
    """
<!doctype html>
<html lang="bg">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    body { font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #222; }
    h1 { font-size: 20px; margin: 0 0 8px 0; }
    .meta { color: #666; font-size: 12px; margin-bottom: 16px; }
    .cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0 20px; }
    .card { border: 1px solid #ddd; border-radius: 6px; padding: 10px 12px; min-width: 140px; background:#fafafa; }
    .card .label { color:#777; font-size:12px; }
    .card .value { font-size:18px; font-weight:600; }
    .group { margin-bottom: 26px; }
    .group h2 { font-size: 16px; margin: 0 0 8px 0; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border: 1px solid #e0e0e0; padding: 4px 6px; vertical-align: top; }
    th { background: #f5f5f5; text-align: left; }
    .qty { text-align: right; font-variant-numeric: tabular-nums; }
    .status-CRIT { background: #ffe5e5; }
    .status-WARN { background: #fff8e5; }
    .status-NOEXP { background: #eef5ff; }
    .badge { display:inline-block; padding:2px 6px; border-radius: 4px; font-size: 12px; }
    .badge.CRIT { background:#dc3545; color:#fff; }
    .badge.WARN { background:#fd7e14; color:#fff; }
    .badge.NOEXP { background:#0d6efd; color:#fff; }
    .badge.OK { background:#198754; color:#fff; }
    .muted { color:#777; }
    tbody tr:nth-child(odd) { background: #fbfbfb; }
    tbody tr:hover { background: #f6faff; }
    th { position: sticky; top: 0; z-index: 1; }
    table { border-radius: 6px; overflow: hidden; }
  </style>
</head>
<body>
  <h1>{{ title | e }}</h1>
  <div class="meta">Генериран: {{ generated_at | e }}</div>

  <div class="cards">
    <div class="card"><div class="label">SKU</div><div class="value">{{ cards.total_skus }}</div></div>
    <div class="card"><div class="label">Партиди</div><div class="value">{{ cards.total_lots }}</div></div>
    <div class="card"><div class="label">Количество</div><div class="value">{{ cards.total_qty }}</div></div>
    <div class="card"><div class="label">Стойност (доставна)</div><div class="value">{{ cards.total_cost_value }}</div></div>
    <div class="card"><div class="label">Стойност (продажна)</div><div class="value">{{ cards.total_sales_value }}</div></div>
    <div class="card"><div class="label"><=30 дни</div><div class="value">{{ cards.exp_le_30 }}</div></div>
    <div class="card"><div class="label"><=60 дни</div><div class="value">{{ cards.exp_le_60 }}</div></div>
    <div class="card"><div class="label">Без годност</div><div class="value">{{ cards.missing_exp }}</div></div>
  </div>

  {% if groups and groups|length > 0 %}
    {% for store_name, rows, group_qty, group_cost, group_sales in groups %}
    <div class="group">
      <h2>{{ store_name | e }} <span class="muted">— Общо: {{ fmt_qty(group_qty) }} бр · {{ fmt_money(group_cost) }} (доставна) · {{ fmt_money(group_sales) }} (продажна)</span></h2>
      <table>
        <thead>
          <tr>
            <th>Код</th>
            <th>Артикул</th>
            <th>Марка</th>
            <th>Партида</th>
            <th>Годност</th>
            <th class="qty">Наличност</th>
            <th>Статус</th>
            <th class="qty">Цена/бр (доставна)</th>
            <th class="qty">Стойност (доставна)</th>
            <th class="qty">Цена/бр (продажна)</th>
            <th class="qty">Стойност (продажна)</th>
          </tr>
        </thead>
        <tbody>
          {% for r in rows %}
          <tr class="status-{{ r.status }}">
            <td>{{ r.sku | e }}</td>
            <td>{{ r.item_name | e }}</td>
            <td>{{ (r.brand or '') | e }}</td>
            <td>{{ r.lot | e }}</td>
            <td>{{ r.expiry or '' }}</td>
            <td class="qty">{{ fmt_qty(r.qty) if r.qty is not none else '' }}</td>
            <td><span class="badge {{ r.status }}">{{ r.status }}</span></td>
            <td class="qty">{{ fmt_money(r.unit_cost) if r.unit_cost is not none else '' }}</td>
            <td class="qty">{{ fmt_money(r.inventory_value) if r.inventory_value is not none else '' }}</td>
            <td class="qty">{{ fmt_money(r.unit_price) if r.unit_price is not none else '' }}</td>
            <td class="qty">{{ fmt_money(r.sales_value) if r.sales_value is not none else '' }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% endfor %}
  {% else %}
    <p class="muted">Няма данни за показване.</p>
  {% endif %}
</body>
</html>
"""
)


def build_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def post_rpc(url: str, token: str, payload: dict, timeout: int = 60) -> dict:
    r = requests.post(f"{url}?token={token}", json={"data": payload}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def to_decimal(x) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def fmt_qty(x) -> str:
    try:
        return format_decimal(float(x or 0), locale="bg_BG", format="#,##0")
    except Exception:
        return "0"


def fmt_money(x) -> str:
    try:
        return format_decimal(float(x or 0), locale="bg_BG", format="#,##0.00")
    except Exception:
        return "0.00"


UNIT_PRICE = float(os.getenv("UNIT_PRICE", "0") or 0.0)


def norm_label(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return str(x)
    except Exception:
        return ""


def parse_expiry_from_params(params: Any) -> Optional[date]:
    if params is None:
        return None
    if isinstance(params, list):
        for obj in params:
            if not isinstance(obj, dict):
                continue
            for key in ("EXPIRATION", "expiration", "expiry", "expire"):
                if key in obj:
                    try:
                        return date.fromisoformat(obj[key][:10])
                    except Exception:
                        pass
        return None
    if not isinstance(params, dict):
        return None
    for key in ("EXPIRATION", "expiration", "expiry", "expire"):
        if key in params:
            try:
                return date.fromisoformat(params[key][:10])
            except Exception:
                pass
    return None


def unit_cost_from_expiry(expiry: str | None) -> float:
    """Взима година от expiry (ISO низ 'YYYY-MM-DD') и връща доставна цена според .env.

    Търси INVENTORY_COST_<YEAR>, ако няма – INVENTORY_COST_DEFAULT.
    При липса на всичко → 0.0.
    """
    key = None
    if expiry:
        year = str(expiry)[:4]
        if year.isdigit():
            key = f"INVENTORY_COST_{year}"
    raw = os.getenv(key) if key else None
    if raw is None:
        raw = os.getenv("INVENTORY_COST_DEFAULT")
    if raw is None:
        return 0.0
    try:
        return float(to_decimal(raw))
    except Exception:
        return 0.0


def fetch_item_brands(base_url: str, token: str, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    url = f"{base_url}/api/RPC.common.Api.Items.get?token={token}"
    payload = {"data": [{"id": i} for i in item_ids]}
    response = requests.post(url, json=payload, timeout=60)
    if not response.ok:
        return {}
    body = response.json() or {}
    data = body.get("data", {}).get("result", body.get("result", [])) or []
    out: dict[int, str] = {}
    for item in data:
        obj = item.get("item") if isinstance(item, dict) else None
        obj = obj if isinstance(obj, dict) else item
        item_id = obj.get("id") if isinstance(obj, dict) else None
        if not isinstance(item_id, int):
            continue
        brand = obj.get("brand")
        if not brand:
            continue
        name_multilang = (
            brand.get("name_multilang") if isinstance(brand, dict) else None
        )
        bg_name = name_multilang.get("bg") if isinstance(name_multilang, dict) else None
        brand_name = (
            bg_name or brand.get("name") or brand.get("title") or brand.get("code")
        )
        if (
            isinstance(item_id, int)
            and isinstance(brand_name, str)
            and brand_name.strip()
        ):
            out[item_id] = brand_name.strip()
    return out


def fetch_labels(
    base: str,
    token: str,
    *,
    stores: List[str] | None,
    skus: List[str] | None,
    include_oos: bool,
) -> List[dict]:
    payload = {
        "stores_names": stores or None,
        "skus_codes": skus or None,
        "labels": [],
        "have_availability": not include_oos,
    }
    url = build_url(base, "/api/RPC.common.Api.AvailabilitiesByLabels.get")
    resp = post_rpc(url, token, payload)

    rows = resp.get("data", {}).get("result", [])
    out: list[dict] = []

    for r in rows:
        out.append(
            {
                "store_id": r.get("store_id"),
                "store_name": r.get("store_name"),
                "sku": str(r.get("sku") or "").strip(),
                "item_id": r.get("item_id"),
                "item_name": r.get("item_name") or "",
                # ТУК: label го третираме като "етикет" (стринг), не като dict
                "lot": norm_label(r.get("label")),
                # expiry си го вадим от params/raw_params, които са dict/json
                "expiry": parse_expiry_from_params(
                    r.get("params") or r.get("raw_params")
                ),
                "qty": to_decimal(r.get("quantity") or r.get("quantity_on_stock") or 0),
            }
        )

    # Извличаме брандовете по item_id
    item_ids = sorted(
        {
            int(r["item_id"])
            for r in out
            if r.get("item_id") is not None and str(r["item_id"]).strip().isdigit()
        }
    )
    item_brand_map = fetch_item_brands(base, token, item_ids)
    for r in out:
        key = r.get("item_id")
        key_int = int(key) if key is not None and str(key).strip().isdigit() else None
        r["brand"] = item_brand_map.get(key_int) or item_brand_map.get(key) or ""

    return out


def to_df(rows: list[dict]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame({})
    # Нормализираме expiry до ISO низ
    for r in rows:
        d = r.get("expiry")
        r["expiry"] = d.isoformat() if isinstance(d, date) else str(d) if d else None

    df = pl.DataFrame(rows)

    # qty → float, помощна колона за сортиране по expiry
    df = df.with_columns(
        pl.col("qty").cast(pl.Float64),
        pl.coalesce([pl.col("expiry"), pl.lit("9999-12-31")]).alias("_exp_sort"),
    )

    # Доставна цена по година на expiry
    df = df.with_columns(
        pl.col("expiry").map_elements(unit_cost_from_expiry).alias("unit_cost")
    )

    # Стойности: по доставна и по продажна
    df = df.with_columns(
        (pl.col("qty") * pl.col("unit_cost")).alias("inventory_value"),
        pl.lit(UNIT_PRICE).alias("unit_price"),
        (pl.col("qty") * pl.lit(UNIT_PRICE)).alias("sales_value"),
    )

    return df.sort(by=["_exp_sort", "qty"], descending=[False, True]).drop("_exp_sort")


def add_status(
    df: pl.DataFrame, *, crit_days: int = 30, warn_days: int = 60
) -> pl.DataFrame:
    exp_date = pl.col("expiry").str.to_date(format="%Y-%m-%d", strict=False)
    delta_days = (exp_date - pl.lit(date.today())).dt.total_days()

    status_expr = (
        pl.when(pl.col("qty") <= 0)
        .then(pl.lit("OK"))
        .when(exp_date.is_null())
        .then(pl.lit("NOEXP"))
        .when(delta_days <= pl.lit(crit_days))
        .then(pl.lit("CRIT"))
        .when(delta_days <= pl.lit(warn_days))
        .then(pl.lit("WARN"))
        .otherwise(pl.lit("OK"))
    )

    return df.with_columns(status_expr.alias("status"))


def summary_cards(df: pl.DataFrame) -> dict:
    if not df.height:
        total_qty = 0.0
        total_cost = 0.0
        total_sales = 0.0
    else:
        total_qty = df.select(pl.col("qty").sum()).item() or 0.0
        total_cost = (
            df.select(pl.col("inventory_value").sum()).item()
            if "inventory_value" in df.columns
            else 0.0
        )
        total_sales = (
            df.select(pl.col("sales_value").sum()).item()
            if "sales_value" in df.columns
            else 0.0
        )

    return {
        "total_skus": df.select(pl.col("sku").n_unique()).item() if df.height else 0,
        "total_lots": df.height,
        "total_qty": format_decimal(total_qty, locale="bg_BG", format="#,##0"),
        "total_cost_value": fmt_money(total_cost),
        "total_sales_value": fmt_money(total_sales),
        "exp_le_30": df.filter(pl.col("status") == "CRIT").height,
        "exp_le_60": df.filter(pl.col("status") == "WARN").height,
        "missing_exp": df.filter(pl.col("status") == "NOEXP").height,
    }


def send_email(html: str, *, subject: str, insecure: bool = False) -> None:
    """
    Изпраща HTML репорта по email.

    Работи с твоя .env схема:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_USE_TLS
      EMAIL_FROM, EMAIL_TO, EMAIL_CC, EMAIL_BCC
    """

    import os
    import smtplib
    import ssl
    from email.message import EmailMessage

    # --- SMTP базова конфигурация ---
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = (
        os.getenv("SMTP_PASS") or os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PWD")
    )

    # --- получатели ---
    recipients = []

    for key in ("EMAIL_TO", "EMAIL_CC", "EMAIL_BCC", "RECIPIENTS"):
        val = os.getenv(key)
        if val:
            parts = [x.strip() for x in val.split(",") if x.strip()]
            recipients.extend(parts)

    recipients = sorted(set(recipients))  # премахване на дубли

    # --- подател ---
    sender = os.getenv("EMAIL_FROM") or smtp_user

    # --- валидация ---
    if not smtp_host or not smtp_user or not smtp_password or not recipients:
        raise RuntimeError(
            "Missing SMTP configuration (SMTP_HOST, USER, PASS, EMAIL_*). Check your .env"
        )

    # --- подготвяме email ---
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content("HTML report attached.")
    msg.add_alternative(html, subtype="html")

    # --- debug ---
    print(
        f"Connecting to SMTP_SSL {smtp_host}:{smtp_port} as {smtp_user} ...", flush=True
    )

    # --- SSL / insecure context ---
    context = (
        ssl._create_unverified_context() if insecure else ssl.create_default_context()
    )

    # --- ВАЖНО: Port 465 = implicit SSL ---
    try:
        with smtplib.SMTP_SSL(
            smtp_host, smtp_port, timeout=10, context=context
        ) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        print("Email sent OK", flush=True)

    except Exception as e:
        # Нека api1.py да реши какво да прави — тук само логваме
        raise RuntimeError(f"SMTP send failed: {e!r}")


def env_list(key: str) -> List[str] | None:
    val = os.getenv(key)
    return [x.strip() for x in val.split(",") if x.strip()] if val else None
