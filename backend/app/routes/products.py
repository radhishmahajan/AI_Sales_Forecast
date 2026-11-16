"""Product list and product details."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Path, Query

from app.services import analytics_service

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", summary="Search, filter and page through products")
def list_products(search: Optional[str] = Query(None, max_length=60), abc_class: Optional[Literal["A", "B", "C"]] = None,
                  forecastable: Optional[bool] = None,
                  sort: Literal["revenue", "quantity", "code", "variability"] = "revenue",
                  limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    return analytics_service.list_products(search, abc_class, forecastable, sort, limit, offset)


@router.get("/forecastable", summary="Products available for forecasting")
def forecastable() -> list[dict]:
    return analytics_service.forecastable_products()


@router.get("/{stock_code}", summary="Product details, history, ABC class and variability")
def detail(stock_code: str = Path(..., min_length=1, max_length=20)) -> dict:
    return analytics_service.product_detail(stock_code)
