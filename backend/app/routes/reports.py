"""Report generation and download."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.schemas.models import ReportInfo, ReportRequest
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("", response_model=ReportInfo, status_code=201, summary="Generate a sales / forecast / inventory report (CSV or PDF)")
def create(body: ReportRequest) -> dict:
    return report_service.generate(body.report_type, body.format)


@router.get("", response_model=list[ReportInfo], summary="Generated reports")
def list_reports() -> list[dict]:
    return report_service.list_reports()


@router.get("/{report_id}/download", summary="Download a generated report")
def download(report_id: str) -> FileResponse:
    path, name, media = report_service.file_for(report_id)
    return FileResponse(path, filename=name, media_type=media)
