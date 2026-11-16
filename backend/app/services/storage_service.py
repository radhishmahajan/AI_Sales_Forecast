"""
File-storage service — the ONLY place the backend writes application records. No database.

Guarantees
----------
* Atomic writes (temp file + os.replace) for every JSON/CSV write -> no half-written files.
* A per-file lock (threading.RLock) so two requests in this process never interleave writes.
  The app is designed as a SINGLE-USER LOCAL application (one backend process).
* Schema validation of stored JSON with Pydantic; invalid/corrupted files are moved aside to
  '<name>.corrupt-<timestamp>' (kept for manual recovery), logged, and replaced by a default.
* Unique record IDs (UUID4) + UTC timestamps; history files are append-only (never overwritten).
* Safe paths: callers pass logical names; generated file names never come from user input.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from ml import config
from ml.utils import atomic_write_json, atomic_write_text, read_json, to_json_safe, utc_now_iso

logger = logging.getLogger("app.storage")

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()
storage_warnings: list[str] = []

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


def lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def new_record_id() -> str:
    return uuid.uuid4().hex


def storage_path(*parts: str) -> Path:
    """Build a path inside storage/ and refuse anything that escapes it (path traversal)."""
    base = config.STORAGE_DIR.resolve()
    for p in parts:
        if not SAFE_NAME.match(p) or p in {".", ".."}:
            raise ValueError(f"Unsafe storage name: {p!r}")
    path = base.joinpath(*parts).resolve()
    if base not in path.parents and path != base:
        raise ValueError("Path escapes the storage directory")
    return path


def _quarantine(path: Path, reason: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        path.replace(target)
    except OSError:
        pass
    msg = (f"Storage file '{path.name}' was unreadable ({reason}). It was moved to '{target.name}' "
           "and a fresh file was created. Restore it from that copy if needed.")
    logger.error(msg)
    storage_warnings.append(msg)


def load_json(path: Path, default_factory: Callable[[], Any], schema: type[BaseModel] | None = None) -> Any:
    """Load a JSON file, creating it from default_factory if missing; recover from corruption."""
    with lock_for(path):
        if not path.exists():
            data = default_factory()
            atomic_write_json(path, data)
            return data
        try:
            data = read_json(path)
            if schema is not None:
                schema.model_validate(data)
            return data
        except (ValueError, ValidationError) as exc:
            _quarantine(path, type(exc).__name__)
            data = default_factory()
            atomic_write_json(path, data)
            return data


def save_json(path: Path, data: Any, schema: type[BaseModel] | None = None) -> None:
    if schema is not None:
        schema.model_validate(to_json_safe(data))
    with lock_for(path):
        atomic_write_json(path, data)


def append_json_record(path: Path, record: dict[str, Any], schema: type[BaseModel] | None = None,
                       item_schema: type[BaseModel] | None = None) -> dict[str, Any]:
    """Append one record (with new id + timestamp) to a JSON {"records": [...]} file."""
    with lock_for(path):
        doc = load_json(path, lambda: {"records": []}, schema)
        rec = {"record_id": new_record_id(), "created_at": utc_now_iso(), **record}
        if item_schema is not None:
            item_schema.model_validate(to_json_safe(rec))
        doc["records"].append(to_json_safe(rec))
        atomic_write_json(path, doc)
        return rec


def append_csv_row(path: Path, row: dict[str, Any], columns: list[str]) -> None:
    """Append a row to a CSV history file (rewritten atomically; previous rows always preserved)."""
    with lock_for(path):
        existing = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            header = existing.splitlines()[0] if existing else ""
            if header and header.split(",") != columns:
                _quarantine(path, "unexpected CSV header")
                existing = ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        if not existing:
            writer.writeheader()
        writer.writerow({k: to_json_safe(row.get(k)) for k in columns})
        atomic_write_text(path, existing + buf.getvalue())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with lock_for(path):
        if not path.exists():
            return []
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
        except (csv.Error, UnicodeDecodeError) as exc:
            _quarantine(path, type(exc).__name__)
            return []
