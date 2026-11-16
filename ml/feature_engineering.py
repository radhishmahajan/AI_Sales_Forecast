"""
STAGES 4 & 5 — Feature engineering and time-series data preparation.

From transactions to a supervised learning table
-------------------------------------------------
1. Aggregate SALE rows into DAILY demand per product (units sold per StockCode per date).
2. Build a product-day PANEL over each product's observation window
   (first sale date -> last sale date). Inside the window, a calendar day without a sale
   counts as 0 demand. Days before the first or after the last sale are NOT created,
   because we cannot be sure the product was on offer then.
3. Mark each date as OPEN or CLOSED using the store calendar: a date is open if the shop
   recorded any sale at all that day. The shop never trades on Saturdays and closed for
   Christmas and some UK bank holidays. Closed days stay in the series as 0 (so lag 7 is
   always "same weekday last week"), but they are NOT used as training/evaluation rows,
   because demand cannot be observed when the shop is shut.
4. Create features for every row dated D using ONLY data up to D-1.

Target alignment (verified by unit tests)
-----------------------------------------
For a row dated D, the target NEXT_DAY_DEMAND is the demand on D, and the forecast is made
at the end of D-1 (the "forecast origin"). So NEXT_DAY_DEMAND is literally "the next day's
demand" relative to the information used by the features.

Leakage prevention
------------------
* Data sorted by product and date before any shift/rolling.
* All demand-based features use demand.shift(1) per product (shift BEFORE rolling).
* Prices are only known from past sales: last known price (shift(1) + forward-fill).
  At forecast time the last known price is held constant (no future prices are used).
* Calendar features of D (weekday, month...) are known in advance, so they are allowed.
* Exactly the same make_features() function is used for training and for recursive forecasting.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from ml import config
from ml.utils import atomic_write_json, atomic_write_parquet, atomic_write_text, read_json, to_json_safe, utc_now_iso

logger = logging.getLogger(__name__)

FEATURE_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Feature dictionary (every model feature is explained here)
# ---------------------------------------------------------------------------
FEATURE_DICTIONARY: dict[str, dict[str, str]] = {
    "lag_1": {"family": "lag", "description": "Units sold on the previous calendar day (D-1). 0 if the shop was closed."},
    "lag_7": {"family": "lag", "description": "Units sold 7 days earlier (same weekday last week)."},
    "lag_14": {"family": "lag", "description": "Units sold 14 days earlier."},
    "lag_28": {"family": "lag", "description": "Units sold 28 days earlier."},
    "last_open_day_demand": {"family": "lag", "description": "Units sold on the most recent day the shop was open before D (handles Sunday after a closed Saturday)."},
    "prev_day_open": {"family": "calendar", "description": "1 if the shop was open on D-1, else 0."},
    "rolling_mean_7": {"family": "rolling", "description": "Mean daily units over D-7..D-1 (shift(1) then rolling 7)."},
    "rolling_mean_14": {"family": "rolling", "description": "Mean daily units over D-14..D-1."},
    "rolling_mean_28": {"family": "rolling", "description": "Mean daily units over D-28..D-1."},
    "rolling_std_7": {"family": "rolling", "description": "Standard deviation of daily units over D-7..D-1 (recent volatility)."},
    "rolling_max_7": {"family": "rolling", "description": "Largest daily units over D-7..D-1 (recent bulk orders)."},
    "day": {"family": "calendar", "description": "Day of month of D (1-31)."},
    "month": {"family": "calendar", "description": "Month of D (1-12)."},
    "year": {"family": "calendar", "description": "Year of D."},
    "day_of_week": {"family": "calendar", "description": "Weekday of D (0=Monday ... 6=Sunday)."},
    "week_of_year": {"family": "calendar", "description": "ISO week number of D."},
    "is_weekend": {"family": "calendar", "description": "1 if D is Saturday or Sunday."},
    "is_month_start": {"family": "calendar", "description": "1 if D is the first day of a month."},
    "is_month_end": {"family": "calendar", "description": "1 if D is the last day of a month."},
    "last_known_price": {"family": "price", "description": "Most recent average selling price observed BEFORE D (held constant into the future at forecast time)."},
    "avg_price_28": {"family": "price", "description": "Average daily selling price over sale days in D-28..D-1 (the 'average daily price' feature, using only past prices)."},
    "price_change_pct": {"family": "price", "description": "% difference between the last known price and the 28-day average price (recent price change)."},
    "sales_frequency": {"family": "history", "description": "Share of days in the product's history up to D-1 that had a sale (how regularly it sells)."},
    "days_since_prev_sale": {"family": "history", "description": "Calendar days between D and the most recent sale before D."},
    "hist_mean_demand": {"family": "history", "description": "Average daily units over the product's whole history up to D-1."},
    "hist_std_demand": {"family": "history", "description": "Standard deviation of daily units over the product's history up to D-1 (demand variability)."},
    "product_age_days": {"family": "history", "description": "Days since the product's first sale."},
}
FEATURE_COLUMNS: list[str] = list(FEATURE_DICTIONARY.keys())


# ===========================================================================
# 1. Calendar and daily demand
# ===========================================================================
def build_store_calendar(sales: pd.DataFrame) -> pd.DataFrame:
    """Every calendar date in the data period with an is_open flag."""
    open_days = pd.DatetimeIndex(sales["Date"].unique())
    dates = pd.date_range(open_days.min(), open_days.max(), freq="D")
    cal = pd.DataFrame({"Date": dates})
    cal["is_open"] = cal["Date"].isin(open_days)
    return cal


def closed_weekdays(calendar: pd.DataFrame) -> list[int]:
    """Weekdays on which the shop NEVER traded (used to mark future closed days)."""
    open_dow = set(calendar.loc[calendar["is_open"], "Date"].dt.dayofweek)
    return [d for d in range(7) if d not in open_dow]


def daily_product_demand(sales: pd.DataFrame) -> pd.DataFrame:
    """Units, revenue and average price per product per day (SALE rows only)."""
    g = sales.groupby(["StockCode", "Date"], observed=True)
    daily = pd.DataFrame(
        {"demand": g["Quantity"].sum().astype("float64"), "revenue": g["Revenue"].sum(), "orders": g["InvoiceNo"].nunique()}
    ).reset_index()
    daily["avg_price"] = daily["revenue"] / daily["demand"]
    daily["StockCode"] = daily["StockCode"].astype(str)
    return daily


def select_model_products(daily: pd.DataFrame, top_n: int | None = None) -> list[str]:
    """Products with the most sale days (ties: more units). These have enough history to model."""
    top_n = config.MODEL_TOP_N_PRODUCTS if top_n is None else top_n
    stats = daily.groupby("StockCode").agg(sale_days=("demand", "size"), units=("demand", "sum"))
    stats = stats.sort_values(["sale_days", "units"], ascending=False)
    return stats.head(top_n).index.astype(str).tolist()


def build_panel(daily: pd.DataFrame, calendar: pd.DataFrame, products: list[str]) -> pd.DataFrame:
    """Product x calendar-day panel over each product's observation window."""
    sub = daily[daily["StockCode"].isin(products)]
    bounds = sub.groupby("StockCode")["Date"].agg(["min", "max"])
    pieces = []
    for code, (first, last) in bounds.iterrows():
        dates = pd.date_range(first, last, freq="D")
        pieces.append(pd.DataFrame({"StockCode": code, "Date": dates}))
    panel = pd.concat(pieces, ignore_index=True)
    panel = panel.merge(sub[["StockCode", "Date", "demand", "avg_price"]], on=["StockCode", "Date"], how="left")
    panel["demand"] = panel["demand"].fillna(0.0)
    panel = panel.merge(calendar, on="Date", how="left")
    panel["is_open"] = panel["is_open"].fillna(False).astype(bool)
    return panel.sort_values(["StockCode", "Date"]).reset_index(drop=True)


# ===========================================================================
# 2. Features (shared by training and inference)
# ===========================================================================
def _grouped_rolling(series: pd.Series, keys: pd.Series, window: int, how: str) -> pd.Series:
    roll = series.groupby(keys, sort=False).rolling(window, min_periods=window)
    out = getattr(roll, how)()
    return out.reset_index(level=0, drop=True).reindex(series.index)


def make_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Add every feature + the target to a panel (columns: StockCode, Date, demand, avg_price, is_open).

    The panel MUST be sorted by StockCode then Date with consecutive calendar days per product.
    Rows where demand is NaN (future days during recursive forecasting) are allowed: features
    for a row only use earlier rows, so they are still well defined.
    """
    df = panel.sort_values(["StockCode", "Date"]).reset_index(drop=True).copy()
    key = df["StockCode"]
    g = df.groupby("StockCode", sort=False)

    demand = df["demand"].astype("float64")
    prev = g["demand"].shift(1)                     # <- the ONE shift that prevents leakage
    df["lag_1"] = prev
    for lag in config.LAG_DAYS:
        if lag != 1:
            df[f"lag_{lag}"] = g["demand"].shift(lag)

    open_demand = demand.where(df["is_open"])
    df["last_open_day_demand"] = open_demand.groupby(key, sort=False).shift(1)
    df["last_open_day_demand"] = df["last_open_day_demand"].groupby(key, sort=False).ffill()
    df["prev_day_open"] = g["is_open"].shift(1).astype("float64")

    for w in config.ROLLING_MEAN_WINDOWS:
        df[f"rolling_mean_{w}"] = _grouped_rolling(prev, key, w, "mean")
    df["rolling_std_7"] = _grouped_rolling(prev, key, 7, "std")
    df["rolling_max_7"] = _grouped_rolling(prev, key, 7, "max")

    date = df["Date"]
    df["day"] = date.dt.day
    df["month"] = date.dt.month
    df["year"] = date.dt.year
    df["day_of_week"] = date.dt.dayofweek
    df["week_of_year"] = date.dt.isocalendar().week.astype("int64").to_numpy()
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_month_start"] = date.dt.is_month_start.astype(int)
    df["is_month_end"] = date.dt.is_month_end.astype(int)

    prev_price = g["avg_price"].shift(1)
    df["last_known_price"] = prev_price.groupby(key, sort=False).ffill()
    sum28 = _grouped_rolling(prev_price.fillna(0.0), key, 28, "sum")
    cnt28 = _grouped_rolling(prev_price.notna().astype(float), key, 28, "sum")
    df["avg_price_28"] = (sum28 / cnt28.replace(0, np.nan))
    df["avg_price_28"] = df["avg_price_28"].fillna(df["last_known_price"])
    df["price_change_pct"] = 100 * (df["last_known_price"] - df["avg_price_28"]) / df["avg_price_28"]

    # expanding history features via cumulative sums (fast and leakage-free: they use prev)
    n_hist = prev.notna().astype(float).groupby(key, sort=False).cumsum()
    csum = prev.fillna(0.0).groupby(key, sort=False).cumsum()
    csq = (prev.fillna(0.0) ** 2).groupby(key, sort=False).cumsum()
    csale = (prev.fillna(0.0) > 0).astype(float).groupby(key, sort=False).cumsum()
    mean = csum / n_hist.replace(0, np.nan)
    var = (csq - n_hist * mean**2) / (n_hist - 1).replace(0, np.nan)
    df["hist_mean_demand"] = mean
    df["hist_std_demand"] = np.sqrt(var.clip(lower=0))
    df["sales_frequency"] = csale / n_hist.replace(0, np.nan)

    sale_date = df["Date"].where(demand > 0)
    last_sale_before = sale_date.groupby(key, sort=False).shift(1)
    last_sale_before = last_sale_before.groupby(key, sort=False).ffill()
    df["days_since_prev_sale"] = (df["Date"] - last_sale_before).dt.days.astype("float64")

    first_date = g["Date"].transform("min")
    df["product_age_days"] = (df["Date"] - first_date).dt.days

    df[config.TARGET_COLUMN] = demand
    return df


def model_rows(features: pd.DataFrame) -> pd.Series:
    """Rows usable for training/evaluation: shop open, >= MIN_HISTORY_DAYS of history, target known."""
    return (
        features["is_open"]
        & (features["product_age_days"] >= config.MIN_HISTORY_DAYS)
        & features[config.TARGET_COLUMN].notna()
        & features["lag_28"].notna()
    )


# ===========================================================================
# 3. Chronological split (by DATE, never by row)
# ===========================================================================
def chronological_split(features: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    """Assign 'train' / 'validation' / 'test' by unique calendar date.

    All products on the same date land in the same split, and every validation date is later
    than every training date, and every test date later than every validation date.
    """
    dates = np.array(sorted(features["Date"].unique()))
    n = len(dates)
    train_end = dates[int(np.floor(config.TRAIN_FRACTION * n)) - 1]
    val_end = dates[int(np.floor((config.TRAIN_FRACTION + config.VALIDATION_FRACTION) * n)) - 1]
    split = pd.Series(np.where(features["Date"] <= train_end, "train",
                               np.where(features["Date"] <= val_end, "validation", "test")), index=features.index)
    info = {
        "unit": "unique dates of model rows",
        "n_dates": int(n),
        "train": {"start": dates[0], "end": train_end},
        "validation": {"start": dates[dates > train_end][0], "end": val_end},
        "test": {"start": dates[dates > val_end][0], "end": dates[-1]},
        "rows": split.value_counts().to_dict(),
    }
    return split, to_json_safe(info)


def rolling_origin_folds(dates: pd.Series, n_folds: int | None = None) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window, date-based CV folds inside the training period (for tuning).

    The training dates are cut into (n_folds + 1) blocks. Fold k trains on blocks 0..k and
    validates on block k+1 — like re-running the forecast at several past dates.
    Returns positional index arrays suitable for scikit-learn's `cv=` argument.
    """
    n_folds = config.CV_FOLDS if n_folds is None else n_folds
    uniq = np.array(sorted(pd.unique(dates)))
    blocks = np.array_split(uniq, n_folds + 1)
    values = dates.to_numpy()
    folds = []
    for k in range(n_folds):
        train_last = blocks[k][-1]
        val_dates = blocks[k + 1]
        tr = np.where(values <= train_last)[0]
        va = np.where((values >= val_dates[0]) & (values <= val_dates[-1]))[0]
        folds.append((tr, va))
    return folds


# ===========================================================================
# 4. Stage runner
# ===========================================================================
def build_dataset(sales: pd.DataFrame, top_n: int | None = None) -> dict[str, Any]:
    calendar = build_store_calendar(sales)
    daily = daily_product_demand(sales)
    products = select_model_products(daily, top_n)
    panel = build_panel(daily, calendar, products)
    features = make_features(panel)
    usable = model_rows(features)
    data = features[usable].copy()
    split, split_info = chronological_split(data)
    data["split"] = split.values
    return {"calendar": calendar, "daily": daily, "products": products, "panel": panel, "model_data": data, "split_info": split_info}


def feature_dictionary_markdown() -> str:
    lines = ["# Feature Dictionary\n",
             f"Target: **{config.TARGET_COLUMN}** — units of a product sold on date D (the day after the forecast origin D-1).\n",
             "All features for a row dated D use information available at the end of D-1 (or calendar facts about D).\n",
             "| Feature | Family | Meaning |", "|---|---|---|"]
    lines += [f"| `{k}` | {v['family']} | {v['description']} |" for k, v in FEATURE_DICTIONARY.items()]
    return "\n".join(lines) + "\n"


def run(sales: pd.DataFrame | None = None, top_n: int | None = None) -> dict[str, Any]:
    from ml.preprocessing import load_clean_sales

    sales = load_clean_sales() if sales is None else sales
    out = build_dataset(sales, top_n)
    p = config.PROCESSED_DATA_DIR
    atomic_write_parquet(p / "daily_product_demand.parquet", out["daily"])
    atomic_write_parquet(p / "store_calendar.parquet", out["calendar"])
    atomic_write_parquet(p / "demand_panel.parquet", out["panel"])
    atomic_write_parquet(p / "features.parquet", out["model_data"])
    atomic_write_json(config.ARTIFACTS_DIR / "feature_columns.json", {
        "target": config.TARGET_COLUMN, "features": FEATURE_COLUMNS, "version": FEATURE_VERSION,
    })
    data = out["model_data"]
    summary = {
        "report": "Stage 4/5 - Feature engineering and time-series preparation",
        "generated_at": utc_now_iso(),
        "feature_version": FEATURE_VERSION,
        "products_modelled": len(out["products"]),
        "selection_rule": f"Top {len(out['products'])} products by number of days with sales (ties: units sold).",
        "panel_rows": int(len(out["panel"])),
        "model_rows": int(len(data)),
        "closed_weekdays": closed_weekdays(out["calendar"]),
        "closed_dates_in_period": out["calendar"].loc[~out["calendar"]["is_open"], "Date"].dt.strftime("%Y-%m-%d").tolist(),
        "split": out["split_info"],
        "target_stats": data[config.TARGET_COLUMN].describe().to_dict(),
        "zero_target_share": float((data[config.TARGET_COLUMN] == 0).mean()),
        "feature_columns": FEATURE_COLUMNS,
        "feature_dictionary": FEATURE_DICTIONARY,
        "assumptions": [
            "Observation window per product = first sale date to last sale date; no rows outside it.",
            "Inside the window, a day without a sale is 0 demand.",
            "Closed days (no sale anywhere in the shop) stay in the series as 0 but are not training rows.",
            f"Rows need at least {config.MIN_HISTORY_DAYS} days of product history so every lag exists.",
            "Prices: only past prices are used; the last known price is held constant when forecasting.",
        ],
    }
    atomic_write_json(config.REPORTS_DIR / "04_feature_engineering_report.json", summary)
    atomic_write_text(config.PROJECT_ROOT / "docs" / "FEATURE_DICTIONARY.md", feature_dictionary_markdown())
    return {**out, "summary": to_json_safe(summary)}


def load_feature_columns() -> list[str]:
    meta = read_json(config.ARTIFACTS_DIR / "feature_columns.json")
    if not meta:
        raise FileNotFoundError("artifacts/feature_columns.json is missing. Run the training pipeline first.")
    return list(meta["features"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run()
    s = res["summary"]
    print(f"Products: {s['products_modelled']}, panel rows: {s['panel_rows']:,}, model rows: {s['model_rows']:,}")
    print("Split:", s["split"])
    print("Zero-demand share of targets:", round(s["zero_target_share"], 3))
