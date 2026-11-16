"""
STAGE 10 — Model explainability.

Two complementary views:
1. Permutation importance (model-agnostic): shuffle one feature on the TEST rows and measure
   how much the MAE gets worse. A big increase = the model relies heavily on that feature.
   It works the same for Linear Regression, Random Forest, HistGradientBoosting and XGBoost,
   so models can be compared fairly.
2. Direction of effect: rank correlation between each feature and the model's predictions,
   so we can say "higher recent average -> higher forecast" in business language.

Importances are also summed by feature family (lag, rolling, calendar, price, history).
SHAP is optional in the brief and not used, to keep the dependency list small.
"""

from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402

from ml import config  # noqa: E402
from ml.feature_engineering import FEATURE_COLUMNS, FEATURE_DICTIONARY  # noqa: E402
from ml.utils import atomic_write_json, to_json_safe, utc_now_iso  # noqa: E402

FAMILY_MEANING = {
    "lag": "recent individual days of demand",
    "rolling": "recent averages / volatility of demand",
    "calendar": "the date (weekday, month, ...)",
    "price": "recent selling prices",
    "history": "the product's long-run sales behaviour",
}


def explain_model(model: Any, test_rows: pd.DataFrame, model_name: str, sample_size: int = 15000, n_repeats: int = 5) -> dict[str, Any]:
    sample = test_rows.sample(n=min(sample_size, len(test_rows)), random_state=config.RANDOM_SEED)
    X, y = sample[FEATURE_COLUMNS], sample[config.TARGET_COLUMN]
    result = permutation_importance(model, X, y, scoring="neg_mean_absolute_error", n_repeats=n_repeats,
                                    random_state=config.RANDOM_SEED, n_jobs=1)
    imp = pd.DataFrame({
        "feature": FEATURE_COLUMNS,
        "importance_mae_increase": result.importances_mean,
        "importance_std": result.importances_std,
    })
    imp["family"] = imp["feature"].map(lambda f: FEATURE_DICTIONARY[f]["family"])
    total = imp["importance_mae_increase"].clip(lower=0).sum()
    imp["importance_share_pct"] = 100 * imp["importance_mae_increase"].clip(lower=0) / total if total > 0 else 0.0

    preds = np.clip(model.predict(X), 0, None)
    pred_s = pd.Series(preds, index=X.index)
    directions = {}
    for f in FEATURE_COLUMNS:
        col = X[f]
        directions[f] = float(col.rank().corr(pred_s.rank())) if col.nunique() > 1 else 0.0
    imp["direction_rank_corr"] = imp["feature"].map(directions)
    imp = imp.sort_values("importance_mae_increase", ascending=False).reset_index(drop=True)

    fam = imp.groupby("family")["importance_share_pct"].sum().sort_values(ascending=False)

    explanations = []
    for _, r in imp.head(5).iterrows():
        d = r["direction_rank_corr"]
        direction = ("higher values push the forecast UP" if d > 0.1 else
                     "higher values push the forecast DOWN" if d < -0.1 else "no simple up/down relationship")
        explanations.append(
            f"{r['feature']} ({r['importance_share_pct']:.1f}% of importance): {FEATURE_DICTIONARY[r['feature']]['description']} "
            f"Shuffling it raises test MAE by {r['importance_mae_increase']:.2f} units/day; {direction} (rank corr {d:+.2f})."
        )
    top_family = fam.index[0]
    summary = (f"The {model_name} model bases its forecast mainly on {FAMILY_MEANING.get(top_family, top_family)} "
               f"({fam.iloc[0]:.0f}% of total importance). "
               + "; ".join(f"{k}: {v:.0f}%" for k, v in fam.items()) + ".")
    return to_json_safe({
        "generated_at": utc_now_iso(),
        "model_name": model_name,
        "method": f"Permutation importance on {len(sample):,} test rows, {n_repeats} repeats, metric = increase in MAE.",
        "features": imp.to_dict(orient="records"),
        "families": fam.round(2).to_dict(),
        "business_summary": summary,
        "top_feature_explanations": explanations,
    })


def save_explainability(result: dict[str, Any]) -> None:
    atomic_write_json(config.ARTIFACTS_DIR / "feature_importance.json", result)
    atomic_write_json(config.REPORTS_DIR / "10_explainability.json", result)
    imp = pd.DataFrame(result["features"]).head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(imp["feature"], imp["importance_mae_increase"], xerr=imp["importance_std"], color="#4C72B0")
    ax.set_title(f"Permutation feature importance ({result['model_name']}, test period)")
    ax.set_xlabel("Increase in MAE when the feature is shuffled (units/day)")
    ax.set_ylabel("Feature")
    fig.tight_layout()
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(config.FIGURES_DIR / "10_feature_importance.png", dpi=130)
    plt.close(fig)
    fam = pd.Series(result["families"]).sort_values()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(fam.index, fam.values, color="#55A868")
    ax.set_title("Importance by feature family")
    ax.set_xlabel("Share of total importance (%)")
    ax.set_ylabel("Feature family")
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / "10_feature_family_importance.png", dpi=130)
    plt.close(fig)
