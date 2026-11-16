"""
Forecast generation + persistent forecast history.

History storage (survives restarts):
    storage/forecasts/forecast_history.csv          one summary row per forecast (append-only)
    storage/forecasts/records/<record_id>.json      full daily forecast of that run
"""

from __future__ import annotations

from typing import Any

from app.services import analytics_service, data_cache
from app.services.storage_service import append_csv_row, load_json, new_record_id, read_csv_rows, save_json, storage_path
from app.utils.errors import NotFoundError
from ml import config, forecasting
from ml.forecasting import ModelNotAvailableError
from ml.utils import to_json_safe, utc_now_iso

HISTORY_COLUMNS = ["record_id", "created_at", "stock_code", "description", "horizon_days", "model_name",
                   "forecast_origin", "total_forecast_units", "average_daily_demand"]


def _bundle() -> dict[str, Any]:
    path = config.ARTIFACTS_DIR / "demand_model.joblib"
    try:
        return data_cache.cached(path, "bundle", forecasting.load_bundle)
    except FileNotFoundError as exc:
        raise ModelNotAvailableError("No trained model found. Run the pipeline first.") from exc


def _panel():
    path = config.PROCESSED_DATA_DIR / "demand_panel.parquet"
    try:
        return data_cache.cached(path, "panel", forecasting.load_panel)
    except FileNotFoundError as exc:
        raise ModelNotAvailableError("Demand panel missing. Run the pipeline first.") from exc


def _calendar():
    path = config.PROCESSED_DATA_DIR / "store_calendar.parquet"
    try:
        return data_cache.cached(path, "calendar", forecasting.load_calendar)
    except FileNotFoundError as exc:
        raise ModelNotAvailableError("Store calendar missing. Run the pipeline first.") from exc


def generate(stock_code: str, horizon: int, save: bool = True) -> dict[str, Any]:
    result = forecasting.forecast_product(stock_code, horizon, _bundle(), _panel(), _calendar())
    result = to_json_safe(result)
    result["description"] = analytics_service.description_of(stock_code)
    try:  # the backtest is optional extra detail: it must never make the forecast itself fail
        result["backtest"] = to_json_safe(forecasting.backtest_for_product(stock_code))
    except Exception:  # noqa: BLE001
        result["backtest"] = []
    result["record_id"] = new_record_id()
    result["created_at"] = utc_now_iso()
    if save:
        save_json(storage_path("forecasts", "records", f"{result['record_id']}.json"), result)
        append_csv_row(storage_path("forecasts", "forecast_history.csv"), {
            **result, "total_forecast_units": result["summary"]["total_forecast_units"],
            "average_daily_demand": result["summary"]["average_daily_demand"]}, HISTORY_COLUMNS)
    return result


def history(stock_code: str | None, limit: int) -> list[dict[str, Any]]:
    rows = read_csv_rows(storage_path("forecasts", "forecast_history.csv"))
    for r in rows:  # CSV stores text; restore numeric types for the API
        r["horizon_days"] = int(r["horizon_days"]) if r.get("horizon_days") else None
        for k in ("total_forecast_units", "average_daily_demand"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    if stock_code:
        rows = [r for r in rows if r["stock_code"] == stock_code]
    return list(reversed(rows))[:limit]


def record(record_id: str) -> dict[str, Any]:
    if not record_id.isalnum() or len(record_id) != 32:
        raise NotFoundError("Unknown forecast record id.")
    path = storage_path("forecasts", "records", f"{record_id}.json")
    if not path.exists():
        raise NotFoundError("Forecast record not found.")
    return load_json(path, dict)


def model_products() -> list[str]:
    return list(_bundle()["products"])


def is_model_loadable() -> bool:
    path = config.ARTIFACTS_DIR / "demand_model.joblib"
    if not path.exists():
        return False
    try:
        _bundle()
        return True
    except Exception:  # noqa: BLE001 - a health check must never crash
        return False

