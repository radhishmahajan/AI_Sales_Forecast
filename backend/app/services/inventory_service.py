"""
Inventory recommendations: combine the 30-day model forecast + real demand variability with the
user's operational inputs, and keep a history of saved recommendations.

Storage:
    storage/inventory/recommendations.json   {"records": [...]} append-only history (JSON)
    storage/inventory/inventory_inputs.json  last inputs used per product (to pre-fill the form)
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from app.schemas.models import StoredInventoryRecord, StoredRecords
from app.services import analytics_service, forecast_service
from app.services.storage_service import append_json_record, load_json, save_json, storage_path
from ml import config, forecasting, inventory
from ml.inventory import InventoryInputs
from ml.utils import to_json_safe

INVENTORY_HORIZON = 30


def _recs_path():
    return storage_path("inventory", "recommendations.json")


def _inputs_path():
    return storage_path("inventory", "inventory_inputs.json")


def calculate(req: dict[str, Any]) -> dict[str, Any]:
    inp = InventoryInputs(**req)
    inventory.validate_inputs(inp)
    fc = forecast_service.generate(inp.stock_code, INVENTORY_HORIZON, save=False)
    panel = forecast_service._panel()
    hist = panel[panel["StockCode"] == inp.stock_code]
    hist = forecasting.extend_history_to(hist, pd.Timestamp(fc["forecast_origin"]), forecast_service._calendar())
    var = inventory.demand_variability(hist)
    result = inventory.calculate_inventory(inp, [d["predicted_demand"] for d in fc["daily"]], var, INVENTORY_HORIZON)
    result.update({
        "stock_code": inp.stock_code,
        "description": analytics_service.description_of(inp.stock_code),
        "forecast_origin": fc["forecast_origin"],
        "model_name": fc["model_name"],
        "forecast_daily": fc["daily"],
    })
    return to_json_safe(result)


def save(req: dict[str, Any]) -> dict[str, Any]:
    result = calculate(req)
    stored = {k: v for k, v in result.items() if k != "forecast_daily"}
    rec = append_json_record(_recs_path(), stored, StoredRecords, StoredInventoryRecord)
    inputs = load_json(_inputs_path(), dict)
    inputs[req["stock_code"]] = {**req, "saved_at": rec["created_at"]}
    save_json(_inputs_path(), inputs)
    return {**result, "record_id": rec["record_id"], "created_at": rec["created_at"]}


def recommendations(stock_code: str | None, limit: int) -> list[dict[str, Any]]:
    recs = load_json(_recs_path(), lambda: {"records": []}, StoredRecords)["records"]
    if stock_code:
        recs = [r for r in recs if r["stock_code"] == stock_code]
    return list(reversed(recs))[:limit]


def saved_inputs() -> dict[str, Any]:
    return load_json(_inputs_path(), dict)


def risk_summary() -> dict[str, Any]:
    """Latest saved recommendation per product -> status distribution + alerts.

    Based ONLY on stock levels the user entered; products without saved inputs are not assessed.
    """
    recs = load_json(_recs_path(), lambda: {"records": []}, StoredRecords)["records"]
    latest: dict[str, dict[str, Any]] = {}
    for r in recs:  # records are in chronological order -> later ones overwrite earlier ones
        latest[r["stock_code"]] = r
    items = list(latest.values())
    counts = Counter(r["status"] for r in items)
    order = {s: i for i, s in enumerate(inventory.STATUS_ORDER)}
    items.sort(key=lambda r: (order.get(r["status"], 9), -r.get("suggested_order_quantity", 0)))
    alerts = [{"stock_code": r["stock_code"], "description": r.get("description"), **a, "created_at": r["created_at"]}
              for r in items for a in r.get("alerts", [])]
    return {
        "assessed_products": len(items),
        "status_counts": {s: counts.get(s, 0) for s in inventory.STATUS_ORDER},
        "products": [{k: r.get(k) for k in ("stock_code", "description", "status", "current_stock", "inputs",
                                            "reorder_point", "safety_stock", "target_stock", "suggested_order_quantity",
                                            "days_of_cover", "created_at", "record_id")} for r in items],
        "alerts": alerts,
        "note": "Risk is assessed only for products where you saved current stock and lead time (user-entered); "
                "the UCI dataset has no stock levels.",
        "overstock_rule": f"stock > {config.OVERSTOCK_FACTOR:g} x target stock",
    }
