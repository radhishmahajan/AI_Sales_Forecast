"""
Shared pytest fixtures.

IMPORTANT — SYNTHETIC TEST FIXTURES ONLY
These tiny hand-made tables exist ONLY to test the code's behaviour on edge cases
(cancellations, duplicates, missing values, bad types). They are NOT sales data, are
written only to pytest's temporary folders, and never appear in the app or reports.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from ml import config

FIXTURE_LABEL = "SYNTHETIC TEST FIXTURE - NOT REAL DATA"


def make_fixture_rows() -> pd.DataFrame:
    """12 synthetic invoice lines covering the edge cases the loader must handle."""
    rows = [
        # InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country
        (536365, "85123A", "TEST PRODUCT A", 6, datetime(2010, 12, 1, 8, 26), 2.55, 17850, "United Kingdom"),
        (536365, 71053, "TEST PRODUCT B", 6, datetime(2010, 12, 1, 8, 26), 3.39, 17850, "United Kingdom"),
        (536366, 22633, "TEST PRODUCT C", 6, datetime(2010, 12, 1, 8, 28), 1.85, 17850, "United Kingdom"),
        # exact duplicate of the row above
        (536366, 22633, "TEST PRODUCT C", 6, datetime(2010, 12, 1, 8, 28), 1.85, 17850, "United Kingdom"),
        # cancellation (C prefix, negative quantity, non-standard code)
        ("C536379", "D", "Discount", -1, datetime(2010, 12, 1, 9, 41), 27.50, 14527, "United Kingdom"),
        # missing CustomerID and Description, zero price
        (536414, 22139, None, 56, datetime(2010, 12, 1, 11, 52), 0.0, None, "United Kingdom"),
        # negative quantity WITHOUT C prefix (stock adjustment)
        (536589, 21777, None, -10, datetime(2010, 12, 1, 16, 50), 0.0, None, "United Kingdom"),
        # postage line (non-standard StockCode)
        (536370, "POST", "POSTAGE", 3, datetime(2010, 12, 1, 8, 45), 18.0, 12583, "France"),
        # non-integer quantity -> must be reported as invalid during coercion
        (536371, 22086, "TEST PRODUCT D", 2.5, datetime(2010, 12, 2, 9, 0), 2.10, 13047, "France"),
        # invalid date text -> must be reported as invalid during coercion
        (536372, 22086, "TEST PRODUCT D", 4, "not-a-date", 2.10, 13047, "Germany"),
        # negative price (bad-debt adjustment style)
        ("A563185", "B", "Adjust bad debt", 1, datetime(2011, 8, 12, 14, 50), -11062.06, None, "United Kingdom"),
        (581587, 22138, "TEST PRODUCT E", 3, datetime(2011, 12, 9, 12, 50), 4.95, 12680, "France"),
    ]
    return pd.DataFrame(rows, columns=list(config.REQUIRED_COLUMNS))


def write_xlsx(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, engine="openpyxl")
    return path


@pytest.fixture
def fixture_df() -> pd.DataFrame:
    return make_fixture_rows()


@pytest.fixture
def fixture_xlsx(tmp_path: Path, fixture_df: pd.DataFrame) -> Path:
    return write_xlsx(fixture_df, tmp_path / "raw" / "Online Retail.xlsx")


@pytest.fixture
def sample_sales() -> pd.DataFrame:
    """Cleaned SALE rows built from the synthetic generator (tests only)."""
    from ml.data_loader import coerce_types
    from ml.preprocessing import preprocess
    from tests.synthetic import synthetic_transactions

    typed, _ = coerce_types(synthetic_transactions())
    return preprocess(typed).sales


def _patch_paths(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    for name, value in {
        "PROJECT_ROOT": root,
        "DATA_DIR": root / "data",
        "RAW_DATA_DIR": root / "data" / "raw",
        "PROCESSED_DATA_DIR": root / "data" / "processed",
        "REPORTS_DIR": root / "data" / "reports",
        "FIGURES_DIR": root / "data" / "reports" / "figures",
        "ARTIFACTS_DIR": root / "artifacts",
        "STORAGE_DIR": root / "storage",
        "DEFAULT_DATASET_PATH": root / "data" / "raw" / config.DATASET_FILENAME,
    }.items():
        monkeypatch.setattr(config, name, value)
    config.ensure_directories()
    (root / "docs").mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def trained_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the WHOLE pipeline once (fast mode) on synthetic data in a temp project folder."""
    from ml import pipeline
    from tests.synthetic import synthetic_transactions

    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("trained_project")
    _patch_paths(mp, root)
    write_xlsx(synthetic_transactions(), config.DEFAULT_DATASET_PATH)
    pipeline.run_pipeline(fast=True, top_n=6)
    mp.undo()
    return root


@pytest.fixture
def use_trained_project(trained_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _patch_paths(monkeypatch, trained_project)
    return trained_project


@pytest.fixture
def isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every output folder to a temp directory so tests never touch real data."""
    root = tmp_path / "project"
    monkeypatch.setattr(config, "PROJECT_ROOT", root)
    monkeypatch.setattr(config, "DATA_DIR", root / "data")
    monkeypatch.setattr(config, "RAW_DATA_DIR", root / "data" / "raw")
    monkeypatch.setattr(config, "PROCESSED_DATA_DIR", root / "data" / "processed")
    monkeypatch.setattr(config, "REPORTS_DIR", root / "data" / "reports")
    monkeypatch.setattr(config, "FIGURES_DIR", root / "data" / "reports" / "figures")
    monkeypatch.setattr(config, "ARTIFACTS_DIR", root / "artifacts")
    monkeypatch.setattr(config, "STORAGE_DIR", root / "storage")
    monkeypatch.setattr(config, "DEFAULT_DATASET_PATH", root / "data" / "raw" / config.DATASET_FILENAME)
    config.ensure_directories()
    return root
