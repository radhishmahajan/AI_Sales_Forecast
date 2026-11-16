"""Model performance and explainability."""

from __future__ import annotations

from fastapi import APIRouter

from app.services import model_service

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("/performance", summary="Model comparison, metrics, backtests and residuals")
def performance() -> dict:
    return model_service.performance()


@router.get("/feature-importance", summary="Permutation feature importance + business explanations")
def feature_importance() -> dict:
    return model_service.feature_importance()
