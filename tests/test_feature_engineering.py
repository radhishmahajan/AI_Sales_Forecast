"""Stage 4/5 tests: target alignment and LEAKAGE prevention (synthetic data only)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml import config
from ml.feature_engineering import (FEATURE_COLUMNS, build_panel, build_store_calendar, chronological_split,
                                    daily_product_demand, make_features, model_rows, rolling_origin_folds)


def toy_panel(values_a: list[float], values_b: list[float] | None = None, start: str = "2011-01-03") -> pd.DataFrame:
    frames = []
    for code, vals in (("A", values_a), ("B", values_b)):
        if vals is None:
            continue
        dates = pd.date_range(start, periods=len(vals), freq="D")
        frames.append(pd.DataFrame({"StockCode": code, "Date": dates, "demand": np.array(vals, dtype=float),
                                    "avg_price": np.where(np.array(vals) > 0, 2.0, np.nan), "is_open": dates.dayofweek != 5}))
    return pd.concat(frames, ignore_index=True)


def test_target_is_same_day_demand_and_lags_are_past() -> None:
    vals = list(range(1, 41))
    f = make_features(toy_panel(vals))
    row = f.iloc[30]
    assert row[config.TARGET_COLUMN] == vals[30]
    assert row["lag_1"] == vals[29] and row["lag_7"] == vals[23] and row["lag_28"] == vals[2]
    assert row["rolling_mean_7"] == np.mean(vals[23:30])        # D-7..D-1, NOT including D
    assert row["rolling_max_7"] == max(vals[23:30])
    assert row["hist_mean_demand"] == np.mean(vals[:30])


def test_changing_future_demand_never_changes_past_features() -> None:
    vals = list(np.random.default_rng(0).poisson(5, 60).astype(float))
    base = make_features(toy_panel(vals))
    changed_vals = vals.copy()
    changed_vals[45:] = [999.0] * 15                               # tamper with the "future"
    changed = make_features(toy_panel(changed_vals))
    # every feature for rows up to and including day 45 must be identical (day 45 uses data up to day 44)
    pd.testing.assert_frame_equal(base.loc[:45, FEATURE_COLUMNS], changed.loc[:45, FEATURE_COLUMNS])
    assert changed.loc[46, "lag_1"] == 999.0                       # ...and day 46 legitimately sees day 45


def test_features_are_computed_per_product() -> None:
    f = make_features(toy_panel([1.0] * 35, [100.0] * 35))
    a = f[f["StockCode"] == "A"].iloc[0]
    b = f[f["StockCode"] == "B"].iloc[0]
    assert np.isnan(a["lag_1"]) and np.isnan(b["lag_1"])          # B's first row does not see A's last row
    assert f[f["StockCode"] == "B"]["rolling_mean_7"].dropna().eq(100.0).all()


def test_price_feature_uses_only_past_prices() -> None:
    p = toy_panel([5.0] * 35)
    p.loc[20, "avg_price"] = 10.0
    f = make_features(p)
    assert f.loc[20, "last_known_price"] == 2.0                    # price of day 20 not visible on day 20
    assert f.loc[21, "last_known_price"] == 10.0


def test_panel_window_and_zero_fill(sample_sales: pd.DataFrame) -> None:
    cal = build_store_calendar(sample_sales)
    daily = daily_product_demand(sample_sales)
    panel = build_panel(daily, cal, ["90000"])
    first, last = daily.loc[daily["StockCode"] == "90000", "Date"].agg(["min", "max"])
    assert panel["Date"].min() == first and panel["Date"].max() == last   # no rows outside the window
    assert len(panel) == (last - first).days + 1                          # consecutive calendar days
    assert (panel.loc[~panel["Date"].isin(daily["Date"]), "demand"] == 0).all()
    assert not panel.loc[panel["Date"].dt.dayofweek == 5, "is_open"].any()


def test_split_is_chronological_by_date(sample_sales: pd.DataFrame) -> None:
    cal = build_store_calendar(sample_sales)
    daily = daily_product_demand(sample_sales)
    feats = make_features(build_panel(daily, cal, daily["StockCode"].unique().tolist()))
    data = feats[model_rows(feats)]
    split, info = chronological_split(data)
    d = data.assign(split=split.values)
    assert d.loc[d["split"] == "train", "Date"].max() < d.loc[d["split"] == "validation", "Date"].min()
    assert d.loc[d["split"] == "validation", "Date"].max() < d.loc[d["split"] == "test", "Date"].min()
    assert d.groupby("Date")["split"].nunique().max() == 1          # all products on a date share a split
    assert d["is_open"].all() and (d["product_age_days"] >= config.MIN_HISTORY_DAYS).all()


def test_rolling_origin_folds_never_validate_on_the_past() -> None:
    dates = pd.Series(pd.date_range("2011-01-01", periods=40).repeat(3))
    for tr, va in rolling_origin_folds(dates, 3):
        assert dates.iloc[tr].max() < dates.iloc[va].min()
