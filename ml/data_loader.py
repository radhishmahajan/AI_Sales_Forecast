"""
STAGE 1 — Dataset import and understanding.

What this module does (in simple words)
---------------------------------------
1. Finds the UCI "Online Retail.xlsx" file (default: data/raw/Online Retail.xlsx).
2. Checks the FILE before opening it: does it exist, is it really an .xlsx, is the size sane?
3. Checks the CONTENT: are all 8 required columns present, is it non-empty?
4. Converts every column to the correct data type and counts values that could not be converted.
5. Builds a "dataset overview" (profile): size, previews, data types, statistics, missing values,
   duplicates, unique products/customers/invoices, date range and early data-quality observations.
6. Saves that overview as JSON (for the API/dashboard) and Markdown (for humans / the report).

Nothing here CHANGES or DELETES data. Cleaning decisions are made in Stage 3 (preprocessing.py),
so this stage gives an honest picture of the raw data exactly as UCI provides it.

Run from the project root:
    python -m ml.data_loader
    python -m ml.data_loader --path "data/raw/Online Retail.xlsx" --no-cache
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml import config
from ml.utils import (
    atomic_write_json,
    atomic_write_parquet,
    atomic_write_text,
    read_json,
    sha256_file,
    to_json_safe,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

LOADER_VERSION = "1.0"  # bump this if type-coercion rules change -> invalidates the cache

# A "normal" product StockCode in this dataset is 5 digits, optionally followed by letters
# (e.g. 85123A). Codes like POST, M, D, DOT, BANK CHARGES are postage/fees/adjustments.
STANDARD_STOCKCODE_PATTERN = re.compile(r"^\d{5}[A-Za-z]{0,2}$")


class DatasetValidationError(ValueError):
    """Raised when the dataset file or its content fails validation.

    The message is written for the end user (shown in the notebook / API / dashboard).
    """


@dataclass
class LoadResult:
    """Everything produced when loading the dataset."""

    df: pd.DataFrame
    file_info: dict[str, Any]
    column_mapping: dict[str, str]
    coercion_report: dict[str, dict[str, int]]
    warnings: list[str] = field(default_factory=list)
    from_cache: bool = False


# ===========================================================================
# 1. FILE-LEVEL VALIDATION (before we even open the file)
# ===========================================================================
def resolve_dataset_path(path: str | Path | None = None) -> Path:
    """Return the dataset path to use (explicit argument wins, else the default location)."""
    return Path(path).expanduser().resolve() if path else config.DEFAULT_DATASET_PATH


def validate_file(path: str | Path, max_size_mb: float | None = None) -> dict[str, Any]:
    """Validate the dataset FILE (existence, extension, size, real Excel signature).

    Why: opening a wrong/corrupt/huge file can crash the program or waste minutes.
    We never execute uploaded files; we only read bytes and check the ZIP signature
    that every genuine .xlsx file starts with.

    Returns basic file information. Raises DatasetValidationError on any problem.
    """
    path = Path(path)
    max_size_mb = config.MAX_DATASET_SIZE_MB if max_size_mb is None else max_size_mb

    if not path.exists():
        raise DatasetValidationError(
            f"Dataset file '{path.name}' was not found. Download it from "
            f"{config.DATASET_SOURCE_URL}, unzip it, and place '{config.DATASET_FILENAME}' "
            f"inside the data/raw/ folder (or upload it from the Dataset page)."
        )
    if not path.is_file():
        raise DatasetValidationError(f"'{path.name}' is a folder, not a file.")

    extension = path.suffix.lower()
    if extension not in config.ALLOWED_DATASET_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_DATASET_EXTENSIONS))
        raise DatasetValidationError(
            f"Unsupported file type '{extension or '(none)'}'. Allowed: {allowed}. "
            "Please upload the original 'Online Retail.xlsx' Excel file."
        )

    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise DatasetValidationError(f"'{path.name}' is empty (0 bytes).")
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > max_size_mb:
        raise DatasetValidationError(
            f"'{path.name}' is {size_mb:.1f} MB, above the {max_size_mb} MB limit."
        )

    with open(path, "rb") as handle:
        signature = handle.read(len(config.XLSX_MAGIC_BYTES))
    if signature != config.XLSX_MAGIC_BYTES:
        raise DatasetValidationError(
            f"'{path.name}' has an .xlsx extension but is not a valid Excel workbook "
            "(file signature mismatch). The file may be corrupted or renamed."
        )

    return {
        "file_name": path.name,  # name only: we never expose full local paths
        "file_size_bytes": int(size_bytes),
        "file_size_mb": round(size_mb, 2),
        "extension": extension,
    }


# ===========================================================================
# 2. COLUMN-LEVEL VALIDATION
# ===========================================================================
def build_column_mapping(columns: list[Any]) -> dict[str, str]:
    """Map original header names -> canonical names (handles stray spaces / letter case).

    Example: ' Quantity ' -> 'Quantity', 'customerid' -> 'CustomerID'.
    """
    canonical_by_key = {c.lower(): c for c in config.REQUIRED_COLUMNS}
    mapping: dict[str, str] = {}
    for original in columns:
        key = str(original).strip().lower()
        if key in canonical_by_key:
            mapping[str(original)] = canonical_by_key[key]
    return mapping


def validate_columns(columns: list[Any]) -> tuple[dict[str, str], list[str]]:
    """Check that all 8 required columns exist. Returns (mapping, warnings)."""
    mapping = build_column_mapping(columns)
    found = set(mapping.values())
    missing = [c for c in config.REQUIRED_COLUMNS if c not in found]
    if missing:
        raise DatasetValidationError(
            "The file is missing required column(s): "
            + ", ".join(missing)
            + ". Expected columns: "
            + ", ".join(config.REQUIRED_COLUMNS)
            + ". Make sure you uploaded the UCI Online Retail dataset."
        )
    warnings: list[str] = []
    extra = [str(c) for c in columns if str(c) not in mapping]
    if extra:
        warnings.append(f"Ignoring {len(extra)} unexpected column(s): {', '.join(extra[:10])}")
    renamed = {k: v for k, v in mapping.items() if k != v}
    if renamed:
        warnings.append(f"Normalised column names: {renamed}")
    return mapping, warnings


# ===========================================================================
# 3. TYPE COERCION
# ===========================================================================
def _clean_code_series(series: pd.Series) -> pd.Series:
    """Text codes (InvoiceNo/StockCode): strip spaces, remove a spurious trailing '.0'."""
    s = series.astype("string").str.strip()
    s = s.str.replace(r"^(\d+)\.0$", r"\1", regex=True)
    return s.replace("", pd.NA)


def _to_nullable_int(series: pd.Series) -> tuple[pd.Series, int]:
    """Convert to pandas nullable Int64; count values that were not whole numbers."""
    numeric = pd.to_numeric(series, errors="coerce")
    non_integer = numeric.notna() & (np.floor(numeric) != numeric)
    numeric = numeric.mask(non_integer)
    return numeric.astype("Int64"), int(non_integer.sum())


def coerce_types(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Convert every column to its expected type (see config.EXPECTED_DTYPES).

    Why: Excel mixes numbers and text in the same column (e.g. InvoiceNo 536365 vs C536379).
    Explicit types prevent silent bugs later (like '536365' != 536365).

    Returns (typed DataFrame, coercion report). The report counts, per column:
      missing_before   -> values already empty in the file
      invalid_coerced  -> values present in the file but impossible to convert (became missing)
    """
    out = df.copy()
    report: dict[str, dict[str, int]] = {}

    def record(col: str, before: pd.Series, after: pd.Series, extra_invalid: int = 0) -> None:
        missing_before = int(before.isna().sum())
        invalid = int((before.notna() & after.isna()).sum())
        report[col] = {
            "missing_before": missing_before,
            "invalid_coerced": max(invalid, extra_invalid),
        }

    for col in ("InvoiceNo", "StockCode"):
        before = out[col]
        out[col] = _clean_code_series(before)
        record(col, before, out[col])

    for col in ("Description", "Country"):
        before = out[col]
        out[col] = before.astype("string").str.strip().replace("", pd.NA)
        # Blank-only text counts as missing, not as "invalid".
        report[col] = {"missing_before": int(out[col].isna().sum()), "invalid_coerced": 0}

    before = out["Quantity"]
    out["Quantity"], non_int = _to_nullable_int(before)
    record("Quantity", before, out["Quantity"], non_int)

    before = out["CustomerID"]
    out["CustomerID"], non_int = _to_nullable_int(before)
    record("CustomerID", before, out["CustomerID"], non_int)

    before = out["UnitPrice"]
    out["UnitPrice"] = pd.to_numeric(before, errors="coerce").astype("float64")
    record("UnitPrice", before, out["UnitPrice"])

    before = out["InvoiceDate"]
    out["InvoiceDate"] = pd.to_datetime(before, errors="coerce").astype("datetime64[ns]")
    record("InvoiceDate", before, out["InvoiceDate"])

    return out[list(config.REQUIRED_COLUMNS)], report


# ===========================================================================
# 4. LOADING (with a fast Parquet cache)
# ===========================================================================
def _cache_paths(cache_dir: Path) -> tuple[Path, Path]:
    return cache_dir / config.RAW_CACHE_FILENAME, cache_dir / config.RAW_CACHE_META_FILENAME


def _read_excel_header(path: Path) -> list[Any]:
    try:
        header = pd.read_excel(path, sheet_name=0, nrows=0, engine="openpyxl")
    except Exception as exc:  # openpyxl raises many different exception types
        raise DatasetValidationError(
            f"Could not open '{path.name}' as an Excel workbook: {type(exc).__name__}. "
            "The file may be corrupted."
        ) from exc
    return list(header.columns)


def load_dataset(
    path: str | Path | None = None,
    use_cache: bool = True,
    cache_dir: str | Path | None = None,
    nrows: int | None = None,
) -> LoadResult:
    """Validate and load the dataset. This is the ONE function the rest of the project calls.

    Reading a 500k-row Excel file takes about a minute, so after the first read we save an
    exact typed copy as Parquet. Next time, if the Excel file's SHA-256 fingerprint is
    unchanged, we load the Parquet copy in about a second. Change the Excel file and the
    cache is rebuilt automatically.
    """
    path = resolve_dataset_path(path)
    file_info = validate_file(path)
    file_info["sha256"] = sha256_file(path)

    cache_dir = Path(cache_dir) if cache_dir else config.PROCESSED_DATA_DIR
    cache_file, cache_meta_file = _cache_paths(cache_dir)

    # ---- Try the cache first -------------------------------------------------
    if use_cache and nrows is None and cache_file.exists():
        try:
            meta = read_json(cache_meta_file, default={}) or {}
        except ValueError:
            meta = {}
        if meta.get("source_sha256") == file_info["sha256"] and meta.get("loader_version") == LOADER_VERSION:
            try:
                df = pd.read_parquet(cache_file)
                df, _ = coerce_types(df)  # re-assert dtypes (cheap; protects against version drift)
                logger.info("Loaded dataset from Parquet cache (%s rows)", len(df))
                return LoadResult(
                    df=df,
                    file_info=file_info,
                    column_mapping=meta.get("column_mapping", {}),
                    coercion_report=meta.get("coercion_report", {}),
                    warnings=meta.get("warnings", []),
                    from_cache=True,
                )
            except Exception as exc:  # corrupted cache -> fall back to Excel
                logger.warning("Parquet cache unreadable (%s); re-reading Excel.", exc)

    # ---- Read the Excel file -------------------------------------------------
    columns = _read_excel_header(path)
    mapping, warnings = validate_columns(columns)
    original_by_canonical = {v: k for k, v in mapping.items()}
    text_cols = ("InvoiceNo", "StockCode", "Description", "Country")
    dtype = {original_by_canonical[c]: str for c in text_cols}

    logger.info("Reading Excel file '%s' (this can take ~1 minute for the full dataset)...", path.name)
    try:
        raw = pd.read_excel(
            path,
            sheet_name=0,
            engine="openpyxl",
            dtype=dtype,
            usecols=list(mapping.keys()),
            nrows=nrows,
        )
    except Exception as exc:
        raise DatasetValidationError(
            f"Failed to read '{path.name}': {type(exc).__name__}: {exc}"
        ) from exc

    raw = raw.rename(columns=mapping)
    if raw.empty:
        raise DatasetValidationError(
            f"'{path.name}' contains the column headers but no data rows."
        )

    df, coercion_report = coerce_types(raw)

    if use_cache and nrows is None:
        try:
            atomic_write_parquet(cache_file, df)
            atomic_write_json(
                cache_meta_file,
                {
                    "source_file_name": path.name,
                    "source_sha256": file_info["sha256"],
                    "loader_version": LOADER_VERSION,
                    "created_at": utc_now_iso(),
                    "rows": len(df),
                    "column_mapping": mapping,
                    "coercion_report": coercion_report,
                    "warnings": warnings,
                },
            )
        except Exception as exc:  # cache is an optimisation; never fail the load because of it
            logger.warning("Could not write Parquet cache: %s", exc)

    return LoadResult(
        df=df,
        file_info=file_info,
        column_mapping=mapping,
        coercion_report=coercion_report,
        warnings=warnings,
        from_cache=False,
    )


def load_uploaded_colab_file(uploaded: dict[str, bytes], target_dir: str | Path | None = None) -> Path:
    """Save the result of google.colab.files.upload() to data/raw/ and return its path.

    In Colab, files.upload() returns {filename: file_bytes}. We pick the .xlsx file,
    write it to data/raw/, and from there the normal loader is used.
    """
    target_dir = Path(target_dir) if target_dir else config.RAW_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    xlsx = {name: data for name, data in uploaded.items() if name.lower().endswith(".xlsx")}
    if not xlsx:
        raise DatasetValidationError("No .xlsx file was uploaded. Please upload 'Online Retail.xlsx'.")
    name, data = next(iter(xlsx.items()))
    # Colab renames duplicates to 'Online Retail (1).xlsx'; always store under the canonical name.
    target = target_dir / config.DATASET_FILENAME
    target.write_bytes(data)
    if name != config.DATASET_FILENAME:
        logger.info("Saved uploaded '%s' as '%s'", name, config.DATASET_FILENAME)
    return target


# ===========================================================================
# 5. PROFILING (the "dataset overview")
# ===========================================================================
PURPOSES: dict[str, str] = {
    "file_info": "Confirms which file was analysed (name, size, SHA-256 fingerprint) so results are reproducible.",
    "dimensions": "Shows how big the dataset is: rows = invoice lines, columns = attributes.",
    "columns": "Lists every column with its data type, meaning, missing values and number of distinct values.",
    "type_coercion": "Reports values that could not be converted to the correct type (e.g. text in a number column).",
    "head": "The first five rows: a quick look at what the raw data looks like.",
    "tail": "The last five rows: confirms the file was read to the end and shows the latest records.",
    "sample": "Five random rows (fixed seed 42, so reproducible) to see typical records from the middle of the file.",
    "data_info": "Data types and memory usage, like DataFrame.info().",
    "numeric_summary": "Count, mean, standard deviation, min/max and percentiles of numeric columns. Negative or extreme values here hint at returns and outliers.",
    "categorical_summary": "Most frequent value and number of distinct values for text columns.",
    "date_range": "First and last transaction timestamps and how many days the data covers.",
    "missing_values": "How many values are empty in each column. Missing CustomerID matters for customer analysis but not for product demand.",
    "duplicates": "Rows that are exact copies across all 8 columns. They may be data-entry duplicates and are reviewed in Stage 3.",
    "unique_counts": "Number of distinct products, customers, invoices and countries.",
    "quality_observations": "Early warning signs (cancellations, negative quantities, zero prices, non-product codes). Observed only; handled in Stage 3.",
    "uci_documented_check": "Compares what we actually found with what UCI documents, without assuming either is correct.",
}


def _frame_preview(df: pd.DataFrame) -> list[dict[str, Any]]:
    return to_json_safe(df.astype(object).where(df.notna(), None).to_dict(orient="records"))


def profile_dataset(result: LoadResult | pd.DataFrame, sample_size: int = 5) -> dict[str, Any]:
    """Build the complete Stage 1 dataset overview as a JSON-safe dictionary."""
    if isinstance(result, pd.DataFrame):
        result = LoadResult(df=result, file_info={}, column_mapping={}, coercion_report={})
    df = result.df
    if df.empty:
        raise DatasetValidationError("Cannot profile an empty dataset.")

    n_rows, n_cols = df.shape
    missing = df.isna().sum()

    # ---- columns -------------------------------------------------------------
    columns = []
    for col in df.columns:
        columns.append(
            {
                "name": col,
                "dtype": str(df[col].dtype),
                "expected_dtype": config.EXPECTED_DTYPES.get(col),
                "description": config.COLUMN_DESCRIPTIONS.get(col, ""),
                "non_null": int(df[col].notna().sum()),
                "missing": int(missing[col]),
                "missing_pct": round(100 * missing[col] / n_rows, 3),
                "unique": int(df[col].nunique(dropna=True)),
            }
        )

    # ---- numeric & categorical summaries -------------------------------------
    numeric_cols = [c for c in ("Quantity", "UnitPrice") if c in df]
    numeric_summary = {}
    for col in numeric_cols:
        s = df[col].astype("float64")
        desc = s.describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        numeric_summary[col] = {k: to_json_safe(v) for k, v in desc.items()}
        numeric_summary[col]["negative_count"] = int((s < 0).sum())
        numeric_summary[col]["zero_count"] = int((s == 0).sum())

    categorical_summary = {}
    for col in ("InvoiceNo", "StockCode", "Description", "Country"):
        s = df[col].dropna()
        vc = s.value_counts()
        categorical_summary[col] = {
            "count": int(s.size),
            "unique": int(vc.size),
            "top": None if vc.empty else str(vc.index[0]),
            "top_frequency": None if vc.empty else int(vc.iloc[0]),
        }

    # ---- dates ---------------------------------------------------------------
    dates = df["InvoiceDate"].dropna()
    date_range = {
        "min": dates.min() if not dates.empty else None,
        "max": dates.max() if not dates.empty else None,
        "span_days": int((dates.max() - dates.min()).days) + 1 if not dates.empty else 0,
        "distinct_transaction_days": int(dates.dt.normalize().nunique()),
        "months_covered": sorted(dates.dt.strftime("%Y-%m").unique().tolist()),
    }

    # ---- missing -------------------------------------------------------------
    missing_values = {
        "per_column": {c: int(missing[c]) for c in df.columns},
        "per_column_pct": {c: round(100 * missing[c] / n_rows, 3) for c in df.columns},
        "rows_with_any_missing": int(df.isna().any(axis=1).sum()),
        "total_missing_cells": int(missing.sum()),
    }

    # ---- duplicates ----------------------------------------------------------
    dup_mask_all = df.duplicated(keep=False)
    dup_mask_extra = df.duplicated(keep="first")
    dup_examples = df[dup_mask_all].sort_values(list(df.columns)).head(6)
    duplicates = {
        "exact_duplicate_rows": int(dup_mask_extra.sum()),  # extra copies beyond the first
        "exact_duplicate_pct": round(100 * dup_mask_extra.sum() / n_rows, 3),
        "rows_involved_in_duplication": int(dup_mask_all.sum()),
        "duplicate_groups": int(df[dup_mask_all].drop_duplicates().shape[0]),
        "examples": _frame_preview(dup_examples),
    }

    # ---- uniques -------------------------------------------------------------
    invoice = df["InvoiceNo"].astype("string")
    is_cancel = invoice.str.upper().str.startswith("C").fillna(False).astype(bool)
    unique_counts = {
        "products_stockcode": int(df["StockCode"].nunique()),
        "descriptions": int(df["Description"].nunique()),
        "customers": int(df["CustomerID"].nunique()),
        "invoices": int(df["InvoiceNo"].nunique()),
        "cancelled_invoices": int(df.loc[is_cancel, "InvoiceNo"].nunique()),
        "countries": int(df["Country"].nunique()),
    }

    # ---- quality observations (NOT cleaning) --------------------------------
    qty = df["Quantity"].astype("float64")
    price = df["UnitPrice"]
    stock = df["StockCode"].astype("string")
    non_standard = ~stock.fillna("").str.match(STANDARD_STOCKCODE_PATTERN)
    desc_per_code = df.dropna(subset=["StockCode", "Description"]).groupby("StockCode")["Description"].nunique()
    quality_observations = {
        "cancellation_rows_invoice_starts_with_C": int(is_cancel.sum()),
        "negative_quantity_rows": int((qty < 0).sum()),
        "negative_quantity_rows_not_cancelled": int(((qty < 0) & ~is_cancel).sum()),
        "zero_quantity_rows": int((qty == 0).sum()),
        "zero_unit_price_rows": int((price == 0).sum()),
        "negative_unit_price_rows": int((price < 0).sum()),
        "missing_customer_id_rows": int(df["CustomerID"].isna().sum()),
        "missing_description_rows": int(df["Description"].isna().sum()),
        "non_standard_stockcode_rows": int(non_standard.sum()),
        "non_standard_stockcode_examples": stock[non_standard].value_counts().head(15).to_dict(),
        "stockcodes_with_multiple_descriptions": int((desc_per_code > 1).sum()),
        "note": "These are observations only. Stage 3 (preprocessing) decides how each case is handled.",
    }

    # ---- compare with UCI documentation (no assumptions) ----------------------
    uci_documented = {"rows": 541909, "columns": 8, "period": "2010-12 to 2011-12"}
    first, last = date_range["min"], date_range["max"]
    observed_period = f"{first:%Y-%m} to {last:%Y-%m}" if first is not None else None
    uci_check = {
        "documented": uci_documented,
        "observed": {"rows": n_rows, "columns": n_cols, "period": observed_period},
        "rows_match": n_rows == uci_documented["rows"],
        "columns_match": n_cols == uci_documented["columns"],
        "period_match": observed_period == uci_documented["period"],
    }

    rng_state = np.random.RandomState(config.RANDOM_SEED)
    sample = df.sample(n=min(sample_size, n_rows), random_state=rng_state)

    profile = {
        "report": "Stage 1 - Dataset Overview",
        "generated_at": utc_now_iso(),
        "loaded_from_cache": result.from_cache,
        "purposes": PURPOSES,
        "file_info": result.file_info,
        "load_warnings": result.warnings,
        "dimensions": {"rows": n_rows, "columns": n_cols},
        "columns": columns,
        "type_coercion": result.coercion_report,
        "head": _frame_preview(df.head(5)),
        "tail": _frame_preview(df.tail(5)),
        "sample": _frame_preview(sample),
        "data_info": {
            "dtypes": {c: str(t) for c, t in df.dtypes.items()},
            "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 2),
        },
        "numeric_summary": numeric_summary,
        "categorical_summary": categorical_summary,
        "date_range": date_range,
        "missing_values": missing_values,
        "duplicates": duplicates,
        "unique_counts": unique_counts,
        "quality_observations": quality_observations,
        "uci_documented_check": uci_check,
    }
    return to_json_safe(profile)


# ===========================================================================
# 6. SAVING THE REPORT
# ===========================================================================
def _md_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return "_(none)_\n"
    columns = columns or list(rows[0].keys())

    def fmt(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:,.4g}" if abs(v) < 1e6 else f"{v:,.0f}"
        return str(v).replace("|", "\\|")

    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(fmt(r.get(c)) for c in columns) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def render_markdown(profile: dict[str, Any]) -> str:
    """Human-readable version of the overview (goes into docs / the PBL report)."""
    p = profile
    P = p["purposes"]
    d, u, q, dup, mv = (
        p["dimensions"], p["unique_counts"], p["quality_observations"], p["duplicates"], p["missing_values"]
    )
    out: list[str] = []
    out.append("# Stage 1 — Dataset Overview Report\n")
    out.append(f"_Generated: {p['generated_at']} — all numbers computed from the actual file; nothing is assumed._\n")

    fi = p.get("file_info") or {}
    if fi:
        out.append("## 1. File\n")
        out.append(f"> {P['file_info']}\n")
        out.append(f"- File: `{fi.get('file_name')}` ({fi.get('file_size_mb')} MB)\n- SHA-256: `{fi.get('sha256')}`\n")

    out.append("## 2. Dimensions\n")
    out.append(f"> {P['dimensions']}\n")
    out.append(f"- Rows: **{d['rows']:,}**\n- Columns: **{d['columns']}**\n")

    out.append("## 3. Columns and data types\n")
    out.append(f"> {P['columns']}\n")
    out.append(_md_table(p["columns"], ["name", "dtype", "non_null", "missing", "missing_pct", "unique", "description"]))

    out.append("\n## 4. Type conversion check\n")
    out.append(f"> {P['type_coercion']}\n")
    tc = [{"column": k, **v} for k, v in (p.get("type_coercion") or {}).items()]
    out.append(_md_table(tc))

    for key, title in (("head", "5. First five rows"), ("tail", "6. Last five rows"), ("sample", "7. Random sample (seed 42)")):
        out.append(f"\n## {title}\n")
        out.append(f"> {P[key]}\n")
        out.append(_md_table(p[key]))

    out.append("\n## 8. Statistical summary (numeric)\n")
    out.append(f"> {P['numeric_summary']}\n")
    ns = [{"statistic": stat, **{col: p["numeric_summary"][col].get(stat) for col in p["numeric_summary"]}}
          for stat in next(iter(p["numeric_summary"].values())).keys()]
    out.append(_md_table(ns))

    out.append("\n## 9. Statistical summary (text columns)\n")
    out.append(f"> {P['categorical_summary']}\n")
    out.append(_md_table([{"column": k, **v} for k, v in p["categorical_summary"].items()]))

    dr = p["date_range"]
    out.append("\n## 10. Date range\n")
    out.append(f"> {P['date_range']}\n")
    out.append(
        f"- First transaction: **{dr['min']}**\n- Last transaction: **{dr['max']}**\n"
        f"- Calendar span: **{dr['span_days']} days**; days with at least one transaction: **{dr['distinct_transaction_days']}**\n"
        f"- Months covered: {', '.join(dr['months_covered'])}\n"
    )

    out.append("\n## 11. Missing values\n")
    out.append(f"> {P['missing_values']}\n")
    out.append(_md_table([{"column": c, "missing": mv["per_column"][c], "missing_pct": mv["per_column_pct"][c]} for c in mv["per_column"]]))
    out.append(f"\nRows with at least one missing value: **{mv['rows_with_any_missing']:,}**\n")

    out.append("\n## 12. Duplicates\n")
    out.append(f"> {P['duplicates']}\n")
    out.append(
        f"- Extra exact-duplicate rows (beyond first copy): **{dup['exact_duplicate_rows']:,}** ({dup['exact_duplicate_pct']}%)\n"
        f"- Distinct duplicated records: **{dup['duplicate_groups']:,}**\n"
    )

    out.append("\n## 13. Unique counts\n")
    out.append(f"> {P['unique_counts']}\n")
    out.append(_md_table([{"entity": k, "unique": v} for k, v in u.items()]))

    out.append("\n## 14. Early data-quality observations\n")
    out.append(f"> {P['quality_observations']}\n")
    out.append(_md_table([{"observation": k, "rows": v} for k, v in q.items() if isinstance(v, int)]))
    if q.get("non_standard_stockcode_examples"):
        out.append("\nMost frequent non-standard StockCodes (postage, fees, manual adjustments, etc.):\n\n")
        out.append(_md_table([{"StockCode": k, "rows": v} for k, v in q["non_standard_stockcode_examples"].items()]))

    uc = p["uci_documented_check"]
    out.append("\n## 15. Comparison with UCI documentation\n")
    out.append(f"> {P['uci_documented_check']}\n")
    out.append(_md_table([
        {"property": "rows", "documented": uc["documented"]["rows"], "observed": uc["observed"]["rows"], "match": uc["rows_match"]},
        {"property": "columns", "documented": uc["documented"]["columns"], "observed": uc["observed"]["columns"], "match": uc["columns_match"]},
        {"property": "period", "documented": uc["documented"]["period"], "observed": uc["observed"]["period"], "match": uc["period_match"]},
    ]))

    if p.get("load_warnings"):
        out.append("\n## Load warnings\n")
        out += [f"- {w}\n" for w in p["load_warnings"]]
    return "".join(out)


def save_overview_report(profile: dict[str, Any], reports_dir: str | Path | None = None) -> dict[str, Path]:
    """Save the overview as JSON + Markdown (atomic writes)."""
    reports_dir = Path(reports_dir) if reports_dir else config.REPORTS_DIR
    json_path = atomic_write_json(reports_dir / "01_dataset_overview.json", profile)
    md_path = atomic_write_text(reports_dir / "01_dataset_overview.md", render_markdown(profile))
    return {"json": json_path, "markdown": md_path}


# ===========================================================================
# 7. COMMAND-LINE ENTRY POINT
# ===========================================================================
def run(path: str | Path | None = None, use_cache: bool = True) -> dict[str, Any]:
    """Load -> validate -> profile -> save. Returns the profile."""
    config.ensure_directories()
    result = load_dataset(path, use_cache=use_cache)
    profile = profile_dataset(result)
    save_overview_report(profile)
    return profile


def _print_summary(profile: dict[str, Any]) -> None:
    d, u, q, dr = profile["dimensions"], profile["unique_counts"], profile["quality_observations"], profile["date_range"]
    print("=" * 64)
    print(" STAGE 1 - DATASET OVERVIEW")
    print("=" * 64)
    print(f" Rows x Columns            : {d['rows']:,} x {d['columns']}")
    print(f" Period                    : {dr['min']}  ->  {dr['max']}")
    print(f" Unique products/customers : {u['products_stockcode']:,} / {u['customers']:,}")
    print(f" Unique invoices/countries : {u['invoices']:,} / {u['countries']}")
    print(f" Missing CustomerID rows   : {q['missing_customer_id_rows']:,}")
    print(f" Missing Description rows  : {q['missing_description_rows']:,}")
    print(f" Exact duplicate rows      : {profile['duplicates']['exact_duplicate_rows']:,}")
    print(f" Cancellation rows (C...)  : {q['cancellation_rows_invoice_starts_with_C']:,}")
    print(f" Negative quantity rows    : {q['negative_quantity_rows']:,}")
    print(f" Zero / negative price rows: {q['zero_unit_price_rows']:,} / {q['negative_unit_price_rows']:,}")
    print("-" * 64)
    print(" Reports saved to data/reports/01_dataset_overview.{json,md}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1: load, validate and profile the UCI Online Retail dataset.")
    parser.add_argument("--path", default=None, help="Path to 'Online Retail.xlsx' (default: data/raw/Online Retail.xlsx)")
    parser.add_argument("--no-cache", action="store_true", help="Ignore the Parquet cache and re-read the Excel file")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    try:
        profile = run(args.path, use_cache=not args.no_cache)
    except DatasetValidationError as exc:
        print(f"\nDATASET ERROR: {exc}\n", file=sys.stderr)
        return 2
    _print_summary(profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
