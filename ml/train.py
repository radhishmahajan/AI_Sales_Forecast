"""
STAGES 6, 7 & 8 — Baselines, machine-learning models and hyperparameter tuning.

Workflow (no step ever looks at the test period before the final evaluation)
-----------------------------------------------------------------------------
1. Baselines (no learning): previous-day demand, same day last week, 7-day moving average.
   A model is only useful if it beats these.
2. For each ML model, tune hyperparameters with RandomizedSearchCV using ROLLING-ORIGIN
   folds built from TRAINING dates only (feature_engineering.rolling_origin_folds).
3. Fit each tuned model on the training period and score it on the VALIDATION period.
4. Select the best model by validation MAE (the lowest average error in units).
5. Refit every model on train + validation and evaluate ONCE on the untouched TEST period
   (this is the number we report).
6. Refit the selected model on ALL rows (train + validation + test) with the same
   hyperparameters and save it as artifacts/demand_model.joblib for live forecasting.

Negative predictions are clipped to 0 (explicit, documented rule: demand cannot be negative).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.stats import loguniform, randint, uniform
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml import config
from ml.evaluate import METRIC_EXPLANATIONS, regression_metrics
from ml.feature_engineering import FEATURE_COLUMNS, rolling_origin_folds
from ml.utils import atomic_write_csv, atomic_write_json, atomic_write_parquet, to_json_safe, utc_now_iso

logger = logging.getLogger(__name__)

try:  # XGBoost is optional
    from xgboost import XGBRegressor

    HAS_XGBOOST = True
except Exception:  # pragma: no cover
    HAS_XGBOOST = False

N_JOBS = max(1, (os.cpu_count() or 2))
MODEL_VERSION = "1.0"
CLIP_RULE = "Predictions below 0 are set to 0 because demand cannot be negative."

BASELINES: dict[str, tuple[str, str]] = {
    "baseline_previous_day": ("lag_1", "Tomorrow's demand = today's demand."),
    "baseline_same_day_last_week": ("lag_7", "Demand = demand on the same weekday last week."),
    "baseline_moving_average_7": ("rolling_mean_7", "Demand = average of the last 7 days."),
}

MODEL_DESCRIPTIONS = {
    "linear_regression": "Linear Regression: weighted sum of the (standardised) features. Simple, fast, interpretable.",
    "random_forest": "Random Forest: average of many decision trees trained on random samples of rows/features.",
    "hist_gradient_boosting": "HistGradientBoosting: trees added one after another, each fixing the previous errors (binned features, fast).",
    "xgboost": "XGBoost: regularised gradient boosting library, widely used in forecasting competitions.",
}


# ===========================================================================
# Model factories and search spaces
# ===========================================================================
def _pipeline(estimator: Any, scale: bool = False) -> Pipeline:
    steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        steps.append(("scaler", StandardScaler()))
    steps.append(("model", estimator))
    return Pipeline(steps)


def model_factories(fast: bool = False) -> dict[str, tuple[Callable[[], Pipeline], dict[str, Any] | None]]:
    """name -> (factory, param distributions for RandomizedSearchCV or None)."""
    rf_trees = [60, 100] if fast else [100, 200, 300]
    specs: dict[str, tuple[Callable[[], Pipeline], dict[str, Any] | None]] = {
        "linear_regression": (lambda: _pipeline(LinearRegression(), scale=True), None),
        "random_forest": (
            lambda: _pipeline(RandomForestRegressor(random_state=config.RANDOM_SEED, n_jobs=N_JOBS, max_samples=0.5)),
            {
                "model__n_estimators": rf_trees,
                "model__max_depth": [8, 12, 16, 24],
                "model__min_samples_split": [2, 5, 10, 20],
                "model__min_samples_leaf": [1, 3, 5, 10],
                "model__max_features": [0.3, 0.5, "sqrt", 1.0],
            },
        ),
        "hist_gradient_boosting": (
            lambda: _pipeline(HistGradientBoostingRegressor(random_state=config.RANDOM_SEED, early_stopping=False)),
            {
                "model__learning_rate": loguniform(0.02, 0.2),
                "model__max_iter": [100, 200, 400] if not fast else [50, 100],
                "model__max_leaf_nodes": [15, 31, 63],
                "model__l2_regularization": [0.0, 0.1, 1.0, 10.0],
                "model__loss": ["squared_error", "poisson"],
            },
        ),
    }
    if HAS_XGBOOST:
        specs["xgboost"] = (
            lambda: _pipeline(XGBRegressor(tree_method="hist", n_jobs=N_JOBS, random_state=config.RANDOM_SEED,
                                           objective="reg:squarederror", verbosity=0)),
            {
                "model__n_estimators": randint(100, 600) if not fast else [50, 100],
                "model__max_depth": [3, 4, 5, 6, 8],
                "model__learning_rate": loguniform(0.02, 0.2),
                "model__subsample": uniform(0.6, 0.4),
                "model__colsample_bytree": uniform(0.5, 0.5),
                "model__objective": ["reg:squarederror", "count:poisson", "reg:tweedie"],
                "model__tweedie_variance_power": [1.2, 1.35, 1.5],
            },
        )
    return specs


def loss_function_experiment(train: pd.DataFrame, val: pd.DataFrame) -> list[dict[str, Any]]:
    """Design check (validation data only): which loss suits count-like, spiky demand?

    Same HistGradientBoosting settings, three losses. Absolute-error loss predicts the MEDIAN,
    which for intermittent demand is far below the mean, so it under-forecasts total demand
    (large negative bias) — dangerous for inventory planning. That is why the tuned search
    spaces offer squared-error and Poisson/Tweedie losses but not absolute error.
    """
    out = []
    for loss in ("squared_error", "poisson", "absolute_error"):
        m = HistGradientBoostingRegressor(loss=loss, learning_rate=0.05, max_iter=300, max_leaf_nodes=31,
                                          l2_regularization=1.0, early_stopping=False, random_state=config.RANDOM_SEED)
        m.fit(train[FEATURE_COLUMNS], train[config.TARGET_COLUMN])
        met = regression_metrics(val[config.TARGET_COLUMN], np.clip(m.predict(val[FEATURE_COLUMNS]), 0, None))
        mean_actual = float(val[config.TARGET_COLUMN].mean())
        out.append({"loss": loss, "validation_mae": met["mae"], "validation_wape_pct": met["wape_pct"],
                    "validation_bias": met["bias"], "bias_pct_of_mean_demand": 100 * met["bias"] / mean_actual})
    return out


def predict_demand(model: Pipeline, X: pd.DataFrame) -> np.ndarray:
    """Model prediction with the documented clipping rule."""
    return np.clip(model.predict(X[FEATURE_COLUMNS]), 0, None)


# ===========================================================================
# Training workflow
# ===========================================================================
def tune_model(name: str, factory: Callable[[], Pipeline], dist: dict[str, Any] | None, train: pd.DataFrame,
               n_iter: int) -> dict[str, Any]:
    """Time-series-aware RandomizedSearchCV on the training period only."""
    if dist is None:
        return {"best_params": {}, "cv_mae": None, "cv_folds": 0, "candidates": 0}
    tr = train.reset_index(drop=True)
    folds = rolling_origin_folds(tr["Date"])
    search = RandomizedSearchCV(
        factory(), dist, n_iter=n_iter, cv=folds, scoring="neg_mean_absolute_error",
        random_state=config.RANDOM_SEED, n_jobs=1, refit=False, error_score="raise",
    )
    search.fit(tr[FEATURE_COLUMNS], tr[config.TARGET_COLUMN])
    best = {k: (v.item() if hasattr(v, "item") else v) for k, v in search.best_params_.items()}
    return {
        "best_params": best,
        "cv_mae": float(-search.best_score_),
        "cv_folds": len(folds),
        "candidates": n_iter,
        "cv_fold_periods": [
            {"train_until": tr["Date"].iloc[f[0]].max(), "validate": [tr["Date"].iloc[f[1]].min(), tr["Date"].iloc[f[1]].max()]}
            for f in folds
        ],
    }


def fit(factory: Callable[[], Pipeline], params: dict[str, Any], data: pd.DataFrame) -> Pipeline:
    model = factory()
    if params:
        model.set_params(**params)
    model.fit(data[FEATURE_COLUMNS], data[config.TARGET_COLUMN])
    return model


def train_and_evaluate(model_data: pd.DataFrame, fast: bool = False, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Full Stage 6-9 workflow. Returns models, predictions and metrics (does not write files)."""
    say = progress or (lambda msg: logger.info(msg))
    train = model_data[model_data["split"] == "train"]
    val = model_data[model_data["split"] == "validation"]
    test = model_data[model_data["split"] == "test"]
    trval = model_data[model_data["split"] != "test"]
    if min(len(train), len(val), len(test)) == 0:
        raise ValueError("Train/validation/test split produced an empty part; not enough history.")

    rows: list[dict[str, Any]] = []
    for name, (col, _) in BASELINES.items():
        for split_name, part in (("validation", val), ("test", test)):
            rows.append({"model": name, "type": "baseline", "split": split_name,
                         **regression_metrics(part[config.TARGET_COLUMN], part[col])})

    say("Loss-function design check on validation data")
    loss_experiment = loss_function_experiment(train, val) if not fast else []

    specs = model_factories(fast)
    tuning: dict[str, Any] = {}
    val_models: dict[str, Pipeline] = {}
    timings: dict[str, float] = {}
    for name, (factory, dist) in specs.items():
        t0 = time.time()
        n_iter = 2 if fast else config.TUNING_ITERATIONS.get(name, 6)
        say(f"Tuning {name} ({'no hyperparameters' if dist is None else f'{n_iter} candidates x {config.CV_FOLDS} folds'})")
        tuning[name] = tune_model(name, factory, dist, train, n_iter)
        model = fit(factory, tuning[name]["best_params"], train)
        val_models[name] = model
        rows.append({"model": name, "type": "ml", "split": "validation",
                     **regression_metrics(val[config.TARGET_COLUMN], predict_demand(model, val))})
        timings[name] = round(time.time() - t0, 1)
        say(f"{name}: validation MAE {rows[-1]['mae']:.3f} ({timings[name]}s)")

    val_scores = {r["model"]: r["mae"] for r in rows if r["type"] == "ml" and r["split"] == "validation"}
    best_name = min(val_scores, key=val_scores.get)
    say(f"Selected by validation MAE: {best_name}")

    # final evaluation on the untouched test period (each model refit on train+validation)
    test_pred = test[["Date", "StockCode", config.TARGET_COLUMN]].rename(columns={config.TARGET_COLUMN: "actual"}).copy()
    eval_models: dict[str, Pipeline] = {}
    for name, (factory, _) in specs.items():
        say(f"Refitting {name} on train+validation for the test evaluation")
        m = fit(factory, tuning[name]["best_params"], trval)
        eval_models[name] = m
        test_pred[name] = predict_demand(m, test)
        rows.append({"model": name, "type": "ml", "split": "test", **regression_metrics(test_pred["actual"], test_pred[name])})
    for name, (col, _) in BASELINES.items():
        test_pred[name] = test[col].to_numpy()

    comparison = pd.DataFrame(rows)
    base_val = comparison[(comparison["type"] == "baseline") & (comparison["split"] == "validation")]
    best_baseline = base_val.loc[base_val["mae"].idxmin(), "model"]

    say(f"Refitting {best_name} on all data for live forecasting")
    final_model = fit(specs[best_name][0], tuning[best_name]["best_params"], model_data)

    return {
        "comparison": comparison,
        "loss_experiment": loss_experiment,
        "tuning": tuning,
        "timings": timings,
        "best_model_name": best_name,
        "best_baseline_name": best_baseline,
        "val_models": val_models,
        "eval_models": eval_models,
        "final_model": final_model,
        "test_predictions": test_pred,
        "test_rows": test,
    }


def improvement_summary(comparison: pd.DataFrame, best: str, baseline: str) -> dict[str, Any]:
    t = comparison[comparison["split"] == "test"].set_index("model")
    b, m = t.loc[baseline], t.loc[best]
    return {
        "best_model": best,
        "best_baseline": baseline,
        "test_mae_model": m["mae"],
        "test_mae_baseline": b["mae"],
        "mae_improvement_pct": 100 * (b["mae"] - m["mae"]) / b["mae"] if b["mae"] else None,
        "test_wape_model": m["wape_pct"],
        "test_wape_baseline": b["wape_pct"],
        "beats_baseline": bool(m["mae"] < b["mae"]),
    }


def save_training_outputs(result: dict[str, Any], split_info: dict[str, Any], products: list[str],
                          closed_dows: list[int], data_end: Any, n_rows: int) -> dict[str, Any]:
    """Persist model + metadata + metrics (Joblib / JSON / CSV / Parquet)."""
    best = result["best_model_name"]
    comparison = result["comparison"]
    summary = improvement_summary(comparison, best, result["best_baseline_name"])

    metadata = to_json_safe({
        "model_name": best,
        "model_description": MODEL_DESCRIPTIONS.get(best),
        "model_version": MODEL_VERSION,
        "trained_at": utc_now_iso(),
        "target": config.TARGET_COLUMN,
        "target_definition": "Gross fulfilled demand: units of the product sold on date D (SALE rows), forecast from information up to D-1.",
        "features": FEATURE_COLUMNS,
        "selection_rule": "Lowest validation MAE among ML models (tuned with rolling-origin CV on training dates only).",
        "hyperparameters": result["tuning"][best]["best_params"],
        "all_tuning": result["tuning"],
        "loss_function_experiment": result.get("loss_experiment", []),
        "loss_function_note": "Absolute-error loss is excluded from tuning: it predicts the median and under-forecasts "
                              "total demand (see loss_function_experiment bias), which would cause stockouts.",
        "training_seconds": result["timings"],
        "split": split_info,
        "final_fit": "Selected model refit on all model rows (train + validation + test) with the same hyperparameters. "
                     "Reported test metrics come from the train+validation fit evaluated on the untouched test period.",
        "metrics_validation": comparison[(comparison["model"] == best) & (comparison["split"] == "validation")].iloc[0].to_dict(),
        "metrics_test": comparison[(comparison["model"] == best) & (comparison["split"] == "test")].iloc[0].to_dict(),
        "baseline_comparison": summary,
        "clip_rule": CLIP_RULE,
        "price_policy": "Last known price held constant during forecasting; no future prices are used.",
        "products_modelled": len(products),
        "model_rows": n_rows,
        "data_end_date": data_end,
        "closed_weekdays": closed_dows,
        "library_versions": {"scikit-learn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__,
                             **({"xgboost": __import__("xgboost").__version__} if HAS_XGBOOST else {})},
        "uncertainty": "No prediction intervals are produced (no validated uncertainty method implemented).",
    })
    bundle = {"model": result["final_model"], "model_name": best, "feature_columns": FEATURE_COLUMNS,
              "target": config.TARGET_COLUMN, "products": products, "closed_weekdays": closed_dows,
              "data_end_date": pd.Timestamp(data_end), "version": MODEL_VERSION, "trained_at": metadata["trained_at"]}
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.ARTIFACTS_DIR / ".demand_model.joblib.tmp"
    joblib.dump(bundle, tmp)
    os.replace(tmp, config.ARTIFACTS_DIR / "demand_model.joblib")
    atomic_write_json(config.ARTIFACTS_DIR / "model_metadata.json", metadata)
    atomic_write_json(config.ARTIFACTS_DIR / "best_params.json", {k: v["best_params"] for k, v in result["tuning"].items()})

    metrics_dir = config.REPORTS_DIR / "metrics"
    atomic_write_csv(metrics_dir / "model_comparison.csv", comparison.round(5))
    atomic_write_json(metrics_dir / "model_comparison.json", {
        "generated_at": metadata["trained_at"], "metric_explanations": METRIC_EXPLANATIONS,
        "best_model": best, "best_baseline": result["best_baseline_name"], "summary": summary,
        "rows": comparison.to_dict(orient="records"),
        "models": {**{k: v for k, v in MODEL_DESCRIPTIONS.items() if k in result["tuning"]},
                   **{k: v[1] for k, v in BASELINES.items()}},
    })
    atomic_write_parquet(config.PROCESSED_DATA_DIR / "test_predictions.parquet", result["test_predictions"])
    return metadata
