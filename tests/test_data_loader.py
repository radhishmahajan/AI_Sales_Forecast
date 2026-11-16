"""Tests for Stage 1 (ml/data_loader.py). Uses synthetic fixtures only — see conftest.py."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ml import config, data_loader
from ml.data_loader import DatasetValidationError
from ml.utils import atomic_write_json, read_json
from tests.conftest import write_xlsx


# --------------------------------------------------------------------------- file validation
def test_missing_file_raises_helpful_error(tmp_path: Path) -> None:
    with pytest.raises(DatasetValidationError, match="not found"):
        data_loader.validate_file(tmp_path / "Online Retail.xlsx")


def test_unsupported_extension_rejected(tmp_path: Path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n")
    with pytest.raises(DatasetValidationError, match="Unsupported file type"):
        data_loader.validate_file(csv)


def test_empty_file_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "Online Retail.xlsx"
    empty.write_bytes(b"")
    with pytest.raises(DatasetValidationError, match="empty"):
        data_loader.validate_file(empty)


def test_renamed_text_file_rejected_by_signature(tmp_path: Path) -> None:
    fake = tmp_path / "Online Retail.xlsx"
    fake.write_text("this is not an excel file")
    with pytest.raises(DatasetValidationError, match="signature"):
        data_loader.validate_file(fake)


def test_size_limit_enforced(fixture_xlsx: Path) -> None:
    with pytest.raises(DatasetValidationError, match="limit"):
        data_loader.validate_file(fixture_xlsx, max_size_mb=0.000001)


def test_valid_file_info_has_no_full_path(fixture_xlsx: Path) -> None:
    info = data_loader.validate_file(fixture_xlsx)
    assert info["file_name"] == "Online Retail.xlsx"
    assert str(fixture_xlsx.parent) not in json.dumps(info)


# --------------------------------------------------------------------------- column validation
def test_missing_columns_listed(tmp_path: Path, fixture_df: pd.DataFrame) -> None:
    path = write_xlsx(fixture_df.drop(columns=["Quantity", "Country"]), tmp_path / "Online Retail.xlsx")
    with pytest.raises(DatasetValidationError, match="Quantity, Country"):
        data_loader.load_dataset(path, use_cache=False)


def test_column_names_with_spaces_and_case_are_normalised(tmp_path: Path, fixture_df: pd.DataFrame) -> None:
    messy = fixture_df.rename(columns={"Quantity": " quantity ", "CustomerID": "customerid"})
    path = write_xlsx(messy, tmp_path / "Online Retail.xlsx")
    result = data_loader.load_dataset(path, use_cache=False)
    assert list(result.df.columns) == list(config.REQUIRED_COLUMNS)
    assert any("Normalised" in w for w in result.warnings)


def test_header_only_file_is_empty_dataset_error(tmp_path: Path, fixture_df: pd.DataFrame) -> None:
    path = write_xlsx(fixture_df.iloc[0:0], tmp_path / "Online Retail.xlsx")
    with pytest.raises(DatasetValidationError, match="no data rows"):
        data_loader.load_dataset(path, use_cache=False)


# --------------------------------------------------------------------------- type coercion
def test_types_are_coerced_and_invalid_values_counted(fixture_xlsx: Path) -> None:
    result = data_loader.load_dataset(fixture_xlsx, use_cache=False)
    df = result.df
    for col, expected in config.EXPECTED_DTYPES.items():
        assert str(df[col].dtype) == expected, col
    # Mixed numeric/text invoice numbers both become text
    assert set(df["InvoiceNo"].head(2)) == {"536365"}
    assert "C536379" in set(df["InvoiceNo"])
    # numeric stock code is read as text without '.0'
    assert "71053" in set(df["StockCode"])
    rep = result.coercion_report
    assert rep["Quantity"]["invalid_coerced"] == 1      # the 2.5 quantity
    assert rep["InvoiceDate"]["invalid_coerced"] == 1   # 'not-a-date'
    assert rep["CustomerID"]["missing_before"] == 3
    assert rep["Description"]["missing_before"] == 2


# --------------------------------------------------------------------------- cache
def test_cache_is_used_and_invalidated_when_file_changes(tmp_path: Path, fixture_df: pd.DataFrame) -> None:
    path = write_xlsx(fixture_df, tmp_path / "Online Retail.xlsx")
    cache = tmp_path / "cache"
    first = data_loader.load_dataset(path, cache_dir=cache)
    second = data_loader.load_dataset(path, cache_dir=cache)
    assert not first.from_cache and second.from_cache
    pd.testing.assert_frame_equal(first.df, second.df)

    write_xlsx(fixture_df.head(5), path)  # file content changes -> fingerprint changes
    third = data_loader.load_dataset(path, cache_dir=cache)
    assert not third.from_cache and len(third.df) == 5


def test_corrupted_cache_meta_falls_back_to_excel(tmp_path: Path, fixture_xlsx: Path) -> None:
    cache = tmp_path / "cache"
    data_loader.load_dataset(fixture_xlsx, cache_dir=cache)
    (cache / config.RAW_CACHE_META_FILENAME).write_text("{ broken json")
    result = data_loader.load_dataset(fixture_xlsx, cache_dir=cache)
    assert not result.from_cache and len(result.df) == 12


# --------------------------------------------------------------------------- profiling
def test_profile_counts_match_fixture(fixture_xlsx: Path) -> None:
    result = data_loader.load_dataset(fixture_xlsx, use_cache=False)
    p = data_loader.profile_dataset(result)
    assert p["dimensions"] == {"rows": 12, "columns": 8}
    assert p["duplicates"]["exact_duplicate_rows"] == 1
    q = p["quality_observations"]
    assert q["cancellation_rows_invoice_starts_with_C"] == 1
    assert q["negative_quantity_rows"] == 2
    assert q["negative_quantity_rows_not_cancelled"] == 1
    assert q["zero_unit_price_rows"] == 2
    assert q["negative_unit_price_rows"] == 1
    assert q["missing_customer_id_rows"] == 3
    assert q["non_standard_stockcode_rows"] == 3  # D, POST, B
    u = p["unique_counts"]
    assert u["invoices"] == 10 and u["cancelled_invoices"] == 1 and u["countries"] == 3
    assert len(p["head"]) == 5 and len(p["tail"]) == 5 and len(p["sample"]) == 5
    assert p["uci_documented_check"]["rows_match"] is False  # fixture is not the real dataset
    json.dumps(p)  # must be strictly JSON-serialisable (no NaN objects)


def test_sample_is_reproducible(fixture_xlsx: Path) -> None:
    result = data_loader.load_dataset(fixture_xlsx, use_cache=False)
    assert data_loader.profile_dataset(result)["sample"] == data_loader.profile_dataset(result)["sample"]


def test_empty_dataframe_cannot_be_profiled() -> None:
    with pytest.raises(DatasetValidationError):
        data_loader.profile_dataset(pd.DataFrame(columns=list(config.REQUIRED_COLUMNS)))


def test_run_writes_json_and_markdown_reports(isolated_project: Path, fixture_df: pd.DataFrame) -> None:
    write_xlsx(fixture_df, config.DEFAULT_DATASET_PATH)
    data_loader.run()
    reports = config.REPORTS_DIR
    data = json.loads((reports / "01_dataset_overview.json").read_text())
    assert data["dimensions"]["rows"] == 12
    md = (reports / "01_dataset_overview.md").read_text()
    assert "Dataset Overview Report" in md and "Missing values" in md


def test_cli_returns_error_code_when_dataset_missing(isolated_project: Path, capsys: pytest.CaptureFixture) -> None:
    assert data_loader.main([]) == 2
    assert "not found" in capsys.readouterr().err


# --------------------------------------------------------------------------- colab helper
def test_colab_upload_helper_saves_canonical_name(tmp_path: Path, fixture_xlsx: Path) -> None:
    saved = data_loader.load_uploaded_colab_file({"Online Retail (1).xlsx": fixture_xlsx.read_bytes()}, tmp_path)
    assert saved.name == config.DATASET_FILENAME and saved.stat().st_size > 0
    with pytest.raises(DatasetValidationError):
        data_loader.load_uploaded_colab_file({"notes.txt": b"x"}, tmp_path)


# --------------------------------------------------------------------------- utils
def test_atomic_json_roundtrip_and_corruption_detection(tmp_path: Path) -> None:
    target = tmp_path / "x.json"
    atomic_write_json(target, {"a": float("nan"), "b": pd.Timestamp("2011-01-01")})
    assert read_json(target) == {"a": None, "b": "2011-01-01T00:00:00"}
    assert not list(tmp_path.glob("*.tmp"))  # no temp files left behind
    target.write_text("{bad")
    with pytest.raises(ValueError, match="corrupted"):
        read_json(target)
    assert read_json(tmp_path / "missing.json", default={}) == {}
