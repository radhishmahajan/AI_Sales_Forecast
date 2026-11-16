"""
Dataset upload, validation and the Stage 1 / Stage 3 reports.

Upload flow (the uploaded file is only READ, never executed):
1. Stream the upload to storage/raw/upload_<uuid>.xlsx, aborting above the size limit.
2. Validate it: extension, size, Excel ZIP signature, required columns (header only).
3. Only if valid, atomically move it to data/raw/Online Retail.xlsx (the canonical location).
4. Invalid uploads are deleted. The user then runs the pipeline to profile, clean and train.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, BinaryIO

import pandas as pd

from app import config as app_config
from app.services import pipeline_service
from app.services.storage_service import storage_path
from app.utils.errors import AppError, NotReadyError
from ml import config
from ml.data_loader import DatasetValidationError, build_column_mapping, validate_file
from ml.utils import read_json

CHUNK = 1024 * 1024


def _validate_path(path) -> dict[str, Any]:
    info = validate_file(path, max_size_mb=app_config.MAX_UPLOAD_MB)
    try:
        header = list(pd.read_excel(path, sheet_name=0, nrows=0, engine="openpyxl").columns)
    except Exception as exc:
        raise DatasetValidationError(f"Could not open the workbook ({type(exc).__name__}). The file may be corrupted.") from exc
    mapping = build_column_mapping(header)
    found = sorted(set(mapping.values()))
    missing = [c for c in config.REQUIRED_COLUMNS if c not in found]
    warnings = []
    extra = [str(c) for c in header if str(c) not in mapping]
    if extra:
        warnings.append(f"Unexpected columns will be ignored: {', '.join(extra[:10])}")
    return {
        "valid": not missing,
        "file_name": info["file_name"],
        "file_size_mb": info["file_size_mb"],
        "columns_found": found,
        "missing_columns": missing,
        "warnings": warnings,
        "message": "File is a valid UCI Online Retail workbook." if not missing
        else "Missing required columns: " + ", ".join(missing),
    }


def save_upload(filename: str | None, stream: BinaryIO) -> dict[str, Any]:
    name = os.path.basename(filename or "")
    if not name.lower().endswith(".xlsx"):
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", "Only .xlsx Excel files are accepted (upload 'Online Retail.xlsx').")
    if pipeline_service.is_running():
        raise AppError(409, "PIPELINE_RUNNING", "Wait for the running pipeline to finish before uploading a new dataset.")
    tmp = storage_path("raw", f"upload_{uuid.uuid4().hex}.xlsx")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    limit = app_config.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    try:
        with open(tmp, "wb") as out:
            while chunk := stream.read(CHUNK):
                written += len(chunk)
                if written > limit:
                    raise AppError(413, "FILE_TOO_LARGE", f"File exceeds the {app_config.MAX_UPLOAD_MB} MB limit.")
                out.write(chunk)
        try:
            result = _validate_path(tmp)
        except DatasetValidationError as exc:  # show the user's file name, not the internal temp name
            raise DatasetValidationError(str(exc).replace(tmp.name, name)) from exc
        if not result["valid"]:
            raise AppError(400, "INVALID_DATASET", result["message"])
        config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, config.DEFAULT_DATASET_PATH)
        result["file_name"] = config.DATASET_FILENAME
        result["message"] += " Saved. Run the pipeline to profile, clean and train."
        return result
    finally:
        if tmp.exists():
            tmp.unlink()


def validate_current() -> dict[str, Any]:
    if not config.DEFAULT_DATASET_PATH.exists():
        raise AppError(404, "DATASET_REQUIRED", f"No dataset found. Upload '{config.DATASET_FILENAME}' first.")
    return _validate_path(config.DEFAULT_DATASET_PATH)


def status() -> dict[str, Any]:
    p = config.DEFAULT_DATASET_PATH
    present = p.exists()
    return {
        "dataset_present": present,
        "file_name": p.name if present else None,
        "file_size_mb": round(p.stat().st_size / 1024**2, 2) if present else None,
        "uploaded_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat() if present else None,
        "overview_available": (config.REPORTS_DIR / "01_dataset_overview.json").exists(),
        "preprocessing_available": (config.REPORTS_DIR / "03_preprocessing_report.json").exists(),
        "model_available": (config.ARTIFACTS_DIR / "demand_model.joblib").exists(),
        "pipeline": pipeline_service.get_status(),
    }


def _report(name: str) -> dict[str, Any]:
    try:
        data = read_json(config.REPORTS_DIR / name)
    except ValueError as exc:
        raise AppError(500, "CORRUPTED_REPORT", f"{exc} Re-run the pipeline to regenerate it.") from exc
    if data is None:
        raise NotReadyError()
    return data


def overview() -> dict[str, Any]:
    return _report("01_dataset_overview.json")


def preview(section: str = "head") -> dict[str, Any]:
    ov = overview()
    if section not in {"head", "tail", "sample"}:
        raise AppError(400, "INVALID_SECTION", "section must be head, tail or sample")
    return {"section": section, "rows": ov[section], "columns": [c["name"] for c in ov["columns"]],
            "source": "dataset-derived (raw file, before cleaning)"}


def preprocessing_report() -> dict[str, Any]:
    return _report("03_preprocessing_report.json")
