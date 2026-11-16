"""EDA analytics and dashboard KPIs (all dataset-derived)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.services import analytics_service, inventory_service, model_service

router = APIRouter(tags=["Analytics"])


@router.get("/dashboard", summary="Main dashboard: KPIs, trends, top products, forecast & inventory summaries")
def dashboard() -> dict:
    return {
        "kpis": analytics_service.kpis(),
        "monthly": analytics_service.time_series("M"),
        "weekly": analytics_service.time_series("W"),
        "top_products": analytics_service.top_products("quantity", 10),
        "model": model_service.summary_or_none(),
        "inventory_risk": inventory_service.risk_summary(),
        "abc_summary": analytics_service.catalog()["abc_summary"],
        "source": "dataset-derived KPIs; model metrics calculated on held-out data; inventory based on user-entered stock",
    }


@router.get("/analytics/kpis", summary="Headline KPIs")
def kpis() -> dict:
    return analytics_service.kpis()


@router.get("/analytics/sales", summary="Sales time series")
def sales(freq: Literal["D", "W", "M"] = Query("D", description="D = daily, W = weekly, M = monthly")) -> list[dict]:
    return analytics_service.time_series(freq)


@router.get("/analytics/top-products", summary="Best-selling products")
def top_products(by: Literal["quantity", "revenue"] = "quantity", n: int = Query(10, ge=1, le=100)) -> list[dict]:
    return analytics_service.top_products(by, n)


@router.get("/analytics/slow-moving", summary="Least-selling products")
def slow_moving(n: int = Query(10, ge=1, le=100)) -> list[dict]:
    return analytics_service.slow_moving(n)


@router.get("/analytics/countries", summary="Country-wise revenue and orders")
def countries(n: int = Query(15, ge=1, le=50)) -> list[dict]:
    return analytics_service.countries(n)


@router.get("/analytics/time-patterns", summary="Day-of-week and hourly patterns")
def time_patterns() -> dict:
    return analytics_service.time_patterns()


@router.get("/analytics/customers", summary="Customer purchasing patterns")
def customers() -> dict:
    return analytics_service.customers()


@router.get("/analytics/variability", summary="Product demand variability (CV)")
def variability(limit: int = Query(50, ge=1, le=500), min_sale_days: int = Query(20, ge=1, le=300)) -> dict:
    return analytics_service.variability(limit, min_sale_days)


@router.get("/analytics/abc", summary="ABC analysis")
def abc() -> dict:
    return analytics_service.abc()


@router.get("/analytics/eda", summary="Stage 2 EDA report with chart interpretations")
def eda() -> dict:
    return analytics_service.eda_report()
