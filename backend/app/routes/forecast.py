"""Demand forecasting and forecast history."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas.models import ForecastRequest, ForecastResponse
from app.services import forecast_service

router = APIRouter(prefix="/forecast", tags=["Forecasting"])


@router.post("", response_model=ForecastResponse, summary="Generate (and save) a 7/14/30-day recursive forecast")
def create(body: ForecastRequest) -> dict:
    return forecast_service.generate(body.stock_code, body.horizon_days, save=True)


@router.get("/history", summary="Saved forecast runs (newest first)")
def history(stock_code: Optional[str] = Query(None, max_length=20), limit: int = Query(50, ge=1, le=1000)) -> list[dict]:
    return forecast_service.history(stock_code, limit)


@router.get("/history/{record_id}", summary="A saved forecast run")
def record(record_id: str) -> dict:
    return forecast_service.record(record_id)
