"""
Tiny in-memory cache keyed by file path + modification time.

Reading the 520k-row cleaned sales Parquet file takes ~0.5 s; aggregations take longer.
We cache results and automatically refresh them as soon as the pipeline rewrites the file
(its modification time changes). No database or external cache needed.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_lock = threading.Lock()


def cached(path: Path, key: str, compute: Callable[[], Any]) -> Any:
    """Return compute() result, recomputing only when `path` changes."""
    if not path.exists():
        raise FileNotFoundError(path.name)
    mtime = path.stat().st_mtime
    ck = (str(path.resolve()), key)
    with _lock:
        hit = _cache.get(ck)
        if hit and hit[0] == mtime:
            return hit[1]
    value = compute()
    with _lock:
        _cache[ck] = (mtime, value)
    return value


def clear() -> None:
    with _lock:
        _cache.clear()
