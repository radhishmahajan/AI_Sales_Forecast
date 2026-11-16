"""End-to-end pipeline (synthetic data, fast mode) + forecasting engine behaviour."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ml import config, forecasting
from ml.forecasting import ModelNotAvailableError, ProductNotForecastableError


def test_pipeline_creates_all_artifacts(use_trained_project: Path) -> None:
    for rel in ("artifacts/demand_model.joblib", "artifacts/model_metadata.json", "artifacts/feature_columns.json",
                "artifacts/feature_importance.json", "data/processed/cleaned_sales.csv", "data/processed/features.parquet",
                "data/reports/01_dataset_overview.json", "data/reports/02_eda_report.json",
                "data/reports/03_preprocessing_report.json", "data/reports/09_model_evaluation.json",
                "data/reports/metrics/model_comparison.csv", "storage/products/products.json",
                "storage/pipeline_status.json"):
        assert (use_trained_project / rel).exists(), rel
    status = json.loads((use_trained_project / "storage/pipeline_status.json").read_text())
    assert status["state"] == "completed" and all(s["state"] == "completed" for s in status["steps"])
    meta = json.loads((use_trained_project / "artifacts/model_metadata.json").read_text())
    comp = pd.read_csv(use_trained_project / "data/reports/metrics/model_comparison.csv")
    val = comp[(comp["split"] == "validation") & (comp["type"] == "ml")]
    assert meta["model_name"] == val.loc[val["mae"].idxmin(), "model"]   # selected by validation, not test


@pytest.mark.parametrize("horizon", [7, 14, 30])
def test_forecast_horizons(use_trained_project: Path, horizon: int) -> None:
    code = forecasting.load_bundle()["products"][0]
    out = forecasting.forecast_product(code, horizon)
    assert len(out["daily"]) == horizon
    assert all(d["predicted_demand"] >= 0 for d in out["daily"])
    assert all(d["predicted_demand"] == 0 for d in out["daily"] if not d["is_open"])   # closed-day rule
    assert out["summary"]["total_forecast_units"] == pytest.approx(sum(d["predicted_demand"] for d in out["daily"]), abs=0.05)
    assert all(pd.Timestamp(d["date"]) > pd.Timestamp(out["forecast_origin"]) for d in out["daily"])


def test_invalid_horizon_and_product(use_trained_project: Path) -> None:
    with pytest.raises(ValueError):
        forecasting.forecast_product(forecasting.load_bundle()["products"][0], 10)
    with pytest.raises(ProductNotForecastableError):
        forecasting.forecast_product("NOT-A-PRODUCT", 7)


def test_recursive_forecast_ignores_actual_future(use_trained_project: Path) -> None:
    b = forecasting.load_bundle()
    panel = forecasting.load_panel()
    code = b["products"][0]
    hist = panel[panel["StockCode"] == code]
    origin = hist["Date"].iloc[-20]
    past = hist[hist["Date"] <= origin]
    tampered = hist.copy()
    tampered.loc[tampered["Date"] > origin, "demand"] = 10_000.0          # fake "future" actuals
    a = forecasting.recursive_forecast(past, b["model"], b["feature_columns"], b["closed_weekdays"], 7)
    c = forecasting.recursive_forecast(tampered[tampered["Date"] <= origin], b["model"], b["feature_columns"], b["closed_weekdays"], 7)
    pd.testing.assert_frame_equal(a, c)


def test_missing_model_artifact_raises(isolated_project: Path) -> None:
    with pytest.raises(ModelNotAvailableError):
        forecasting.load_bundle()
    (config.ARTIFACTS_DIR / "demand_model.joblib").write_bytes(b"corrupted")
    with pytest.raises(ModelNotAvailableError):
        forecasting.load_bundle()
