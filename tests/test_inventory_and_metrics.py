"""Inventory formulas, status rule, metrics and ABC analysis."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from ml import config
from ml.analytics import abc_analysis
from ml.evaluate import regression_metrics
from ml.inventory import (InventoryInputError, InventoryInputs, apply_order_constraints, calculate_inventory,
                          classify_stock_status, z_from_service_level)

OK_VAR = {"std_daily": 4.0, "mean_daily": 10.0, "observed_days": 84, "window_days": 84, "sufficient": True}


def test_z_values() -> None:
    assert z_from_service_level(0.95) == pytest.approx(1.6449, abs=1e-3)
    assert z_from_service_level(0.99) == pytest.approx(2.3263, abs=1e-3)
    assert z_from_service_level(0.5) == pytest.approx(0.0, abs=1e-9)


def test_formulas_match_hand_calculation() -> None:
    inp = InventoryInputs("X", current_stock=50, lead_time_days=9, service_level=0.95, review_period_days=7)
    r = calculate_inventory(inp, [10.0] * 30, OK_VAR, 30)
    z = 1.6448536
    ss = z * 4.0 * 3.0
    assert r["safety_stock"] == pytest.approx(round(ss, 2), abs=0.01)
    assert r["reorder_point"] == pytest.approx(round(90 + ss, 2), abs=0.01)
    assert r["target_stock"] == pytest.approx(round(160 + ss, 2), abs=0.01)
    assert r["suggested_order_quantity"] == math.ceil(160 + ss - 50)
    assert r["status"] == "Low Stock"


@pytest.mark.parametrize("field,value", [("current_stock", -1), ("lead_time_days", 0), ("lead_time_days", 400),
                                         ("service_level", 1.2), ("service_level", 0.3), ("pack_size", 0),
                                         ("max_capacity", 0), ("min_order_qty", -5), ("review_period_days", 0)])
def test_invalid_inputs_rejected(field: str, value: float) -> None:
    kwargs = dict(stock_code="X", current_stock=10, lead_time_days=5, service_level=0.95)
    kwargs[field] = value
    with pytest.raises(InventoryInputError):
        calculate_inventory(InventoryInputs(**kwargs), [1.0] * 30, OK_VAR, 30)


def test_moq_pack_and_capacity() -> None:
    r = apply_order_constraints(7.2, current_stock=0, min_order_qty=20, pack_size=12, max_capacity=None)
    assert r["final_order_qty"] == 24                                   # 8 -> MOQ 20 -> pack 24
    r = apply_order_constraints(100, current_stock=50, min_order_qty=None, pack_size=12, max_capacity=110)
    assert r["final_order_qty"] == 60 and r["capacity_limited"] and r["capacity_shortfall"] == 48
    r = apply_order_constraints(0, current_stock=500, min_order_qty=20, pack_size=12, max_capacity=None)
    assert r["final_order_qty"] == 0                                    # MOQ only applies when ordering


def test_status_rule_single_source() -> None:
    assert classify_stock_status(5, 10, 50, 100, 5)[0] == "Critical Stock"
    assert classify_stock_status(0, 0, 50, 100, 5)[0] == "Critical Stock"
    assert classify_stock_status(40, 10, 50, 100, 5)[0] == "Low Stock"
    assert classify_stock_status(80, 10, 50, 100, 5)[0] == "Healthy Stock"
    assert classify_stock_status(151, 10, 50, 100, 5)[0] == "Overstocked"
    assert classify_stock_status(10, 0, 0, 0, 0)[0] == "Overstocked"
    assert classify_stock_status(0, 0, 0, 0, 0)[0] == "Healthy Stock"


def test_insufficient_history_does_not_invent_variability() -> None:
    weak = {"std_daily": None, "mean_daily": 3.0, "observed_days": 10, "window_days": 84, "sufficient": False}
    r = calculate_inventory(InventoryInputs("X", 0, 5, 0.95), [2.0] * 30, weak, 30)
    assert r["safety_stock"] == 0 and r["confidence"] == "low" and r["demand_std_daily"] is None
    assert any("Insufficient" in w for w in r["warnings"])


def test_metrics_and_safe_mape() -> None:
    m = regression_metrics([0, 0, 10, 20], [1, 0, 12, 10])
    assert m["mae"] == pytest.approx((1 + 0 + 2 + 10) / 4)
    assert m["wape_pct"] == pytest.approx(100 * 13 / 30)
    assert m["mape_pct"] == pytest.approx(100 * (0.2 + 0.5) / 2)      # zero-demand rows excluded
    assert m["mape_coverage_pct"] == 50.0
    assert regression_metrics([0, 0], [1, 1])["mape_pct"] is None      # never a misleading value


def test_abc_classes_follow_cumulative_revenue() -> None:
    sales = pd.DataFrame({
        "StockCode": list("ABCDE"), "Description": list("ABCDE"), "Quantity": [1] * 5,
        "Revenue": [50.0, 30.0, 10.0, 6.0, 4.0], "InvoiceNo": list("12345"),
        "Date": pd.Timestamp("2011-01-01"), "CustomerID": pd.array([1] * 5, dtype="Int64"),
    })
    abc = abc_analysis(sales).set_index("StockCode")["abc_class"].to_dict()
    assert abc == {"A": "A", "B": "A", "C": "B", "D": "B", "E": "C"}
    assert config.ABC_THRESHOLDS == (0.80, 0.95)
