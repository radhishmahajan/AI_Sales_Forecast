"""
Runs the ML pipeline in a SEPARATE PROCESS so training never blocks the API.

`python -m ml.pipeline` writes progress to storage/pipeline_status.json; this service starts
it and reads that file. If the server restarts during a run, the status file's heartbeat
tells us whether the run is still alive (no OS-specific process signalling needed).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from app import config as app_config
from app.utils.errors import AppError
from ml import config
from ml.pipeline import STEPS, read_status

logger = logging.getLogger("app.pipeline")

_process: subprocess.Popen | None = None
_lock = threading.Lock()


def _heartbeat_age_minutes(status: dict[str, Any]) -> float | None:
    hb = status.get("heartbeat")
    if not hb:
        return None
    try:
        t = datetime.fromisoformat(hb.rstrip("Z")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - t).total_seconds() / 60


def get_status() -> dict[str, Any]:
    status = read_status()
    with _lock:
        alive = _process is not None and _process.poll() is None
        exit_code = None if _process is None else _process.poll()
    if status.get("state") == "running" and not alive:
        age = _heartbeat_age_minutes(status)
        if exit_code not in (None, 0) or (age is not None and age > app_config.PIPELINE_STALE_MINUTES):
            status["state"] = "interrupted"
            status["error"] = status.get("error") or "The pipeline process stopped before finishing. Run it again."
    status.setdefault("steps", [{"name": n, "label": l, "state": "pending"} for n, l in STEPS])
    status.setdefault("log", [])
    return status


def is_running() -> bool:
    return get_status().get("state") == "running"


def start(fast: bool = False) -> dict[str, Any]:
    global _process
    if not config.DEFAULT_DATASET_PATH.exists():
        raise AppError(400, "DATASET_REQUIRED", "Upload 'Online Retail.xlsx' before running the pipeline.")
    with _lock:
        if (_process is not None and _process.poll() is None) or read_status().get("state") == "running" and \
                (_heartbeat_age_minutes(read_status()) or 0) < app_config.PIPELINE_STALE_MINUTES:
            raise AppError(409, "PIPELINE_RUNNING", "The pipeline is already running.")
        cmd = [sys.executable, "-m", "ml.pipeline"] + (["--fast"] if fast else [])
        env = {**os.environ, "SFIO_PROJECT_ROOT": str(config.PROJECT_ROOT)}
        log_file = open(config.STORAGE_DIR / "pipeline_run.log", "w", encoding="utf-8")  # noqa: SIM115
        _process = subprocess.Popen(cmd, cwd=str(config.PROJECT_ROOT), env=env, stdout=log_file, stderr=subprocess.STDOUT)
        logger.info("Pipeline started (pid %s)", _process.pid)
    return {"started": True, "message": "Pipeline started. Training takes about 5-8 minutes; progress is shown live."}


def wait(timeout: float | None = None) -> int | None:
    """Wait for the current run (used by tests and scripts)."""
    with _lock:
        proc = _process
    return None if proc is None else proc.wait(timeout=timeout)
