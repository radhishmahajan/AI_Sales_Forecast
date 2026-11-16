"""
Backend settings.

The backend re-uses the ML package (ml/) from the project root, so we add the project root
to sys.path here. All data locations come from ml.config — one source of truth for paths.
Values can be overridden with environment variables (no secrets are needed by this app).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("SFIO_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("SFIO_PROJECT_ROOT", str(PROJECT_ROOT))

APP_NAME = "AI Sales Forecasting & Inventory Optimization API"
APP_VERSION = "1.0.0"
API_PREFIX = "/api"

CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.environ.get("SFIO_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
MAX_UPLOAD_MB: int = int(os.environ.get("SFIO_MAX_UPLOAD_MB", "60"))
PIPELINE_STALE_MINUTES: int = 20   # a 'running' status without heartbeat for this long = interrupted
LOG_LEVEL: str = os.environ.get("SFIO_LOG_LEVEL", "INFO")
