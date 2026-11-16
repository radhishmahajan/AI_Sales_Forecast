"""Model performance, comparison and explainability (all read from saved, real evaluation files)."""

from __future__ import annotations

from typing import Any

from app.utils.errors import NotReadyError
from ml import config
from ml.utils import read_json


def _need(path) -> Any:
    data = read_json(path)
    if data is None:
        raise NotReadyError("No trained model yet. Run the pipeline from the Dataset page.")
    return data


def performance() -> dict[str, Any]:
    meta = _need(config.ARTIFACTS_DIR / "model_metadata.json")
    evaluation = _need(config.REPORTS_DIR / "09_model_evaluation.json")
    comparison = _need(config.REPORTS_DIR / "metrics" / "model_comparison.json")
    return {
        "best_model": meta["model_name"],
        "best_model_description": meta.get("model_description"),
        "selection_rule": meta["selection_rule"],
        "trained_at": meta["trained_at"],
        "hyperparameters": meta["hyperparameters"],
        "all_tuning": {k: {"best_params": v["best_params"], "cv_mae": v["cv_mae"]} for k, v in meta["all_tuning"].items()},
        "loss_function_experiment": meta.get("loss_function_experiment", []),
        "loss_function_note": meta.get("loss_function_note"),
        "split": meta["split"],
        "metrics_validation": meta["metrics_validation"],
        "metrics_test": meta["metrics_test"],
        "baseline_comparison": meta["baseline_comparison"],
        "comparison": comparison["rows"],
        "model_descriptions": comparison.get("models", {}),
        "metric_explanations": comparison["metric_explanations"],
        "recursive_backtest_test": evaluation.get("recursive_backtest", []),
        "recursive_backtest_test_origin": evaluation.get("recursive_backtest_origin"),
        "recursive_backtest_validation": evaluation.get("recursive_backtest_validation", []),
        "recursive_backtest_validation_origin": evaluation.get("recursive_backtest_validation_origin"),
        "error_by_weekday": evaluation.get("error_by_weekday", []),
        "error_by_product_top20": evaluation.get("error_by_product_top20", []),
        "residuals": evaluation.get("residuals", {}),
        "products_modelled": meta["products_modelled"],
        "clip_rule": meta["clip_rule"],
        "price_policy": meta["price_policy"],
        "uncertainty": meta["uncertainty"],
        "final_fit": meta["final_fit"],
        "features": meta["features"],
        "source": "calculated from real held-out data",
    }


def feature_importance() -> dict[str, Any]:
    data = _need(config.ARTIFACTS_DIR / "feature_importance.json")
    fe = read_json(config.REPORTS_DIR / "04_feature_engineering_report.json") or {}
    data["feature_dictionary"] = fe.get("feature_dictionary", {})
    return data


def summary_or_none() -> dict[str, Any] | None:
    meta = read_json(config.ARTIFACTS_DIR / "model_metadata.json")
    if not meta:
        return None
    return {"best_model": meta["model_name"], "trained_at": meta["trained_at"], "metrics_test": meta["metrics_test"],
            "baseline_comparison": meta["baseline_comparison"], "products_modelled": meta["products_modelled"],
            "data_end_date": meta.get("data_end_date")}
