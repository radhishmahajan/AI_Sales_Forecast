"""
SYNTHETIC TEST DATA GENERATOR — FOR AUTOMATED TESTS ONLY.

Produces a small, clearly fake transaction table in the UCI column format so the complete
pipeline and API can be tested end-to-end in seconds without the real dataset.
Products are named 'SYNTHETIC TEST PRODUCT n'. Output only goes to pytest temp folders.
It is never used for reported results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml import config


def synthetic_transactions(n_products: int = 6, start: str = "2010-12-01", days: int = 200, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=days, freq="D")
    rows = []
    invoice = 600000
    for d in dates:
        if d.dayofweek == 5:  # like the real shop: closed on Saturdays
            continue
        for p in range(n_products):
            base = 3 + 2 * p
            if rng.random() < 0.6:
                qty = int(rng.poisson(base * (1.3 if d.dayofweek == 3 else 1.0))) + 1
                invoice += 1
                rows.append((str(invoice), f"9{p:04d}", f"SYNTHETIC TEST PRODUCT {p}", qty,
                             d + pd.Timedelta(hours=10), round(1.0 + 0.5 * p, 2), 10000 + p, "United Kingdom"))
    # a few special rows to exercise cleaning rules
    rows.append(("C700001", "90000", "SYNTHETIC TEST PRODUCT 0", -2, dates[50] + pd.Timedelta(hours=12), 1.0, 10000, "United Kingdom"))
    rows.append(("700002", "POST", "POSTAGE", 1, dates[51] + pd.Timedelta(hours=12), 18.0, 10001, "France"))
    rows.append(rows[0])  # exact duplicate
    return pd.DataFrame(rows, columns=list(config.REQUIRED_COLUMNS))
