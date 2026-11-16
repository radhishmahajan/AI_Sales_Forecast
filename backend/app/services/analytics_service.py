"""
Sales analytics, product catalog and dashboard KPIs.

Every number comes from the cleaned sales file produced by the pipeline (dataset-derived),
computed with the same ml.eda / ml.analytics functions used for the reports.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services import data_cache
from app.services.storage_service import load_json
from app.utils.errors import NotFoundError, NotReadyError
from ml import config, eda
from ml.utils import read_json, to_json_safe


def _sales_path():
    return config.PROCESSED_DATA_DIR / "cleaned_sales.parquet"


def sales() -> pd.DataFrame:
    try:
        return data_cache.cached(_sales_path(), "sales", lambda: pd.read_parquet(_sales_path()))
    except FileNotFoundError as exc:
        raise NotReadyError() from exc


def _memo(key: str, fn) -> Any:
    try:
        return data_cache.cached(_sales_path(), key, fn)
    except FileNotFoundError as exc:
        raise NotReadyError() from exc


def catalog() -> dict[str, Any]:
    path = config.STORAGE_DIR / "products" / "products.json"
    if not path.exists():
        raise NotReadyError()
    return data_cache.cached(path, "catalog", lambda: read_json(path))


def kpis() -> dict[str, Any]:
    return _memo("kpis", lambda: to_json_safe(eda.sales_kpis(sales())))


def time_series(freq: str) -> list[dict[str, Any]]:
    return _memo(f"ts_{freq}", lambda: to_json_safe(eda.sales_over_time(sales(), freq).to_dict(orient="records")))


def top_products(by: str, n: int) -> list[dict[str, Any]]:
    return _memo(f"top_{by}_{n}", lambda: to_json_safe(eda.top_products(sales(), by, n).to_dict(orient="records")))


def slow_moving(n: int) -> list[dict[str, Any]]:
    return _memo(f"slow_{n}", lambda: to_json_safe(eda.slow_moving_products(sales(), n).to_dict(orient="records")))


def countries(n: int) -> list[dict[str, Any]]:
    return _memo(f"countries_{n}", lambda: to_json_safe(eda.country_summary(sales()).head(n).to_dict(orient="records")))


def time_patterns() -> dict[str, Any]:
    return _memo("patterns", lambda: to_json_safe({
        "day_of_week": eda.day_of_week_pattern(sales()).to_dict(orient="records"),
        "hourly": eda.hourly_pattern(sales()).to_dict(orient="records"),
    }))


def customers() -> dict[str, Any]:
    return _memo("customers", lambda: to_json_safe(eda.customer_summary(sales())))


def variability(limit: int, min_sale_days: int) -> dict[str, Any]:
    def compute() -> dict[str, Any]:
        v = eda.demand_variability(sales(), min_sale_days=min_sale_days)
        counts = v["variability_class"].value_counts().to_dict()
        return to_json_safe({"summary": counts, "products": v.head(limit).to_dict(orient="records"),
                             "scatter": v.sample(n=min(400, len(v)), random_state=42)[["StockCode", "Description", "mean_daily_demand", "cv"]].to_dict(orient="records"),
                             "explanation": "CV = std / mean of daily demand over each product's observation window. "
                                            "> 1 = erratic. Source: dataset-derived."})
    return _memo(f"var_{limit}_{min_sale_days}", compute)


def eda_report() -> dict[str, Any]:
    data = read_json(config.REPORTS_DIR / "02_eda_report.json")
    if data is None:
        raise NotReadyError()
    return data


def abc() -> dict[str, Any]:
    cat = catalog()
    prods = cat["products"]
    curve = [{"rank": p["revenue_rank"], "cumulative_share": p["cumulative_share"], "abc_class": p["abc_class"]}
             for p in prods[:: max(1, len(prods) // 300)]]
    return {"thresholds": cat["abc_thresholds"], "summary": cat["abc_summary"], "curve": curve,
            "top": [{k: p[k] for k in ("StockCode", "Description", "revenue", "cumulative_share", "abc_class")} for p in prods[:20]]}


# --------------------------------------------------------------------------- products
LIST_FIELDS = ("StockCode", "Description", "quantity", "revenue", "revenue_share_pct", "sale_days", "abc_class",
               "cv", "variability_class", "is_forecastable", "last_sale", "last_unit_price")


def list_products(search: str | None, abc_class: str | None, forecastable: bool | None, sort: str,
                  limit: int, offset: int) -> dict[str, Any]:
    prods = catalog()["products"]
    if search:
        s = search.strip().upper()
        prods = [p for p in prods if s in str(p["StockCode"]).upper() or s in str(p.get("Description") or "").upper()]
    if abc_class:
        prods = [p for p in prods if p["abc_class"] == abc_class]
    if forecastable is not None:
        prods = [p for p in prods if bool(p["is_forecastable"]) == forecastable]
    key, reverse = {"revenue": ("revenue", True), "quantity": ("quantity", True), "code": ("StockCode", False),
                    "variability": ("cv", True)}.get(sort, ("revenue", True))
    prods = sorted(prods, key=lambda p: (p.get(key) is None, p.get(key) or 0), reverse=reverse) if key != "StockCode" \
        else sorted(prods, key=lambda p: str(p["StockCode"]))
    return {"total": len(prods), "offset": offset, "limit": limit,
            "items": [{k: p.get(k) for k in LIST_FIELDS} for p in prods[offset: offset + limit]]}


def product_detail(code: str) -> dict[str, Any]:
    code = code.strip()
    match = next((p for p in catalog()["products"] if str(p["StockCode"]) == code), None)
    if match is None:
        raise NotFoundError(f"Product '{code}' does not exist in the cleaned sales data.")
    s = sales()
    ps = s[s["StockCode"].astype(str) == code]
    monthly = ps.set_index("InvoiceDate").resample("MS").agg({"Quantity": "sum", "Revenue": "sum"}).reset_index()
    daily = ps.groupby("Date").agg(quantity=("Quantity", "sum"), revenue=("Revenue", "sum")).reset_index()
    top_countries = ps.groupby("Country")["Revenue"].sum().nlargest(5).round(2).reset_index()
    return to_json_safe({
        "product": match,
        "source": "dataset-derived",
        "monthly": monthly.rename(columns={"InvoiceDate": "month", "Quantity": "quantity", "Revenue": "revenue"}).to_dict(orient="records"),
        "daily": daily.rename(columns={"Date": "date"}).to_dict(orient="records"),
        "top_countries": top_countries.to_dict(orient="records"),
        "customers": int(ps["CustomerID"].nunique()),
        "orders": int(ps["InvoiceNo"].nunique()),
    })


def forecastable_products() -> list[dict[str, Any]]:
    return [{"StockCode": p["StockCode"], "Description": p["Description"], "abc_class": p["abc_class"]}
            for p in catalog()["products"] if p["is_forecastable"]]


def description_of(code: str) -> str | None:
    try:
        return next((p["Description"] for p in catalog()["products"] if str(p["StockCode"]) == code), None)
    except Exception:
        return None


def settings_defaults() -> dict[str, Any]:
    from app.schemas.models import AppSettings
    return load_json(config.STORAGE_DIR / "settings.json", lambda: AppSettings().model_dump(), AppSettings)
