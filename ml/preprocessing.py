"""
STAGE 3 — Data cleaning and preprocessing.

Simple idea: label every invoice line with WHAT it is before deciding what to use it for.
Nothing is silently dropped. Every row ends up in exactly one TransactionType, and the
preprocessing report counts each one, so every exclusion can be traced.

TransactionType (mutually exclusive, applied in this priority order)
---------------------------------------------------------------------
INVALID                 Missing/unparseable date, missing StockCode, zero or missing quantity.
CANCELLATION_NON_PRODUCT Line on a 'C' invoice for a non-product code (discount, postage refund...).
RETURN                  Line on a 'C' invoice for a real product (goods cancelled/returned, negative qty).
ACCOUNTING_ADJUSTMENT   Invoices starting with 'A' ("Adjust bad debt", negative price).
STOCK_ADJUSTMENT        Negative quantity on a normal invoice with zero price (damaged, lost, "check").
NON_PRODUCT             Postage, carriage, bank charges, Amazon fees, manual entries, gift vouchers...
ZERO_PRICE              Positive quantity but price <= 0: no money changed hands (samples, fixes).
REVERSED_SALE           A sale fully reversed later by a matching cancellation (same customer,
                        product and quantity) — the order was never fulfilled.
SALE                    Everything else: a real, fulfilled product sale. THIS is our demand.

FORECASTING TARGET (fixed policy, used in training AND inference)
    Gross fulfilled demand = sum of Quantity over SALE rows, per product per day.
    Returns are NOT subtracted (they don't tell us how much stock customers asked for);
    they are counted separately. Only sale lines explicitly reversed in full are excluded.

Exact duplicate rows (identical in all 8 columns, including the minute) are removed first:
they are almost certainly double entries.

Outliers are INVESTIGATED and FLAGGED (IsExtremeQuantity), not deleted: wholesale customers
legitimately buy thousands of units. The two famous extreme lines (80,995 and 74,215 units)
are handled by the REVERSED_SALE rule because they were cancelled minutes later.
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ml import config
from ml.utils import atomic_write_csv, atomic_write_json, atomic_write_parquet, atomic_write_text, to_json_safe, utc_now_iso

logger = logging.getLogger(__name__)

# Codes that are not physical products. Found by inspecting every StockCode that does not
# follow the normal "5 digits + optional letters" pattern (see Stage 1 report).
NON_PRODUCT_CODES: frozenset[str] = frozenset(
    {"POST", "DOT", "M", "C2", "D", "S", "B", "BANK CHARGES", "AMAZONFEE", "CRUK"}
)
NON_PRODUCT_PATTERNS: tuple[re.Pattern[str], ...] = (re.compile(r"^gift_", re.IGNORECASE),)

TRANSACTION_TYPES: tuple[str, ...] = (
    "SALE",
    "REVERSED_SALE",
    "RETURN",
    "CANCELLATION_NON_PRODUCT",
    "STOCK_ADJUSTMENT",
    "ACCOUNTING_ADJUSTMENT",
    "NON_PRODUCT",
    "ZERO_PRICE",
    "INVALID",
)

TYPE_EXPLANATIONS: dict[str, str] = {
    "SALE": "Real fulfilled product sale (positive quantity and price). Used for demand and revenue.",
    "REVERSED_SALE": "Sale cancelled in full later by the same customer (same product and quantity). Excluded from demand.",
    "RETURN": "Product line on a cancellation ('C') invoice: goods returned/cancelled. Tracked separately.",
    "CANCELLATION_NON_PRODUCT": "Cancellation line for discounts, postage, fees. Not product demand.",
    "STOCK_ADJUSTMENT": "Negative quantity with zero price on a normal invoice (damaged, lost, stock checks).",
    "ACCOUNTING_ADJUSTMENT": "Bad-debt adjustment invoices starting with 'A'. Not sales.",
    "NON_PRODUCT": "Postage, carriage, bank charges, marketplace fees, manual lines, gift vouchers.",
    "ZERO_PRICE": "Positive quantity with zero price: no revenue, often samples or data fixes.",
    "INVALID": "Missing/invalid timestamp, StockCode or quantity.",
}

PREPROCESSING_VERSION = "1.0"


@dataclass
class PreprocessingResult:
    classified: pd.DataFrame          # every (de-duplicated) row with TransactionType + flags
    sales: pd.DataFrame               # SALE rows only — the cleaned sales dataset
    catalog: pd.DataFrame             # one row per product
    report: dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# Helper rules (small, testable functions)
# ===========================================================================
def normalise_description(text: pd.Series) -> pd.Series:
    """Upper-case, trim and collapse repeated spaces: 'Pink  heart ' -> 'PINK HEART'."""
    return text.astype("string").str.upper().str.replace(r"\s+", " ", regex=True).str.strip().replace("", pd.NA)


def is_non_product_code(stock: pd.Series) -> pd.Series:
    s = stock.astype("string").fillna("").str.strip()
    mask = s.str.upper().isin({c.upper() for c in NON_PRODUCT_CODES})
    for pattern in NON_PRODUCT_PATTERNS:
        mask |= s.str.match(pattern)
    return mask.astype(bool)


def find_reversed_sales(df: pd.DataFrame, candidate_sale: pd.Series, is_return: pd.Series) -> pd.Series:
    """Mark sale lines that a later cancellation reverses in full.

    Match rule: same CustomerID, same StockCode, cancelled quantity == sold quantity, and the
    cancellation happened at or after the sale. Each cancellation is matched to the most
    recent such sale (pandas.merge_asof, direction='backward'); each sale is matched at most once.
    Rows without CustomerID cannot be matched safely, so they are never marked.
    """
    reversed_mask = pd.Series(False, index=df.index)
    cols = ["CustomerID", "StockCode", "Quantity", "InvoiceDate"]
    sales = df.loc[candidate_sale & df["CustomerID"].notna(), cols].copy()
    cancels = df.loc[is_return & df["CustomerID"].notna(), cols].copy()
    if sales.empty or cancels.empty:
        return reversed_mask

    for frame in (sales, cancels):
        frame["CustomerID"] = frame["CustomerID"].astype("int64")
        frame["StockCode"] = frame["StockCode"].astype(str)
        frame["AbsQty"] = frame["Quantity"].astype("int64").abs()
    sales["sale_index"] = sales.index
    sales = sales.sort_values("InvoiceDate")
    cancels = cancels.sort_values("InvoiceDate")

    matched = pd.merge_asof(
        cancels[["InvoiceDate", "CustomerID", "StockCode", "AbsQty"]],
        sales[["InvoiceDate", "CustomerID", "StockCode", "AbsQty", "sale_index"]],
        on="InvoiceDate",
        by=["CustomerID", "StockCode", "AbsQty"],
        direction="backward",
        allow_exact_matches=True,
    )
    idx = matched["sale_index"].dropna().astype("int64").unique()
    reversed_mask.loc[idx] = True
    return reversed_mask


def classify_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Add TransactionType to every row (no rows removed). Expects Stage-1 typed columns."""
    out = df.copy()
    invoice = out["InvoiceNo"].astype("string").fillna("").str.upper()
    qty = out["Quantity"].astype("float64")
    price = out["UnitPrice"].astype("float64")
    non_product = is_non_product_code(out["StockCode"])

    invalid = out["InvoiceDate"].isna() | out["StockCode"].isna() | qty.isna() | (qty == 0) | price.isna()
    is_c = invoice.str.startswith("C")
    is_a = invoice.str.startswith("A")

    ttype = pd.Series("SALE", index=out.index, dtype="object")
    # Apply rules from LOWEST to HIGHEST priority so higher-priority labels overwrite.
    ttype[(price <= 0) & (qty > 0)] = "ZERO_PRICE"
    ttype[non_product & ~is_c] = "NON_PRODUCT"
    ttype[(qty < 0) & ~is_c & ~is_a] = "STOCK_ADJUSTMENT"
    ttype[is_a] = "ACCOUNTING_ADJUSTMENT"
    ttype[is_c & ~non_product] = "RETURN"
    ttype[is_c & non_product] = "CANCELLATION_NON_PRODUCT"
    # Anything else that is not a clean positive sale (e.g. positive qty on a C invoice is impossible
    # in this data, but be defensive):
    ttype[(ttype == "SALE") & ~((qty > 0) & (price > 0))] = "INVALID"
    ttype[invalid] = "INVALID"

    candidate_sale = ttype == "SALE"
    reversed_mask = find_reversed_sales(out, candidate_sale, ttype == "RETURN")
    ttype[reversed_mask & candidate_sale] = "REVERSED_SALE"

    out["TransactionType"] = pd.Categorical(ttype, categories=list(TRANSACTION_TYPES))
    out["Revenue"] = (qty * price).astype("float64")
    out["Date"] = out["InvoiceDate"].dt.normalize()
    return out


def canonical_descriptions(classified: pd.DataFrame) -> pd.Series:
    """One clean description per StockCode: the most frequent normalised description among
    SALE rows (ties broken alphabetically); falls back to any row if a product never sold."""
    tmp = classified[["StockCode", "Description", "TransactionType"]].copy()
    tmp["Description"] = normalise_description(tmp["Description"])
    tmp = tmp.dropna(subset=["StockCode", "Description"])
    # junk notes found on stock adjustments are not product names
    tmp = tmp[~tmp["Description"].str.contains(r"^\?+$|^CHECK$|DAMAGE|THROWN AWAY", regex=True, na=False)]
    tmp["is_sale"] = (tmp["TransactionType"] == "SALE").astype(int)
    counts = (
        tmp.groupby(["StockCode", "Description"], observed=True)
        .agg(sale_n=("is_sale", "sum"), n=("is_sale", "size"))
        .reset_index()
        .sort_values(["StockCode", "sale_n", "n", "Description"], ascending=[True, False, False, True])
    )
    return counts.drop_duplicates("StockCode").set_index("StockCode")["Description"]


def flag_extreme_quantities(sales: pd.DataFrame) -> pd.Series:
    """Flag (do NOT delete) unusually large sale lines for each product.

    Rule: quantity above the product's 99th-percentile line quantity AND at least 10x the
    product's median line quantity AND >= 100 units. Wholesale bulk orders are real demand,
    so flagged lines stay in the data; the flag is for investigation and reporting.
    """
    q = sales["Quantity"].astype("float64")
    grp = q.groupby(sales["StockCode"])
    p99 = grp.transform(lambda s: s.quantile(0.99))
    med = grp.transform("median")
    return ((q > p99) & (q >= 10 * med) & (q >= 100)).astype(bool)


def build_catalog(sales: pd.DataFrame) -> pd.DataFrame:
    """Product catalog (one row per StockCode) from the cleaned sales."""
    s = sales.sort_values("InvoiceDate")
    g = s.groupby("StockCode", observed=True)
    catalog = pd.DataFrame(
        {
            "Description": g["Description"].first(),
            "first_sale_date": g["Date"].min(),
            "last_sale_date": g["Date"].max(),
            "total_quantity": g["Quantity"].sum().astype("int64"),
            "total_revenue": g["Revenue"].sum().round(2),
            "n_invoice_lines": g.size(),
            "n_invoices": g["InvoiceNo"].nunique(),
            "n_sale_days": g["Date"].nunique(),
            "n_customers": g["CustomerID"].nunique(),
            "avg_unit_price": (g["Revenue"].sum() / g["Quantity"].sum()).round(4),
            "last_unit_price": g["UnitPrice"].last().round(4),
        }
    ).reset_index()
    return catalog.sort_values("total_revenue", ascending=False).reset_index(drop=True)


# ===========================================================================
# Main pipeline
# ===========================================================================
def preprocess(raw: pd.DataFrame) -> PreprocessingResult:
    """Run every cleaning step and build the report. Pure function: no files written."""
    if raw.empty:
        raise ValueError("Cannot preprocess an empty dataset.")
    n_original = len(raw)
    missing_before = raw.isna().sum().to_dict()

    # 1) exact duplicates
    dup_mask = raw.duplicated(keep="first")
    n_duplicates = int(dup_mask.sum())
    df = raw.loc[~dup_mask].copy()

    # 2) classify every remaining row
    classified = classify_transactions(df)

    # 3) standardise descriptions (also fills missing descriptions from the same StockCode)
    canon = canonical_descriptions(classified)
    classified["DescriptionRaw"] = classified["Description"]
    classified["Description"] = classified["StockCode"].map(canon).astype("string")
    n_desc_filled = int((classified["DescriptionRaw"].isna() & classified["Description"].notna()).sum())
    n_desc_changed = int(
        (normalise_description(classified["DescriptionRaw"]).fillna("") != classified["Description"].fillna("")).sum()
    )

    # 4) cleaned sales + outlier flags
    sales = classified[classified["TransactionType"] == "SALE"].copy()
    sales["IsExtremeQuantity"] = flag_extreme_quantities(sales)
    classified["IsExtremeQuantity"] = False
    classified.loc[sales.index, "IsExtremeQuantity"] = sales["IsExtremeQuantity"]
    no_desc = sales["Description"].isna()
    sales.loc[no_desc, "Description"] = "UNKNOWN PRODUCT " + sales.loc[no_desc, "StockCode"]
    sales = sales.drop(columns=["DescriptionRaw", "TransactionType"]).reset_index(drop=True)

    catalog = build_catalog(sales)

    # 5) report
    counts = classified["TransactionType"].value_counts().reindex(list(TRANSACTION_TYPES), fill_value=0)
    c_lines = int(counts["RETURN"] + counts["CANCELLATION_NON_PRODUCT"])
    revenue_by_type = classified.groupby("TransactionType", observed=False)["Revenue"].sum().round(2)
    gross_fulfilled = float(revenue_by_type.get("SALE", 0.0))
    gross_invoiced = gross_fulfilled + float(revenue_by_type.get("REVERSED_SALE", 0.0))
    cancel_value = float(revenue_by_type.get("RETURN", 0.0) + revenue_by_type.get("CANCELLATION_NON_PRODUCT", 0.0))

    extreme = sales[sales["IsExtremeQuantity"]].sort_values("Quantity", ascending=False)
    top_reversed = classified[classified["TransactionType"] == "REVERSED_SALE"].nlargest(5, "Quantity")

    report = {
        "report": "Stage 3 - Preprocessing Report",
        "version": PREPROCESSING_VERSION,
        "generated_at": utc_now_iso(),
        "forecast_target_policy": (
            "Gross fulfilled demand: daily sum of Quantity over SALE rows per StockCode. "
            "Returns/cancellations are tracked separately and NOT subtracted; sale lines fully reversed "
            "by a matching cancellation (REVERSED_SALE) are excluded because they were never fulfilled."
        ),
        "counts": {
            "original_rows": n_original,
            "missing_values_by_column": {k: int(v) for k, v in missing_before.items()},
            "missing_value_cells_total": int(sum(missing_before.values())),
            "duplicate_rows_removed": n_duplicates,
            "rows_after_deduplication": len(classified),
            "invalid_rows": int(counts["INVALID"]),
            "cancellation_lines": c_lines,
            "cancelled_invoices": int(
                classified.loc[classified["TransactionType"].isin(["RETURN", "CANCELLATION_NON_PRODUCT"]), "InvoiceNo"].nunique()
            ),
            "return_lines": int(counts["RETURN"]),
            "reversed_sale_lines": int(counts["REVERSED_SALE"]),
            "stock_adjustment_lines": int(counts["STOCK_ADJUSTMENT"]),
            "accounting_adjustment_lines": int(counts["ACCOUNTING_ADJUSTMENT"]),
            "non_product_lines": int(counts["NON_PRODUCT"]),
            "zero_price_lines": int(counts["ZERO_PRICE"]),
            "removed_rows_total": n_original - len(sales),
            "retained_sale_rows": len(sales),
            "final_dimensions": {"rows": len(sales), "columns": sales.shape[1]},
            "missing_customer_id_in_sales": int(sales["CustomerID"].isna().sum()),
            "descriptions_filled_from_stockcode": n_desc_filled,
            "descriptions_standardised": n_desc_changed,
            "extreme_quantity_lines_flagged_kept": int(sales["IsExtremeQuantity"].sum()),
        },
        "transaction_types": {
            t: {"rows": int(counts[t]), "revenue": float(revenue_by_type.get(t, 0.0)), "meaning": TYPE_EXPLANATIONS[t]}
            for t in TRANSACTION_TYPES
        },
        "revenue": {
            "gross_fulfilled_sales_revenue": round(gross_fulfilled, 2),
            "gross_invoiced_revenue_incl_reversed": round(gross_invoiced, 2),
            "cancellations_and_returns_value": round(cancel_value, 2),
            "net_revenue_after_cancellations": round(gross_invoiced + cancel_value, 2),
            "note": "Dashboard 'revenue' = gross fulfilled sales revenue (SALE rows). Net revenue is shown separately.",
        },
        "outliers": {
            "rule": "Flag if quantity > product's 99th percentile AND >= 10x product median AND >= 100 units. Flagged rows are KEPT.",
            "flagged_lines": int(sales["IsExtremeQuantity"].sum()),
            "largest_flagged_lines": to_json_safe(
                extreme.head(10)[["InvoiceNo", "StockCode", "Description", "Quantity", "UnitPrice", "InvoiceDate", "CustomerID"]]
            ),
            "largest_reversed_sales": to_json_safe(
                top_reversed[["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "CustomerID"]]
            ),
        },
        "steps": [
            "1. Removed exact duplicate rows (identical in all 8 columns).",
            "2. Labelled every row with one TransactionType (see transaction_types).",
            "3. Matched cancellations to the sales they fully reverse (same customer, product, quantity).",
            "4. Standardised descriptions: one canonical upper-case description per StockCode; missing descriptions filled from the same StockCode.",
            "5. Kept only SALE rows in the cleaned sales dataset; computed Revenue = Quantity x UnitPrice.",
            "6. Flagged (did not delete) extreme quantities for investigation.",
            "7. Built a product catalog from cleaned sales.",
        ],
        "products_in_clean_sales": int(sales["StockCode"].nunique()),
        "date_range_clean_sales": {"min": sales["InvoiceDate"].min(), "max": sales["InvoiceDate"].max()},
    }
    return PreprocessingResult(classified=classified, sales=sales, catalog=catalog, report=to_json_safe(report))


def render_markdown(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "# Stage 3 — Preprocessing Report\n",
        f"_Generated {report['generated_at']} from the real dataset._\n",
        "## Forecasting target policy\n",
        report["forecast_target_policy"] + "\n",
        "## Row accounting\n",
        "| Item | Rows |",
        "|---|---|",
    ]
    for key in (
        "original_rows", "missing_value_cells_total", "duplicate_rows_removed", "rows_after_deduplication",
        "invalid_rows", "cancellation_lines", "cancelled_invoices", "return_lines", "reversed_sale_lines",
        "stock_adjustment_lines", "accounting_adjustment_lines", "non_product_lines", "zero_price_lines",
        "removed_rows_total", "retained_sale_rows", "missing_customer_id_in_sales",
        "descriptions_filled_from_stockcode", "descriptions_standardised", "extreme_quantity_lines_flagged_kept",
    ):
        lines.append(f"| {key.replace('_', ' ')} | {c[key]:,} |")
    lines.append(f"\nFinal cleaned dataset: **{c['final_dimensions']['rows']:,} rows x {c['final_dimensions']['columns']} columns**.\n")
    lines += ["## Transaction types\n", "| Type | Rows | Revenue (GBP) | Meaning |", "|---|---|---|---|"]
    for t, v in report["transaction_types"].items():
        lines.append(f"| {t} | {v['rows']:,} | {v['revenue']:,.2f} | {v['meaning']} |")
    r = report["revenue"]
    lines += [
        "\n## Revenue definitions\n",
        f"- Gross fulfilled sales revenue (SALE): **£{r['gross_fulfilled_sales_revenue']:,.2f}**",
        f"- Gross invoiced revenue incl. reversed orders: £{r['gross_invoiced_revenue_incl_reversed']:,.2f}",
        f"- Value of cancellations and returns: £{r['cancellations_and_returns_value']:,.2f}",
        f"- Net revenue after cancellations: £{r['net_revenue_after_cancellations']:,.2f}",
        f"- {r['note']}\n",
        "## Outlier investigation\n",
        report["outliers"]["rule"] + "\n",
        "Largest reversed sales (excluded because they were cancelled in full):\n",
        "| Invoice | StockCode | Description | Qty | Date |",
        "|---|---|---|---|---|",
    ]
    for row in report["outliers"]["largest_reversed_sales"]:
        lines.append(f"| {row['InvoiceNo']} | {row['StockCode']} | {row['Description']} | {row['Quantity']:,} | {row['InvoiceDate']} |")
    lines += ["\nLargest flagged (kept) sale lines:\n", "| Invoice | StockCode | Description | Qty | Price |", "|---|---|---|---|---|"]
    for row in report["outliers"]["largest_flagged_lines"]:
        lines.append(f"| {row['InvoiceNo']} | {row['StockCode']} | {row['Description']} | {row['Quantity']:,} | {row['UnitPrice']} |")
    lines += ["\n## Steps\n"] + [f"{s}" for s in report["steps"]]
    return "\n".join(lines) + "\n"


def save_outputs(result: PreprocessingResult) -> dict[str, str]:
    """Persist cleaned data, classified rows, catalog and report."""
    config.ensure_directories()
    p, r = config.PROCESSED_DATA_DIR, config.REPORTS_DIR
    classified = result.classified.copy()
    classified["TransactionType"] = classified["TransactionType"].astype("string")
    atomic_write_parquet(p / "transactions_classified.parquet", classified)
    atomic_write_parquet(p / "cleaned_sales.parquet", result.sales)
    atomic_write_csv(p / "cleaned_sales.csv", result.sales, date_format="%Y-%m-%d %H:%M:%S")
    atomic_write_parquet(p / "product_catalog.parquet", result.catalog)
    atomic_write_json(r / "03_preprocessing_report.json", result.report)
    atomic_write_text(r / "03_preprocessing_report.md", render_markdown(result.report))
    return {"cleaned_sales": "data/processed/cleaned_sales.parquet", "report": "data/reports/03_preprocessing_report.json"}


def load_clean_sales() -> pd.DataFrame:
    path = config.PROCESSED_DATA_DIR / "cleaned_sales.parquet"
    if not path.exists():
        raise FileNotFoundError("Cleaned sales not found. Run the preprocessing stage first (python -m ml.pipeline).")
    return pd.read_parquet(path)


def load_classified() -> pd.DataFrame:
    path = config.PROCESSED_DATA_DIR / "transactions_classified.parquet"
    if not path.exists():
        raise FileNotFoundError("Classified transactions not found. Run the preprocessing stage first.")
    return pd.read_parquet(path)


def run(raw: pd.DataFrame | None = None) -> PreprocessingResult:
    if raw is None:
        from ml.data_loader import load_dataset

        raw = load_dataset().df
    result = preprocess(raw)
    save_outputs(result)
    return result


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Stage 3: clean and preprocess the dataset").parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    result = run()
    c = result.report["counts"]
    print(f"Original rows: {c['original_rows']:,} -> cleaned sale rows: {c['retained_sale_rows']:,}")
    for t, v in result.report["transaction_types"].items():
        print(f"  {t:<26}{v['rows']:>9,}")
    print("Saved data/processed/cleaned_sales.{parquet,csv} and data/reports/03_preprocessing_report.{json,md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
