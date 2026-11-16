"""
STAGE 9 — Model evaluation.

Metrics (all computed on real held-out data, never typed in by hand)
--------------------------------------------------------------------
MAE   Mean Absolute Error: average size of the error in units. "On average we are off by X units/day."
RMSE  Root Mean Squared Error: like MAE but punishes big misses more (sensitive to bulk orders).
WAPE  Weighted Absolute Percentage Error = sum|actual - predicted| / sum(actual) x 100.
      The % of total demand that was mis-forecast. Works with zero-demand days, so it is the
      main percentage metric for intermittent retail demand.
MAPE  Mean Absolute Percentage Error. Undefined when actual = 0 and explodes when actual is tiny
      (actual 1, predicted 3 -> 200%). We therefore compute it ONLY on days with actual demand
      >= config.MAPE_MIN_ACTUAL units and always report how many rows it covers.
R2    Share of variance explained (1 = perfect, 0 = no better than predicting the mean). Diagnostic only.
Bias  Mean(predicted - actual): positive = over-forecasting on average.
"""

from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

from ml import config  # noqa: E402

METRIC_EXPLANATIONS = {
    "mae": "Mean Absolute Error (units/day). Lower is better.",
    "rmse": "Root Mean Squared Error (units/day). Penalises large misses. Lower is better.",
    "wape_pct": "Weighted Absolute Percentage Error: total absolute error / total actual demand x 100. Lower is better.",
    "mape_pct": f"MAPE on days with actual demand >= {config.MAPE_MIN_ACTUAL:g} units only (undefined for zero days).",
    "mape_coverage_pct": "Share of rows on which MAPE was computed.",
    "r2": "Coefficient of determination (diagnostic). 1 = perfect.",
    "bias": "Mean(predicted - actual). Positive = over-forecasting.",
}


def regression_metrics(actual: np.ndarray | pd.Series, predicted: np.ndarray | pd.Series) -> dict[str, float | int | None]:
    y = np.asarray(actual, dtype="float64")
    p = np.asarray(predicted, dtype="float64")
    mask = ~(np.isnan(y) | np.isnan(p))
    y, p = y[mask], p[mask]
    if y.size == 0:
        return {"n": 0, "mae": None, "rmse": None, "wape_pct": None, "mape_pct": None, "mape_coverage_pct": 0.0, "r2": None, "bias": None}
    err = p - y
    abs_err = np.abs(err)
    total = np.abs(y).sum()
    mape_mask = y >= config.MAPE_MIN_ACTUAL
    ss_tot = ((y - y.mean()) ** 2).sum()
    return {
        "n": int(y.size),
        "mae": float(abs_err.mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "wape_pct": float(100 * abs_err.sum() / total) if total > 0 else None,
        "mape_pct": float(100 * (abs_err[mape_mask] / y[mape_mask]).mean()) if mape_mask.any() else None,
        "mape_coverage_pct": float(100 * mape_mask.mean()),
        "r2": float(1 - (err**2).sum() / ss_tot) if ss_tot > 0 else None,
        "bias": float(err.mean()),
    }


def error_by_group(df: pd.DataFrame, pred_col: str, group: str) -> pd.DataFrame:
    tmp = df.assign(abs_err=(df[pred_col] - df["actual"]).abs())
    g = tmp.groupby(group, observed=True)
    out = pd.DataFrame({
        "mae": g["abs_err"].mean(),
        "total_actual": g["actual"].sum(),
        "total_abs_error": g["abs_err"].sum(),
        "rows": g.size(),
    })
    out["wape_pct"] = 100 * out["total_abs_error"] / out["total_actual"].replace(0, np.nan)
    return out.reset_index()


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def _save(fig: plt.Figure, name: str) -> str:
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / name, dpi=130)
    plt.close(fig)
    return f"figures/{name}"


def make_evaluation_charts(pred: pd.DataFrame, comparison: pd.DataFrame, best: str, best_baseline: str,
                           horizon_table: pd.DataFrame | None = None) -> list[dict[str, str]]:
    """pred: test rows with columns Date, StockCode, actual, <model columns>."""
    sns.set_theme(style="whitegrid")
    charts = []

    daily = pred.groupby("Date")[["actual", best, best_baseline]].sum()
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(daily.index, daily["actual"], lw=2, label="Actual units (all modelled products)")
    ax.plot(daily.index, daily[best], lw=2, ls="--", label=f"Predicted: {best}")
    ax.plot(daily.index, daily[best_baseline], lw=1.2, ls=":", label=f"Baseline: {best_baseline}")
    ax.set_title("Actual vs predicted daily demand on the test period (sum over modelled products)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Units per day")
    ax.legend()
    charts.append({"title": "Actual vs predicted (test)", "file": _save(fig, "09_actual_vs_predicted.png")})

    resid = pred[best] - pred["actual"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    sns.histplot(resid.clip(resid.quantile(0.01), resid.quantile(0.99)), bins=80, ax=ax, color="#8172B3")
    ax.axvline(0, color="black", lw=1)
    ax.set_title(f"Residual distribution on test period ({best}, 1st-99th percentile shown)")
    ax.set_xlabel("Predicted - actual (units)")
    ax.set_ylabel("Number of product-days")
    charts.append({"title": "Residual distribution", "file": _save(fig, "09_residuals.png")})

    comp = comparison.copy()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, metric, label in ((axes[0], "mae", "MAE (units/day)"), (axes[1], "wape_pct", "WAPE (%)")):
        sub = comp.pivot(index="model", columns="split", values=metric).sort_values("test")
        sub[["validation", "test"]].plot.barh(ax=ax, color=["#8FB3DE", "#4C72B0"])
        ax.set_title(f"{label} by model")
        ax.set_xlabel(label)
        ax.set_ylabel("Model")
    charts.append({"title": "Model comparison", "file": _save(fig, "09_model_comparison.png")})

    by_dow = error_by_group(pred.assign(dow=pred["Date"].dt.day_name()), best, "dow")
    order = [d for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] if d in set(by_dow["dow"])]
    by_dow = by_dow.set_index("dow").loc[order].reset_index()
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(by_dow["dow"], by_dow["wape_pct"], color="#4C72B0")
    ax.set_title(f"Test WAPE by weekday ({best})")
    ax.set_xlabel("Day of week")
    ax.set_ylabel("WAPE (%)")
    charts.append({"title": "Error by weekday", "file": _save(fig, "09_error_by_weekday.png")})

    by_prod = error_by_group(pred, best, "StockCode").nlargest(15, "total_abs_error").iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.barh(by_prod["StockCode"].astype(str), by_prod["total_abs_error"], color="#C44E52")
    ax.set_title(f"15 products with the largest total absolute error (test, {best})")
    ax.set_xlabel("Total absolute error (units)")
    ax.set_ylabel("StockCode")
    charts.append({"title": "Error by product", "file": _save(fig, "09_error_by_product.png")})

    if horizon_table is not None and not horizon_table.empty:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for method, sub in horizon_table.groupby("method"):
            ax.plot(sub["horizon_days"], sub["wape_pct"], marker="o", label=method)
        ax.set_title("Recursive multi-day forecast accuracy from the test origin")
        ax.set_xlabel("Forecast horizon (days)")
        ax.set_ylabel("WAPE over the horizon (%)")
        ax.set_xticks(sorted(horizon_table["horizon_days"].unique()))
        ax.legend()
        charts.append({"title": "Forecast accuracy by horizon", "file": _save(fig, "09_accuracy_by_horizon.png")})
    return charts
