"""Inventory optimisation."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas.models import InventoryRequest, InventoryResult
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.post("/calculate", response_model=InventoryResult, summary="Calculate a recommendation (not saved; use for what-if simulation)")
def calculate(body: InventoryRequest) -> dict:
    return inventory_service.calculate(body.model_dump())


@router.post("/recommendations", response_model=InventoryResult, status_code=201, summary="Calculate and SAVE a recommendation")
def save(body: InventoryRequest) -> dict:
    return inventory_service.save(body.model_dump())


@router.get("/recommendations", summary="Saved recommendations (newest first)")
def recommendations(stock_code: Optional[str] = Query(None, max_length=20), limit: int = Query(100, ge=1, le=5000)) -> list[dict]:
    return inventory_service.recommendations(stock_code, limit)


@router.get("/inputs", summary="Last saved inputs per product")
def inputs() -> dict:
    return inventory_service.saved_inputs()


@router.get("/risk-summary", summary="Inventory status distribution and alerts")
def risk() -> dict:
    return inventory_service.risk_summary()
