"""Health, pipeline control and settings."""

from __future__ import annotations

from fastapi import APIRouter, status

from app import config as app_config
from app.schemas.models import AppSettings, HealthResponse, PipelineRunRequest, PipelineStatus
from app.services import analytics_service, forecast_service, pipeline_service
from app.services.storage_service import save_json, storage_warnings
from ml import config

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health() -> dict:
    return {"status": "ok", "version": app_config.APP_VERSION,
            "dataset_present": config.DEFAULT_DATASET_PATH.exists(),
            "pipeline_state": pipeline_service.get_status().get("state", "never_run"),
            "model_available": forecast_service.is_model_loadable(),
            "storage_warnings": storage_warnings[-5:]}


@router.post("/pipeline/run", status_code=status.HTTP_202_ACCEPTED, summary="Start preprocessing + training in the background")
def run_pipeline(body: PipelineRunRequest | None = None) -> dict:
    return pipeline_service.start(fast=bool(body and body.fast))


@router.get("/pipeline/status", response_model=PipelineStatus, summary="Live pipeline progress")
def pipeline_status() -> dict:
    return pipeline_service.get_status()


@router.get("/settings", response_model=AppSettings, summary="Application settings (JSON file)")
def get_settings() -> dict:
    return analytics_service.settings_defaults()


@router.put("/settings", response_model=AppSettings, summary="Update application settings")
def put_settings(body: AppSettings) -> dict:
    save_json(config.STORAGE_DIR / "settings.json", body.model_dump(), AppSettings)
    return body.model_dump()
