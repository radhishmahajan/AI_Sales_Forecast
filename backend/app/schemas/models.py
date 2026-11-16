"""
Pydantic request/response schemas.

Requests are validated strictly (types, ranges, allowed values) so bad input is rejected with
HTTP 422 before any business logic runs. Large analytical responses use typed top-level fields
with flexible nested dicts where the shape mirrors the saved JSON reports.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ValueSource = Literal["dataset-derived", "user-entered", "model-predicted", "calculated"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# --------------------------------------------------------------------------- system
class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    dataset_present: bool
    pipeline_state: str
    model_available: bool
    storage_warnings: list[str] = []


class PipelineStep(BaseModel):
    name: str
    label: str
    state: str
    seconds: Optional[float] = None


class PipelineStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    state: str
    run_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_step: Optional[str] = None
    error: Optional[str] = None
    steps: list[PipelineStep] = []
    log: list[str] = []
    result: Optional[dict[str, Any]] = None


class PipelineRunRequest(BaseModel):
    fast: bool = Field(False, description="Quick run with fewer tuning candidates (for testing).")


# --------------------------------------------------------------------------- dataset
class DatasetValidation(BaseModel):
    valid: bool
    file_name: str
    file_size_mb: float
    columns_found: list[str]
    missing_columns: list[str]
    warnings: list[str]
    message: str


class DatasetStatus(BaseModel):
    dataset_present: bool
    file_name: Optional[str] = None
    file_size_mb: Optional[float] = None
    uploaded_at: Optional[str] = None
    overview_available: bool
    preprocessing_available: bool
    model_available: bool
    pipeline: PipelineStatus


# --------------------------------------------------------------------------- forecasting
class ForecastRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=20)
    horizon_days: Literal[7, 14, 30] = 7

    @field_validator("stock_code")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stock_code must not be blank")
        return v


class ForecastDay(BaseModel):
    date: str
    predicted_demand: float
    is_open: bool
    source: str


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())
    record_id: str
    created_at: str
    stock_code: str
    description: Optional[str] = None
    horizon_days: int
    forecast_origin: str
    model_name: Optional[str] = None
    daily: list[ForecastDay]
    summary: dict[str, Any]
    weekly: list[dict[str, Any]]
    history: list[dict[str, Any]]
    backtest: list[dict[str, Any]]
    warnings: list[str]
    uncertainty: str


# --------------------------------------------------------------------------- inventory
class InventoryRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=20)
    current_stock: float = Field(..., ge=0, le=10_000_000, description="Units on hand (user-entered).")
    lead_time_days: int = Field(..., ge=1, le=365, description="Supplier lead time in days (user-entered).")
    service_level: float = Field(0.95, ge=0.5, le=0.999, description="Target probability of no stockout during lead time.")
    review_period_days: int = Field(7, ge=1, le=90)
    min_order_qty: Optional[int] = Field(None, ge=0, le=10_000_000)
    pack_size: Optional[int] = Field(None, ge=1, le=100_000)
    max_capacity: Optional[int] = Field(None, gt=0, le=100_000_000)

    @field_validator("stock_code")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stock_code must not be blank")
        return v


class InventoryResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    stock_code: str
    description: Optional[str] = None
    status: Literal["Critical Stock", "Low Stock", "Healthy Stock", "Overstocked"]
    average_daily_demand: float
    safety_stock: float
    reorder_point: float
    target_stock: float
    suggested_order_quantity: int
    record_id: Optional[str] = None
    created_at: Optional[str] = None


# --------------------------------------------------------------------------- stored files
class StoredRecords(BaseModel):
    """Shape of storage/inventory/recommendations.json."""
    records: list[dict[str, Any]]


class StoredInventoryRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    record_id: str
    created_at: str
    stock_code: str
    status: str
    suggested_order_quantity: int


class AppSettings(BaseModel):
    default_service_level: float = Field(0.95, ge=0.5, le=0.999)
    default_lead_time_days: int = Field(7, ge=1, le=365)
    default_review_period_days: int = Field(7, ge=1, le=90)
    default_forecast_horizon: Literal[7, 14, 30] = 14
    currency_symbol: str = Field("£", max_length=3)


# --------------------------------------------------------------------------- reports
class ReportRequest(BaseModel):
    report_type: Literal["sales", "forecast", "inventory"]
    format: Literal["csv", "pdf"] = "csv"


class ReportInfo(BaseModel):
    report_id: str
    report_type: str
    format: str
    file_name: str
    created_at: str
    size_bytes: int
    rows: Optional[int] = None
    download_url: str
