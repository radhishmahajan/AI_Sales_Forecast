"""
INVENTORY OPTIMIZATION ENGINE.

IMPORTANT: the UCI dataset has NO stock-on-hand, lead time or stockout history. These
recommendations combine
    * real historical sales (dataset-derived) and model forecasts (model-predicted), with
    * current stock, supplier lead time, service level, MOQ, pack size and capacity that the
      USER ENTERS (user-entered).
They are recommendations, not measurements of historical stock.

Policy: periodic review, order-up-to level ("target stock")
------------------------------------------------------------
d    = average daily demand (calendar days) = mean of the model forecast over the forecast horizon
sd   = standard deviation of DAILY demand over the last 84 calendar days of real history
Z    = standard normal quantile of the service level (95% -> 1.645)
L    = supplier lead time in days, R = review period in days (how often stock is reviewed; default 7)

Safety stock      SS  = Z x sd x sqrt(L)
Reorder point     ROP = d x L + SS
Target stock      T   = d x (L + R) + SS       (covers the lead time AND the time until the next review)
Order quantity    Q   = max(0, T - current stock), then MOQ, pack-size rounding and capacity limits

Assumptions behind SS = Z x sd x sqrt(L): daily demands are independent and identically
distributed, so the standard deviation of demand over L days is sd x sqrt(L); the lead time
itself is fixed (no lead-time variability). Daily retail demand is bursty, so this is an
approximation; it is the standard textbook formula requested in the project brief.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from ml import config

STATUS_ORDER = ("Critical Stock", "Low Stock", "Healthy Stock", "Overstocked")


class InventoryInputError(ValueError):
    """Raised when user-entered inventory inputs are invalid."""


@dataclass
class InventoryInputs:
    stock_code: str
    current_stock: float
    lead_time_days: int
    service_level: float = config.DEFAULT_SERVICE_LEVEL
    review_period_days: int = config.DEFAULT_REVIEW_PERIOD_DAYS
    min_order_qty: int | None = None
    pack_size: int | None = None
    max_capacity: int | None = None


def validate_inputs(inp: InventoryInputs) -> None:
    errors = []
    if inp.current_stock is None or not np.isfinite(inp.current_stock) or inp.current_stock < 0:
        errors.append("Current stock must be 0 or more.")
    if not isinstance(inp.lead_time_days, (int, np.integer)) or not (1 <= inp.lead_time_days <= 365):
        errors.append("Lead time must be a whole number of days between 1 and 365.")
    if inp.service_level is None or not (0.5 <= inp.service_level <= 0.999):
        errors.append("Service level must be between 0.50 and 0.999 (e.g. 0.95 for 95%).")
    if not isinstance(inp.review_period_days, (int, np.integer)) or not (1 <= inp.review_period_days <= 90):
        errors.append("Review period must be between 1 and 90 days.")
    if inp.min_order_qty is not None and inp.min_order_qty < 0:
        errors.append("Minimum order quantity cannot be negative.")
    if inp.pack_size is not None and inp.pack_size < 1:
        errors.append("Pack size must be at least 1.")
    if inp.max_capacity is not None and inp.max_capacity <= 0:
        errors.append("Maximum storage capacity must be greater than 0.")
    if errors:
        raise InventoryInputError(" ".join(errors))


def z_from_service_level(service_level: float) -> float:
    """Z value = inverse of the standard normal CDF (95% -> 1.645, 99% -> 2.326)."""
    return float(NormalDist().inv_cdf(service_level))


def demand_variability(history: pd.DataFrame, window_days: int = config.VARIABILITY_WINDOW_DAYS) -> dict[str, Any]:
    """Standard deviation of daily demand over the last `window_days` calendar days of real history.

    history: StockCode-level rows with Date, demand (calendar days, closed days = 0).
    """
    h = history.sort_values("Date")
    if h.empty:
        return {"std_daily": None, "mean_daily": None, "observed_days": 0, "sufficient": False}
    end = h["Date"].max()
    recent = h[h["Date"] > end - pd.Timedelta(days=window_days)]
    n = int(len(recent))
    sufficient = n >= config.MIN_DAYS_FOR_VARIABILITY
    return {
        "std_daily": float(recent["demand"].std(ddof=1)) if n > 1 and sufficient else None,
        "mean_daily": float(recent["demand"].mean()) if n else None,
        "observed_days": n,
        "window_days": window_days,
        "sufficient": sufficient,
    }


def classify_stock_status(current_stock: float, safety_stock: float, reorder_point: float, target_stock: float,
                          avg_daily_demand: float, overstock_factor: float = config.OVERSTOCK_FACTOR) -> tuple[str, str]:
    """THE single rule used everywhere for inventory status.

    Critical Stock : stock <= safety stock (or zero stock while demand is expected)
    Low Stock      : stock <= reorder point -> time to order
    Overstocked    : stock > overstock_factor x target stock (or any stock with no expected demand)
    Healthy Stock  : otherwise
    """
    if avg_daily_demand <= 0 and reorder_point <= 0:
        if current_stock > 0:
            return "Overstocked", "No demand is forecast, so any stock on hand is surplus."
        return "Healthy Stock", "No stock and no forecast demand."
    if current_stock <= 0 or current_stock <= safety_stock:
        return "Critical Stock", "Stock is at or below the safety stock: high risk of running out before a delivery arrives."
    if current_stock <= reorder_point:
        return "Low Stock", "Stock is at or below the reorder point: place an order now."
    if target_stock > 0 and current_stock > overstock_factor * target_stock:
        return "Overstocked", f"Stock is more than {overstock_factor:g}x the target stock level: capital is tied up."
    return "Healthy Stock", "Stock is between the reorder point and the overstock limit."


def apply_order_constraints(raw_qty: float, current_stock: float, min_order_qty: int | None, pack_size: int | None,
                            max_capacity: int | None) -> dict[str, Any]:
    """Turn the raw order need into an orderable quantity and explain every adjustment."""
    steps: list[str] = []
    if raw_qty <= 0:
        return {"final_order_qty": 0, "steps": ["No order needed (stock already at or above target)."],
                "capacity_limited": False, "capacity_shortfall": 0}
    qty = int(math.ceil(raw_qty))
    steps.append(f"Raw need {raw_qty:.2f} rounded up to {qty} whole units.")
    if min_order_qty and qty < min_order_qty:
        steps.append(f"Raised to the minimum order quantity of {min_order_qty}.")
        qty = int(min_order_qty)
    if pack_size and pack_size > 1 and qty % pack_size:
        new = int(math.ceil(qty / pack_size) * pack_size)
        steps.append(f"Rounded up from {qty} to {new} to fit packs of {pack_size}.")
        qty = new
    limited, shortfall = False, 0
    if max_capacity is not None:
        room = max(0, int(math.floor(max_capacity - current_stock)))
        if qty > room:
            allowed = room
            if pack_size and pack_size > 1:
                allowed = (room // pack_size) * pack_size
            shortfall = qty - allowed
            steps.append(f"Storage capacity {max_capacity} allows only {allowed} more units "
                         f"({shortfall} units short of the recommendation).")
            if min_order_qty and 0 < allowed < min_order_qty:
                steps.append(f"Warning: the capacity-limited quantity is below the MOQ of {min_order_qty}.")
            qty, limited = allowed, True
    return {"final_order_qty": int(qty), "steps": steps, "capacity_limited": limited, "capacity_shortfall": int(shortfall)}


def calculate_inventory(inp: InventoryInputs, forecast_daily: list[float] | np.ndarray, variability: dict[str, Any],
                        forecast_horizon_days: int) -> dict[str, Any]:
    """Compute every inventory number for one product. Pure function (no files)."""
    validate_inputs(inp)
    fc = np.asarray(forecast_daily, dtype="float64")
    if fc.size == 0:
        raise InventoryInputError("A demand forecast is required to calculate inventory recommendations.")
    d = float(fc.mean())
    L, R = int(inp.lead_time_days), int(inp.review_period_days)
    z = z_from_service_level(inp.service_level)
    warnings: list[str] = []

    sd = variability.get("std_daily")
    if not variability.get("sufficient") or sd is None:
        safety_stock = 0.0
        warnings.append(f"Insufficient demand history ({variability.get('observed_days', 0)} days < "
                        f"{config.MIN_DAYS_FOR_VARIABILITY}): safety stock NOT calculated; recommendation is low-confidence.")
        confidence = "low"
    else:
        safety_stock = z * sd * math.sqrt(L)
        confidence = "normal"
    if L + R > forecast_horizon_days:
        warnings.append(f"Lead time + review period ({L + R} days) exceeds the {forecast_horizon_days}-day forecast; "
                        "average forecast demand is extended beyond the horizon.")

    lead_time_demand = d * L
    reorder_point = lead_time_demand + safety_stock
    target_stock = d * (L + R) + safety_stock
    raw_order = max(0.0, target_stock - inp.current_stock)
    order = apply_order_constraints(raw_order, inp.current_stock, inp.min_order_qty, inp.pack_size, inp.max_capacity)
    status, reason = classify_stock_status(inp.current_stock, safety_stock, reorder_point, target_stock, d)

    alerts = []
    if status == "Critical Stock":
        alerts.append({"level": "critical", "message": f"{inp.stock_code}: critical stock — order {order['final_order_qty']} units immediately."})
    elif status == "Low Stock":
        alerts.append({"level": "warning", "message": f"{inp.stock_code}: below reorder point — order {order['final_order_qty']} units."})
    elif status == "Overstocked":
        alerts.append({"level": "info", "message": f"{inp.stock_code}: overstocked — pause ordering."})
    if inp.current_stock < lead_time_demand:
        alerts.append({"level": "warning", "message": f"Stockout risk: current stock covers less than the {L}-day lead-time demand."})
    if order["capacity_limited"]:
        alerts.append({"level": "warning", "message": f"Capacity limit: order reduced by {order['capacity_shortfall']} units."})

    def r(x: float) -> float:
        return round(float(x), 2)

    return {
        "inputs": {**asdict(inp), "source": "user-entered"},
        "z_value": round(z, 4),
        "average_daily_demand": r(d),
        "forecast_total": r(fc.sum()),
        "forecast_horizon_days": forecast_horizon_days,
        "demand_std_daily": None if sd is None else r(sd),
        "variability_window_days": variability.get("window_days"),
        "variability_observed_days": variability.get("observed_days"),
        "lead_time_demand": r(lead_time_demand),
        "safety_stock": r(safety_stock),
        "reorder_point": r(reorder_point),
        "target_stock": r(target_stock),
        "raw_order_quantity": r(raw_order),
        "suggested_order_quantity": order["final_order_qty"],
        "order_adjustments": order["steps"],
        "capacity_limited": order["capacity_limited"],
        "capacity_shortfall": order["capacity_shortfall"],
        "days_of_cover": r(inp.current_stock / d) if d > 0 else None,
        "status": status,
        "status_reason": reason,
        "alerts": alerts,
        "confidence": confidence,
        "warnings": warnings,
        "value_sources": {
            "current_stock / lead_time / service_level / MOQ / pack / capacity": "user-entered",
            "average_daily_demand / forecast_total": "model-predicted",
            "demand_std_daily": "dataset-derived (last 84 days of real sales)",
            "safety_stock / reorder_point / target_stock / order": "calculated",
        },
        "policy": {
            "safety_stock": "Z x daily demand std x sqrt(lead time)",
            "reorder_point": "average daily demand x lead time + safety stock",
            "target_stock": "average daily demand x (lead time + review period) + safety stock",
            "order_quantity": "max(0, target stock - current stock), then MOQ / pack size / capacity",
            "assumptions": "Independent daily demand, fixed lead time, forecast demand constant over the lead time.",
            "overstock_rule": f"stock > {config.OVERSTOCK_FACTOR:g} x target stock",
        },
        "disclaimer": "Recommendation based on user-entered operational data and model forecasts; "
                      "UCI provides no historical stock levels.",
    }
