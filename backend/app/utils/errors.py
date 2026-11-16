"""Application errors and their HTTP mapping (routes stay free of try/except clutter)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ml.data_loader import DatasetValidationError
from ml.forecasting import ModelNotAvailableError, ProductNotForecastableError
from ml.inventory import InventoryInputError

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """An error with an HTTP status, a stable machine-readable code and a user-friendly message."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


class NotReadyError(AppError):
    def __init__(self, message: str = "Data not available yet. Upload the dataset and run the pipeline first.") -> None:
        super().__init__(409, "PIPELINE_REQUIRED", message)


class NotFoundError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(404, "NOT_FOUND", message)


def _payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_payload(exc.code, exc.message))

    @app.exception_handler(DatasetValidationError)
    async def dataset_error(_: Request, exc: DatasetValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content=_payload("INVALID_DATASET", str(exc)))

    @app.exception_handler(ModelNotAvailableError)
    async def model_error(_: Request, exc: ModelNotAvailableError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_payload("MODEL_NOT_AVAILABLE", str(exc)))

    @app.exception_handler(ProductNotForecastableError)
    async def product_error(_: Request, exc: ProductNotForecastableError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_payload("PRODUCT_NOT_FORECASTABLE", str(exc)))

    @app.exception_handler(InventoryInputError)
    async def inventory_error(_: Request, exc: InventoryInputError) -> JSONResponse:
        return JSONResponse(status_code=422, content=_payload("INVALID_INVENTORY_INPUT", str(exc)))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Never leak stack traces or local file paths to the client; full details go to the log.
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content=_payload("INTERNAL_ERROR", "Unexpected server error. See backend log."))
