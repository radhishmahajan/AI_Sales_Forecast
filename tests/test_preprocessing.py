"""Stage 3 tests (synthetic fixtures only)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from ml import config
from ml.data_loader import coerce_types
from ml.preprocessing import TRANSACTION_TYPES, classify_transactions, normalise_description, preprocess


def typed(rows: list[tuple]) -> pd.DataFrame:
    df, _ = coerce_types(pd.DataFrame(rows, columns=list(config.REQUIRED_COLUMNS)))
    return df


T = datetime(2011, 3, 1, 10, 0)
T2 = datetime(2011, 3, 1, 11, 0)


def test_each_rule_assigns_expected_type() -> None:
    df = typed([
        ("536365", "85123A", "A", 6, T, 2.55, 17850, "UK"),             # SALE
        ("C536379", "85123A", "A", -3, T2, 2.55, 99999, "UK"),           # RETURN (no matching sale)
        ("C536380", "D", "Discount", -1, T2, 5.0, 17850, "UK"),          # CANCELLATION_NON_PRODUCT
        ("536381", "POST", "POSTAGE", 1, T, 18.0, 12583, "France"),      # NON_PRODUCT
        ("536382", "gift_0001_20", "Voucher", 1, T, 16.67, 12583, "UK"), # NON_PRODUCT (pattern)
        ("536383", "22139", None, 56, T, 0.0, None, "UK"),               # ZERO_PRICE
        ("536384", "21777", "damaged", -10, T, 0.0, None, "UK"),         # STOCK_ADJUSTMENT
        ("A563185", "B", "Adjust bad debt", 1, T, -11062.06, None, "UK"),# ACCOUNTING_ADJUSTMENT
        ("536385", "22086", "X", 0, T, 2.1, 1, "UK"),                    # INVALID (zero qty)
    ])
    got = classify_transactions(df)["TransactionType"].astype(str).tolist()
    assert got == ["SALE", "RETURN", "CANCELLATION_NON_PRODUCT", "NON_PRODUCT", "NON_PRODUCT", "ZERO_PRICE",
                   "STOCK_ADJUSTMENT", "ACCOUNTING_ADJUSTMENT", "INVALID"]


def test_full_reversal_marks_sale_but_partial_return_does_not() -> None:
    df = typed([
        ("581483", "23843", "BIRDIE", 80995, T, 2.08, 16446, "UK"),
        ("C581484", "23843", "BIRDIE", -80995, T2, 2.08, 16446, "UK"),
        ("581490", "22000", "OTHER", 10, T, 1.0, 16446, "UK"),
        ("C581491", "22000", "OTHER", -4, T2, 1.0, 16446, "UK"),     # partial return: sale stays SALE
    ])
    types = classify_transactions(df)["TransactionType"].astype(str).tolist()
    assert types == ["REVERSED_SALE", "RETURN", "SALE", "RETURN"]


def test_cancellation_before_sale_is_not_matched() -> None:
    df = typed([
        ("C1", "22000", "X", -5, T, 1.0, 1, "UK"),
        ("2", "22000", "X", 5, T2, 1.0, 1, "UK"),
    ])
    assert classify_transactions(df)["TransactionType"].astype(str).tolist() == ["RETURN", "SALE"]


def test_preprocess_report_accounts_for_every_row() -> None:
    rows = [
        ("1", "85123A", "pink  heart ", 6, T, 2.0, 1, "UK"),
        ("1", "85123A", "pink  heart ", 6, T, 2.0, 1, "UK"),   # duplicate
        ("2", "85123A", "PINK HEART", 4, T2, 2.0, 2, "UK"),
        ("3", "85123A", None, 3, T2, 2.0, 3, "UK"),             # missing description -> filled
        ("C4", "85123A", "PINK HEART", -1, T2, 2.0, 2, "UK"),
        ("5", "POST", "POSTAGE", 1, T, 18.0, 1, "UK"),
    ]
    res = preprocess(typed(rows))
    c = res.report["counts"]
    assert c["original_rows"] == 6 and c["duplicate_rows_removed"] == 1
    total_types = sum(v["rows"] for v in res.report["transaction_types"].values())
    assert total_types == c["rows_after_deduplication"] == 5
    assert c["retained_sale_rows"] == 3 and c["return_lines"] == 1 and c["non_product_lines"] == 1
    assert c["removed_rows_total"] == 6 - 3
    assert set(res.sales["Description"]) == {"PINK HEART"}
    assert res.sales["Revenue"].sum() == (6 + 4 + 3) * 2.0
    assert set(res.report["transaction_types"]) == set(TRANSACTION_TYPES)


def test_normalise_description() -> None:
    assert normalise_description(pd.Series(["  pink   Heart "])).iloc[0] == "PINK HEART"
