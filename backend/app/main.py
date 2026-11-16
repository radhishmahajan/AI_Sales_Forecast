"""
FastAPI application entry point.

    cd backend
    uvicorn app.main:app --reload

Swagger UI: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from app import config as app_config  # noqa: F401  (sets up sys.path for the ml package)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import analytics, dataset, forecast, inventory, models, products, reports, system
from app.utils.errors import register_error_handlers
from ml import config

logging.basicConfig(level=app_config.LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_directories()
    for sub in ("products", "forecasts", "inventory", "reports", "raw"):
        (config.STORAGE_DIR / sub).mkdir(parents=True, exist_ok=True)
    logging.getLogger("app").info("API ready. Project root: %s", config.PROJECT_ROOT.name)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=app_config.APP_NAME,
    version=app_config.APP_VERSION,
    description="Database-free retail analytics API: UCI Online Retail data, ML demand forecasting and inventory "
                "optimisation. All storage is file-based (CSV / JSON / Parquet / Joblib).",
)
app.add_middleware(CORSMiddleware, allow_origins=app_config.CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT"], allow_headers=["*"])
register_error_handlers(app)

for r in (system.router, dataset.router, analytics.router, products.router, forecast.router, models.router,
          inventory.router, reports.router):
    app.include_router(r, prefix=app_config.API_PREFIX)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": app_config.APP_NAME, "docs": "/docs", "health": f"{app_config.API_PREFIX}/health"}
