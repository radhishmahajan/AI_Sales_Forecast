"""
Small, reusable helpers shared by every pipeline stage.

The most important idea here is the ATOMIC WRITE:
    1. Write the new content to a temporary file in the same folder.
    2. Flush it to disk.
    3. Replace the real file in one step with os.replace().
If the program crashes halfway, the old file is still intact — we never end up with
a half-written, corrupted JSON/CSV file. The backend's file-storage service reuses this.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------
def to_json_safe(value: Any) -> Any:
    """Recursively convert pandas/NumPy objects into plain JSON-serialisable Python.

    NaN / NaT / pd.NA become None (JSON null) so reports never contain invalid JSON.
    """
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return to_json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return to_json_safe(value.to_dict())
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, np.ndarray):
        return to_json_safe(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if value is pd.NA or value is pd.NaT:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------
def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    """Write text to *path* atomically (temp file + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Clean up the temp file if anything went wrong; the original stays untouched.
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise
    return path


def atomic_write_json(path: str | Path, data: Any, indent: int = 2) -> Path:
    """Serialise *data* to JSON (after making it JSON-safe) and write atomically."""
    text = json.dumps(to_json_safe(data), indent=indent, ensure_ascii=False)
    return atomic_write_text(path, text + "\n")


def atomic_write_parquet(path: str | Path, df: pd.DataFrame) -> Path:
    """Write a DataFrame to Parquet atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        df.to_parquet(tmp_name, index=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise
    return path


def atomic_write_csv(path: str | Path, df: pd.DataFrame, **kwargs: Any) -> Path:
    """Write a DataFrame to CSV atomically."""
    kwargs.setdefault("index", False)
    return atomic_write_text(path, df.to_csv(**kwargs))


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read JSON; return *default* if the file is missing. Raises ValueError if corrupted."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON file '{path.name}' is corrupted ({exc.msg} at line {exc.lineno}). "
            "Delete it or restore it from a backup and re-run the step that creates it."
        ) from exc


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Fingerprint a file. Used to know whether a cached copy is still up to date."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (used to timestamp every report)."""
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
