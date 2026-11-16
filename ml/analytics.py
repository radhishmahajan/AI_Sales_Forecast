"""
ADVANCED ANALYTICS — ABC analysis and product insights.

ABC analysis (Pareto principle)
-------------------------------
Sort products by revenue (highest first) and compute each product's cumulative share of
total revenue:
    A = products that together make up the first 80% of revenue  (few, very important)
    B = the next 15% (cumulative 80% -> 95%)
    C = the last 5% (many products, small contribution)
Thresholds 80/95 are the common Pareto convention and are configurable (config.ABC_THRESHOLDS).
A product is placed by where its revenue STARTS on the cumulative curve, so the product that
crosses the 80% line is still class A.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml import config
from ml.eda import demand_variability, product_performance
from ml.utils import atomic_write_json, to_json_safe, utc_now_iso


def abc_analysis(sales: pd.DataFrame, thresholds: tuple[float, float] = config.ABC_THRESHOLDS) -> pd.DataFrame:
    a_lim, b_lim = thresholds
    perf = product_performance(sales).sort_values("revenue", ascending=False).reset_index(drop=True)
    total = perf["revenue"].sum()
    perf["cumulative_share"] = perf["revenue"].cumsum() / total
    start_share = perf["cumulative_share"] - perf["revenue"] / total
    perf["abc_class"] = np.select([start_share < a_lim, start_share < b_lim], ["A", "B"], default="C")
    perf["revenue_rank"] = np.arange(1, len(perf) + 1)
    return perf


def abc_summary(abc: pd.DataFrame) -> list[dict[str, Any]]:
    total_rev = abc["revenue"].sum()
    out = []
    for cls in ("A", "B", "C"):
        sub = abc[abc["abc_class"] == cls]
        out.append({"class": cls, "products": int(len(sub)), "product_share_pct": round(100 * len(sub) / len(abc), 2),
                    "revenue": round(float(sub["revenue"].sum()), 2),
                    "revenue_share_pct": round(100 * float(sub["revenue"].sum()) / total_rev, 2)})
    return out


def build_product_catalog(sales: pd.DataFrame, modelled_products: list[str]) -> pd.DataFrame:
    """Catalog used by the API: performance + ABC class + variability + modelled flag."""
    abc = abc_analysis(sales)
    var = demand_variability(sales)[["StockCode", "mean_daily_demand", "std_daily_demand", "cv", "variability_class", "sale_day_ratio"]]
    cat = abc.merge(var, on="StockCode", how="left")
    last_price = sales.sort_values("InvoiceDate").groupby("StockCode", observed=True)["UnitPrice"].last()
    cat["last_unit_price"] = cat["StockCode"].map(last_price)
    modelled = set(map(str, modelled_products))
    cat["StockCode"] = cat["StockCode"].astype(str)
    cat["is_forecastable"] = cat["StockCode"].isin(modelled)
    return cat


def run(sales: pd.DataFrame, modelled_products: list[str]) -> dict[str, Any]:
    cat = build_product_catalog(sales, modelled_products)
    records = to_json_safe(cat.to_dict(orient="records"))
    payload = {
        "generated_at": utc_now_iso(),
        "source": "dataset-derived (cleaned SALE rows)",
        "abc_thresholds": {"A_up_to_cumulative_share": config.ABC_THRESHOLDS[0], "B_up_to_cumulative_share": config.ABC_THRESHOLDS[1]},
        "abc_summary": abc_summary(cat),
        "products": records,
    }
    config.STORAGE_DIR.joinpath("products").mkdir(parents=True, exist_ok=True)
    atomic_write_json(config.STORAGE_DIR / "products" / "products.json", payload)
    atomic_write_json(config.REPORTS_DIR / "abc_analysis.json", {k: v for k, v in payload.items() if k != "products"})
    return payload
