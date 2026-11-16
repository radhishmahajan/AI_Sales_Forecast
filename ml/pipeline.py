"""
END-TO-END PIPELINE — runs every stage in order and records progress in a status file.

    python -m ml.pipeline            # full run on data/raw/Online Retail.xlsx (~6-8 minutes)
    python -m ml.pipeline --fast     # quick smoke run (fewer tuning candidates) for testing

Stages: 1 load+validate -> 3 preprocess -> 2 EDA -> 4/5 features+split -> 6-8 train+tune
        -> 9 evaluate (+ recursive backtest) -> 10 explain -> catalog/ABC.
(EDA runs after the cleaning step because sales charts must use the cleaned transaction labels.)

The FastAPI backend starts this module as a separate process, so training never blocks the API.
Progress is written atomically to storage/pipeline_status.json after every step.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ml import config
from ml.utils import atomic_write_json, atomic_write_text, read_json, to_json_safe, utc_now_iso

logger = logging.getLogger("ml.pipeline")

STEPS: list[tuple[str, str]] = [
    ("load_validate", "Load & validate dataset"),
    ("preprocess", "Clean & preprocess"),
    ("eda", "Exploratory data analysis"),
    ("features", "Feature engineering & split"),
    ("train", "Train, tune & select models"),
    ("evaluate", "Evaluate on test period"),
    ("explain", "Explain model"),
    ("catalog", "Product catalog & ABC analysis"),
]


def status_path() -> Path:
    return config.STORAGE_DIR / "pipeline_status.json"


def read_status() -> dict[str, Any]:
    try:
        data = read_json(status_path(), default=None)
    except ValueError:
        data = None
    return data or {"state": "never_run", "steps": [{"name": n, "label": l, "state": "pending"} for n, l in STEPS]}


class StatusWriter:
    def __init__(self, run_id: str) -> None:
        self.status: dict[str, Any] = {
            "run_id": run_id, "state": "running", "pid": os.getpid(), "started_at": utc_now_iso(), "finished_at": None,
            "current_step": None, "error": None, "log": [],
            "steps": [{"name": n, "label": l, "state": "pending", "seconds": None} for n, l in STEPS],
        }
        self.flush()

    def flush(self) -> None:
        self.status["heartbeat"] = utc_now_iso()
        atomic_write_json(status_path(), self.status)

    def log(self, message: str) -> None:
        logger.info(message)
        self.status["log"] = (self.status["log"] + [f"{time.strftime('%H:%M:%S')} {message}"])[-60:]
        self.flush()

    def step(self, name: str, state: str, seconds: float | None = None) -> None:
        for s in self.status["steps"]:
            if s["name"] == name:
                s["state"] = state
                if seconds is not None:
                    s["seconds"] = round(seconds, 1)
        self.status["current_step"] = name if state == "running" else self.status["current_step"]
        self.flush()


def run_pipeline(fast: bool = False, top_n: int | None = None, dataset_path: str | None = None) -> dict[str, Any]:
    from ml import analytics, data_loader, eda, evaluate, explainability, feature_engineering, forecasting, preprocessing, train

    config.ensure_directories()
    writer = StatusWriter(uuid.uuid4().hex[:12])
    ctx: dict[str, Any] = {}

    def timed(name: str, fn: Callable[[], None]) -> None:
        writer.step(name, "running")
        writer.log(f"Started: {dict(STEPS)[name]}")
        t0 = time.time()
        fn()
        writer.step(name, "completed", time.time() - t0)
        writer.log(f"Finished: {dict(STEPS)[name]} ({time.time() - t0:.1f}s)")

    try:
        def s_load() -> None:
            result = data_loader.load_dataset(dataset_path)
            profile = data_loader.profile_dataset(result)
            data_loader.save_overview_report(profile)
            ctx["raw"] = result.df
            writer.log(f"Rows loaded: {len(result.df):,}")

        def s_pre() -> None:
            res = preprocessing.preprocess(ctx.pop("raw"))
            preprocessing.save_outputs(res)
            ctx["sales"], ctx["classified"] = res.sales, res.classified
            writer.log(f"Clean sale rows: {len(res.sales):,}")

        def s_eda() -> None:
            eda.run(ctx["sales"], ctx.pop("classified"))

        def s_feat() -> None:
            out = feature_engineering.run(ctx["sales"], top_n)
            ctx["features"], ctx["fe"] = out["model_data"], out
            writer.log(f"Model rows: {len(out['model_data']):,} for {len(out['products'])} products")

        def s_train() -> None:
            res = train.train_and_evaluate(ctx["features"], fast=fast, progress=writer.log)
            fe = ctx["fe"]
            meta = train.save_training_outputs(
                res, fe["split_info"], fe["products"], feature_engineering.closed_weekdays(fe["calendar"]),
                fe["calendar"]["Date"].max(), len(ctx["features"]))
            ctx["train"], ctx["meta"] = res, meta

        def s_eval() -> None:
            res, fe = ctx["train"], ctx["fe"]
            best = res["best_model_name"]
            origin = pd.Timestamp(fe["split_info"]["validation"]["end"])
            writer.log(f"Recursive backtest from {origin.date()} (model trained only up to that date)")
            horizon_table = forecasting.recursive_backtest(
                fe["panel"], res["eval_models"][best], feature_engineering.FEATURE_COLUMNS,
                feature_engineering.closed_weekdays(fe["calendar"]), origin)
            val_origin = pd.Timestamp(fe["split_info"]["train"]["end"])
            writer.log(f"Recursive backtest from {val_origin.date()} (validation period, model trained on training data only)")
            horizon_val = forecasting.recursive_backtest(
                fe["panel"], res["val_models"][best], feature_engineering.FEATURE_COLUMNS,
                feature_engineering.closed_weekdays(fe["calendar"]), val_origin)
            pred = res["test_predictions"]
            charts = evaluate.make_evaluation_charts(pred, res["comparison"], best, res["best_baseline_name"], horizon_table)
            by_product = evaluate.error_by_group(pred, best, "StockCode").sort_values("total_abs_error", ascending=False)
            by_dow = evaluate.error_by_group(pred.assign(day_of_week=pred["Date"].dt.day_name()), best, "day_of_week")
            week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            by_dow = by_dow.sort_values("day_of_week", key=lambda s: s.map(week.index)).reset_index(drop=True)
            report = {
                "generated_at": utc_now_iso(), "best_model": best, "best_baseline": res["best_baseline_name"],
                "summary": train.improvement_summary(res["comparison"], best, res["best_baseline_name"]),
                "metric_explanations": evaluate.METRIC_EXPLANATIONS,
                "comparison": res["comparison"].to_dict(orient="records"),
                "recursive_backtest": horizon_table.to_dict(orient="records"),
                "recursive_backtest_origin": origin,
                "recursive_backtest_validation": horizon_val.to_dict(orient="records"),
                "recursive_backtest_validation_origin": val_origin,
                "error_by_weekday": by_dow.to_dict(orient="records"),
                "error_by_product_top20": by_product.head(20).to_dict(orient="records"),
                "residuals": {
                    "mean": float((pred[best] - pred["actual"]).mean()),
                    "median": float((pred[best] - pred["actual"]).median()),
                    "histogram": _histogram(pred[best] - pred["actual"]),
                },
                "charts": charts,
            }
            atomic_write_json(config.REPORTS_DIR / "09_model_evaluation.json", to_json_safe(report))
            from ml.utils import atomic_write_csv
            atomic_write_csv(config.REPORTS_DIR / "metrics" / "recursive_backtest.csv", horizon_table.round(5))
            atomic_write_csv(config.REPORTS_DIR / "metrics" / "error_by_product.csv", by_product.round(5))

        def s_explain() -> None:
            res = ctx["train"]
            best = res["best_model_name"]
            result = explainability.explain_model(res["eval_models"][best], res["test_rows"], best,
                                                  sample_size=3000 if fast else 15000, n_repeats=2 if fast else 5)
            explainability.save_explainability(result)

        def s_catalog() -> None:
            analytics.run(ctx["sales"], ctx["fe"]["products"])

        for name, fn in (("load_validate", s_load), ("preprocess", s_pre), ("eda", s_eda), ("features", s_feat),
                         ("train", s_train), ("evaluate", s_eval), ("explain", s_explain), ("catalog", s_catalog)):
            timed(name, fn)

        writer.status.update({"state": "completed", "finished_at": utc_now_iso(), "current_step": None,
                              "result": {"best_model": ctx["meta"]["model_name"],
                                         "test_mae": ctx["meta"]["metrics_test"]["mae"],
                                         "test_wape_pct": ctx["meta"]["metrics_test"]["wape_pct"]}})
        writer.log("Pipeline completed successfully")
        return writer.status
    except Exception as exc:
        for s in writer.status["steps"]:
            if s["state"] == "running":
                s["state"] = "failed"
        writer.status.update({"state": "failed", "finished_at": utc_now_iso(), "error": f"{type(exc).__name__}: {exc}"})
        writer.log("FAILED: " + f"{type(exc).__name__}: {exc}")
        atomic_write_text(config.STORAGE_DIR / "pipeline_error.log", traceback.format_exc())
        raise


def _histogram(values: pd.Series, bins: int = 40) -> list[dict[str, float]]:
    v = values.clip(values.quantile(0.01), values.quantile(0.99))
    counts, edges = pd.cut(v, bins=bins, retbins=True)
    vc = counts.value_counts(sort=False)
    return [{"bin_start": float(edges[i]), "bin_end": float(edges[i + 1]), "count": int(c)} for i, c in enumerate(vc.values)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full ML pipeline.")
    parser.add_argument("--fast", action="store_true", help="Quick run with fewer tuning candidates (testing only)")
    parser.add_argument("--top-n", type=int, default=None, help="Number of products to model (default 500)")
    parser.add_argument("--dataset", default=None, help="Path to Online Retail.xlsx (default data/raw/)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", stream=sys.stdout)
    try:
        status = run_pipeline(fast=args.fast, top_n=args.top_n, dataset_path=args.dataset)
    except Exception as exc:
        print(f"PIPELINE FAILED: {exc}", file=sys.stderr)
        return 1
    print("Result:", status.get("result"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
