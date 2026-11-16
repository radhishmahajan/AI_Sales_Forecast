"""
DEMAND FORECASTING ENGINE — recursive multi-step forecasting (7, 14 or 30 days).

How recursive forecasting works
-------------------------------
The model predicts ONE day ahead. To forecast 30 days:
    day 1: build features from real history  -> predict day 1
    day 2: append the day-1 PREDICTION to the history, rebuild features -> predict day 2
    ... repeat until the horizon is reached.
Actual future demand is never used. Because later days are built on earlier predictions,
errors can accumulate, so long horizons are less accurate. The recursive backtest
(see recursive_backtest) measures exactly this on the test period.

Closed days: the shop never traded on certain weekdays (Saturday in this dataset). Those future
days are forecast as 0 by an explicit rule, exactly as they appear (as 0) in the training series.
Public holidays in the future are not known to the model, so they are forecast as normal days.

Same code as training: features come from feature_engineering.make_features().
No prediction intervals are shown, because no validated uncertainty method is implemented.
"""

from __future__ import annotations

import logging
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml import config
from ml.evaluate import regression_metrics
from ml.feature_engineering import make_features

logger = logging.getLogger(__name__)

RECURSIVE_NOTE = ("Recursive forecast: each day's prediction becomes input for the next day, so errors can "
                  "accumulate over longer horizons. Treat 30-day forecasts as less certain than 7-day ones.")


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained model artifacts are missing or unreadable."""


class ProductNotForecastableError(ValueError):
    """Raised for unknown products or products outside the modelled set."""


# ===========================================================================
# Loading artifacts
# ===========================================================================
def load_bundle() -> dict[str, Any]:
    path = config.ARTIFACTS_DIR / "demand_model.joblib"
    if not path.exists():
        raise ModelNotAvailableError("No trained model found (artifacts/demand_model.joblib). Run the training pipeline first.")
    try:
        bundle = joblib.load(path)
    except Exception as exc:
        raise ModelNotAvailableError(f"Model file could not be loaded ({type(exc).__name__}). Re-run training.") from exc
    for key in ("model", "feature_columns", "products", "closed_weekdays", "data_end_date"):
        if key not in bundle:
            raise ModelNotAvailableError(f"Model file is incomplete (missing '{key}'). Re-run training.")
    return bundle


def load_panel() -> pd.DataFrame:
    path = config.PROCESSED_DATA_DIR / "demand_panel.parquet"
    if not path.exists():
        raise ModelNotAvailableError("Demand panel not found (data/processed/demand_panel.parquet). Run the pipeline first.")
    return pd.read_parquet(path)


def load_calendar() -> pd.DataFrame:
    path = config.PROCESSED_DATA_DIR / "store_calendar.parquet"
    if not path.exists():
        raise ModelNotAvailableError("Store calendar not found. Run the pipeline first.")
    return pd.read_parquet(path)


# ===========================================================================
# Core recursive loop (works for one or many products at once)
# ===========================================================================
def extend_history_to(history: pd.DataFrame, origin: pd.Timestamp, calendar: pd.DataFrame) -> pd.DataFrame:
    """Make every product's history end exactly at `origin`.

    If a product's last observed sale is before the origin, the days in between are real
    observed days on which the product did not sell, so they are added as 0 demand with
    the true open/closed flags from the store calendar.
    """
    pieces = [history[history["Date"] <= origin]]
    cal = calendar.set_index("Date")["is_open"]
    last = history.groupby("StockCode")["Date"].max()
    for code, last_date in last.items():
        if last_date < origin:
            dates = pd.date_range(last_date + pd.Timedelta(days=1), origin, freq="D")
            pieces.append(pd.DataFrame({"StockCode": code, "Date": dates, "demand": 0.0, "avg_price": np.nan,
                                        "is_open": cal.reindex(dates).fillna(False).to_numpy(dtype=bool)}))
    return pd.concat(pieces, ignore_index=True).sort_values(["StockCode", "Date"]).reset_index(drop=True)


def recursive_forecast(history: pd.DataFrame, model: Any, feature_columns: list[str], closed_weekdays: list[int],
                       horizon: int) -> pd.DataFrame:
    """Forecast `horizon` days after the last date in `history` for every product in it.

    history columns: StockCode, Date, demand, avg_price, is_open (consecutive days, ending at the origin).
    Returns StockCode, Date, predicted_demand, is_open.
    """
    work = history[["StockCode", "Date", "demand", "avg_price", "is_open"]].copy()
    work["demand"] = work["demand"].astype("float64")
    origin = work["Date"].max()
    codes = work["StockCode"].unique()
    out = []
    for step in range(1, horizon + 1):
        day = origin + pd.Timedelta(days=step)
        is_open = day.dayofweek not in closed_weekdays
        new = pd.DataFrame({"StockCode": codes, "Date": day, "demand": np.nan, "avg_price": np.nan, "is_open": is_open})
        work = pd.concat([work, new], ignore_index=True)
        feats = make_features(work)
        rows = feats[feats["Date"] == day]
        if is_open:
            preds = np.clip(model.predict(rows[feature_columns]), 0, None)
        else:
            preds = np.zeros(len(rows))
        pred_map = dict(zip(rows["StockCode"], preds))
        mask = work["Date"] == day
        work.loc[mask, "demand"] = work.loc[mask, "StockCode"].map(pred_map).astype("float64")
        out.append(pd.DataFrame({"StockCode": rows["StockCode"].to_numpy(), "Date": day,
                                 "predicted_demand": preds, "is_open": is_open}))
    return pd.concat(out, ignore_index=True)


# ===========================================================================
# Recursive backtest on the test period (proves error accumulation honestly)
# ===========================================================================
def recursive_backtest(panel: pd.DataFrame, model: Any, feature_columns: list[str], closed_weekdays: list[int],
                       origin: pd.Timestamp, horizons: tuple[int, ...] = config.FORECAST_HORIZONS) -> pd.DataFrame:
    """Forecast max(horizons) days from `origin` using only data up to `origin`, compare with actuals.

    `model` must NOT have been trained on data after `origin` (use the train+validation model).
    Baselines for comparison: 7-day moving average held flat, and repeating the last week.
    """
    H = max(horizons)
    active = panel.groupby("StockCode")["Date"].agg(["min", "max"])
    codes = active[(active["min"] <= origin - pd.Timedelta(days=config.MIN_HISTORY_DAYS)) & (active["max"] > origin)].index
    hist = panel[panel["StockCode"].isin(codes) & (panel["Date"] <= origin)]
    fc = recursive_forecast(hist, model, feature_columns, closed_weekdays, H)

    last7 = hist[hist["Date"] > origin - pd.Timedelta(days=7)]
    ma7 = last7.groupby("StockCode")["demand"].mean()
    fc["baseline_moving_average_7"] = np.where(fc["is_open"], fc["StockCode"].map(ma7), 0.0)
    last_week = last7.assign(dow=last7["Date"].dt.dayofweek).set_index(["StockCode", "dow"])["demand"]
    keys = list(zip(fc["StockCode"], fc["Date"].dt.dayofweek))
    fc["baseline_repeat_last_week"] = last_week.reindex(keys).to_numpy()

    actual = panel[(panel["Date"] > origin) & (panel["Date"] <= origin + pd.Timedelta(days=H)) & panel["is_open"]]
    merged = actual[["StockCode", "Date", "demand"]].merge(fc, on=["StockCode", "Date"], how="inner")
    merged["day_ahead"] = (merged["Date"] - origin).dt.days

    rows = []
    for h in horizons:
        sub = merged[merged["day_ahead"] <= h]
        for method, col in (("model (recursive)", "predicted_demand"), ("baseline_moving_average_7", "baseline_moving_average_7"),
                            ("baseline_repeat_last_week", "baseline_repeat_last_week")):
            m = regression_metrics(sub["demand"], sub[col])
            rows.append({"horizon_days": h, "method": method, "products": int(sub["StockCode"].nunique()), **m})
    return pd.DataFrame(rows)


# ===========================================================================
# Single-product forecast used by the API / dashboard
# ===========================================================================
def validate_horizon(horizon: int) -> int:
    if horizon not in config.FORECAST_HORIZONS:
        raise ValueError(f"Forecast horizon must be one of {list(config.FORECAST_HORIZONS)} days (got {horizon}).")
    return horizon


def forecast_product(stock_code: str, horizon: int, bundle: dict[str, Any] | None = None,
                     panel: pd.DataFrame | None = None, calendar: pd.DataFrame | None = None) -> dict[str, Any]:
    validate_horizon(horizon)
    bundle = bundle or load_bundle()
    stock_code = str(stock_code).strip()
    if stock_code not in set(bundle["products"]):
        raise ProductNotForecastableError(
            f"Product '{stock_code}' is not in the modelled product set ({len(bundle['products'])} products with the "
            "longest sales history). Choose a product from the forecasting product list."
        )
    panel = load_panel() if panel is None else panel
    calendar = load_calendar() if calendar is None else calendar
    history = panel[panel["StockCode"] == stock_code]
    origin = pd.Timestamp(bundle["data_end_date"]).normalize()
    history = extend_history_to(history, origin, calendar)

    fc = recursive_forecast(history, bundle["model"], bundle["feature_columns"], bundle["closed_weekdays"], horizon)
    fc["predicted_demand"] = fc["predicted_demand"].astype(float)

    last_sale = history.loc[history["demand"] > 0, "Date"].max()
    days_since = int((origin - last_sale).days) if pd.notna(last_sale) else None
    warnings = [RECURSIVE_NOTE,
                "Public holidays after the data end are not known to the model; check forecasts around Christmas/New Year."]
    if days_since is not None and days_since > 28:
        warnings.append(f"No sales in the last {days_since} days of the data: the product may be discontinued.")

    hist90 = history[history["Date"] > origin - pd.Timedelta(days=90)]
    hist30 = history[history["Date"] > origin - pd.Timedelta(days=30)]
    total = float(fc["predicted_demand"].sum())
    open_fc = fc[fc["is_open"]]

    weekly = (fc.assign(week_start=fc["Date"] - pd.to_timedelta(fc["Date"].dt.dayofweek, unit="D"))
                .groupby("week_start").agg(predicted_units=("predicted_demand", "sum"), days=("Date", "size")).reset_index())

    return {
        "stock_code": stock_code,
        "horizon_days": horizon,
        "forecast_origin": origin,
        "model_name": bundle.get("model_name"),
        "model_trained_at": bundle.get("trained_at"),
        "daily": [{"date": r.Date, "predicted_demand": round(r.predicted_demand, 3), "is_open": bool(r.is_open),
                   "source": "model-predicted" if r.is_open else "closed-day rule (0)"} for r in fc.itertuples()],
        "summary": {
            "total_forecast_units": round(total, 2),
            "average_daily_demand": round(total / horizon, 3),
            "average_demand_per_open_day": round(float(open_fc["predicted_demand"].mean()), 3) if len(open_fc) else 0.0,
            "open_days_in_horizon": int(fc["is_open"].sum()),
            "historical_avg_daily_demand_last_30_days": round(float(hist30["demand"].mean()), 3) if len(hist30) else None,
            "historical_total_last_30_days": round(float(hist30["demand"].sum()), 2),
            "days_since_last_sale": days_since,
        },
        "weekly": [{"week_start": r.week_start, "predicted_units": round(float(r.predicted_units), 2), "days": int(r.days)}
                   for r in weekly.itertuples()],
        "history": [{"date": r.Date, "demand": float(r.demand), "is_open": bool(r.is_open)} for r in hist90.itertuples()],
        "warnings": warnings,
        "uncertainty": "Not shown: no validated uncertainty method is implemented.",
    }


def backtest_for_product(stock_code: str) -> list[dict[str, Any]]:
    """One-step-ahead actual vs predicted on the test period (from the evaluation model)."""
    path = config.PROCESSED_DATA_DIR / "test_predictions.parquet"
    meta_path = config.ARTIFACTS_DIR / "model_metadata.json"
    if not path.exists() or not meta_path.exists():
        return []
    import json

    best = json.loads(meta_path.read_text(encoding="utf-8"))["model_name"]
    df = pd.read_parquet(path)
    sub = df[df["StockCode"].astype(str) == str(stock_code)].sort_values("Date")
    return [{"date": r["Date"], "actual": float(r["actual"]), "predicted": round(float(r[best]), 3)} for _, r in sub.iterrows()]
