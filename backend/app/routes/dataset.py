"""Dataset upload, validation, preview, summary and preprocessing report."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Query, UploadFile

from app.schemas.models import DatasetStatus, DatasetValidation
from app.services import dataset_service

router = APIRouter(prefix="/dataset", tags=["Dataset"])


@router.post("/upload", response_model=DatasetValidation, summary="Upload 'Online Retail.xlsx'")
def upload(file: UploadFile = File(..., description="The UCI Online Retail Excel file (.xlsx)")) -> dict:
    return dataset_service.save_upload(file.filename, file.file)


@router.post("/validate", response_model=DatasetValidation, summary="Validate the stored dataset file")
def validate() -> dict:
    return dataset_service.validate_current()


@router.get("/status", response_model=DatasetStatus, summary="Dataset, pipeline and model availability")
def status() -> dict:
    return dataset_service.status()


@router.get("/preview", summary="First/last/random rows of the raw dataset")
def preview(section: Literal["head", "tail", "sample"] = Query("head")) -> dict:
    return dataset_service.preview(section)


@router.get("/summary", summary="Stage 1 dataset overview (dimensions, types, missing, duplicates, uniques)")
def summary() -> dict:
    return dataset_service.overview()


@router.get("/preprocessing-report", summary="Stage 3 preprocessing report")
def preprocessing_report() -> dict:
    return dataset_service.preprocessing_report()
