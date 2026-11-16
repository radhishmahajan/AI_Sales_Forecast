"""API tests (FastAPI TestClient) against a temp project trained on SYNTHETIC data."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
import sys  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import data_cache, storage_service  # noqa: E402
from ml import config, eda  # noqa: E402
from tests.conftest import write_xlsx  # noqa: E402
from tests.synthetic import synthetic_transactions  # noqa: E402


@pytest.fixture
def client(use_trained_project: Path) -> TestClient:
    data_cache.clear()
    return TestClient(app)


@pytest.fixture
def empty_client(isolated_project: Path) -> TestClient:
    data_cache.clear()
    return TestClient(app)


def code(client: TestClient) -> str:
    return client.get("/api/products/forecastable").json()[0]["StockCode"]


# ---------------------------------------------------------------- system / dataset
def test_health(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["model_available"] and body["dataset_present"]


def test_dataset_status_summary_preview(client: TestClient) -> None:
    assert client.get("/api/dataset/status").json()["overview_available"]
    assert client.get("/api/dataset/summary").json()["dimensions"]["columns"] == 8
    assert len(client.get("/api/dataset/preview?section=sample").json()["rows"]) == 5
    assert client.get("/api/dataset/preview?section=bad").status_code == 422
    assert client.get("/api/dataset/preprocessing-report").json()["counts"]["retained_sale_rows"] > 0
    assert client.post("/api/dataset/validate").json()["valid"]


def test_upload_rejects_wrong_type_and_fake_excel(empty_client: TestClient) -> None:
    r = empty_client.post("/api/dataset/upload", files={"file": ("data.csv", b"a,b\n1,2", "text/csv")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    r = empty_client.post("/api/dataset/upload", files={"file": ("Online Retail.xlsx", b"not excel", "application/octet-stream")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_DATASET"
    assert not config.DEFAULT_DATASET_PATH.exists()
    assert not list((config.STORAGE_DIR / "raw").glob("upload_*"))       # rejected uploads are deleted


def test_upload_valid_file(empty_client: TestClient, tmp_path: Path) -> None:
    src = write_xlsx(synthetic_transactions(days=80), tmp_path / "x.xlsx")
    r = empty_client.post("/api/dataset/upload", files={"file": ("Online Retail.xlsx", src.read_bytes(), "application/vnd.ms-excel")})
    assert r.status_code == 200 and r.json()["valid"]
    assert config.DEFAULT_DATASET_PATH.exists()


def test_missing_artifacts_give_clear_errors(empty_client: TestClient) -> None:
    for url in ("/api/dashboard", "/api/models/performance", "/api/products", "/api/dataset/summary"):
        r = empty_client.get(url)
        assert r.status_code == 409 and r.json()["error"]["code"] in {"PIPELINE_REQUIRED"}, url
    r = empty_client.post("/api/forecast", json={"stock_code": "90000", "horizon_days": 7})
    assert r.status_code == 409 and r.json()["error"]["code"] == "MODEL_NOT_AVAILABLE"
    r = empty_client.post("/api/pipeline/run")
    assert r.status_code == 400 and r.json()["error"]["code"] == "DATASET_REQUIRED"
    assert empty_client.get("/api/health").json()["model_available"] is False


# ---------------------------------------------------------------- analytics / products
def test_dashboard_numbers_match_ml_functions(client: TestClient) -> None:
    import pandas as pd

    body = client.get("/api/dashboard").json()
    expected = eda.sales_kpis(pd.read_parquet(config.PROCESSED_DATA_DIR / "cleaned_sales.parquet"))
    assert body["kpis"]["total_revenue"] == expected["total_revenue"]
    assert body["kpis"]["total_transactions"] == expected["total_transactions"]
    assert body["model"]["best_model"]
    for url in ("/api/analytics/sales?freq=W", "/api/analytics/top-products?by=revenue&n=3", "/api/analytics/countries",
                "/api/analytics/time-patterns", "/api/analytics/variability?min_sale_days=1", "/api/analytics/abc",
                "/api/analytics/slow-moving", "/api/analytics/customers", "/api/analytics/eda"):
        assert client.get(url).status_code == 200, url
    assert client.get("/api/analytics/sales?freq=X").status_code == 422


def test_products(client: TestClient) -> None:
    lst = client.get("/api/products?search=SYNTHETIC&limit=3").json()
    assert lst["total"] >= 3 and len(lst["items"]) == 3
    c = lst["items"][0]["StockCode"]
    detail = client.get(f"/api/products/{c}").json()
    assert detail["product"]["StockCode"] == c and detail["monthly"]
    assert client.get("/api/products/DOES-NOT-EXIST").status_code == 404
    assert client.get("/api/products?abc_class=Z").status_code == 422


# ---------------------------------------------------------------- forecasting
@pytest.mark.parametrize("h", [7, 14, 30])
def test_forecast_and_history(client: TestClient, h: int) -> None:
    c = code(client)
    r = client.post("/api/forecast", json={"stock_code": c, "horizon_days": h})
    assert r.status_code == 200
    body = r.json()
    assert len(body["daily"]) == h and body["record_id"]
    hist = client.get(f"/api/forecast/history?stock_code={c}").json()
    assert hist[0]["record_id"] == body["record_id"] and hist[0]["horizon_days"] == h
    assert client.get(f"/api/forecast/history/{body['record_id']}").json()["stock_code"] == c


def test_forecast_validation(client: TestClient) -> None:
    c = code(client)
    assert client.post("/api/forecast", json={"stock_code": c, "horizon_days": 10}).status_code == 422
    assert client.post("/api/forecast", json={"stock_code": "  ", "horizon_days": 7}).status_code == 422
    r = client.post("/api/forecast", json={"stock_code": "NOPE", "horizon_days": 7})
    assert r.status_code == 404 and r.json()["error"]["code"] == "PRODUCT_NOT_FORECASTABLE"
    assert client.get("/api/forecast/history/../../etc").status_code == 404


def test_models(client: TestClient) -> None:
    perf = client.get("/api/models/performance").json()
    assert perf["best_model"] and perf["comparison"] and perf["recursive_backtest_test"]
    imp = client.get("/api/models/feature-importance").json()
    assert len(imp["features"]) > 10 and imp["business_summary"]


# ---------------------------------------------------------------- inventory
@pytest.mark.parametrize("bad", [{"current_stock": -1}, {"lead_time_days": 0}, {"lead_time_days": 3.5},
                                 {"service_level": 1.5}, {"service_level": 0.2}, {"pack_size": 0}])
def test_inventory_rejects_invalid_inputs(client: TestClient, bad: dict) -> None:
    body = {"stock_code": code(client), "current_stock": 10, "lead_time_days": 5, "service_level": 0.95, **bad}
    assert client.post("/api/inventory/calculate", json=body).status_code == 422


def test_inventory_save_and_persist(client: TestClient) -> None:
    c = code(client)
    body = {"stock_code": c, "current_stock": 0, "lead_time_days": 7, "service_level": 0.95, "min_order_qty": 10, "pack_size": 6}
    calc = client.post("/api/inventory/calculate", json=body).json()
    assert calc["status"] == "Critical Stock" and calc["suggested_order_quantity"] % 6 == 0
    saved = client.post("/api/inventory/recommendations", json=body)
    assert saved.status_code == 201
    data_cache.clear()                                                    # simulate an application restart
    fresh = TestClient(app)
    recs = fresh.get(f"/api/inventory/recommendations?stock_code={c}").json()
    assert recs[0]["record_id"] == saved.json()["record_id"]
    risk = fresh.get("/api/inventory/risk-summary").json()
    assert risk["status_counts"]["Critical Stock"] >= 1
    assert fresh.get("/api/inventory/inputs").json()[c]["lead_time_days"] == 7
    r = client.post("/api/inventory/calculate", json={**body, "stock_code": "NOPE"})
    assert r.status_code == 404


# ---------------------------------------------------------------- reports & settings
@pytest.mark.parametrize("rtype", ["sales", "forecast", "inventory"])
@pytest.mark.parametrize("fmt", ["csv", "pdf"])
def test_reports(client: TestClient, rtype: str, fmt: str) -> None:
    r = client.post("/api/reports", json={"report_type": rtype, "format": fmt})
    assert r.status_code == 201
    dl = client.get(r.json()["download_url"])
    assert dl.status_code == 200
    assert dl.content.startswith(b"%PDF") if fmt == "pdf" else len(dl.content) > 0
    assert client.get("/api/reports/unknown/download").status_code == 404


def test_settings_roundtrip(client: TestClient) -> None:
    s = client.get("/api/settings").json()
    s["default_lead_time_days"] = 12
    assert client.put("/api/settings", json=s).json()["default_lead_time_days"] == 12
    assert client.put("/api/settings", json={**s, "default_service_level": 2}).status_code == 422


# ---------------------------------------------------------------- storage safety
def test_corrupted_storage_file_is_quarantined(client: TestClient) -> None:
    path = config.STORAGE_DIR / "inventory" / "recommendations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")
    r = client.get("/api/inventory/recommendations")
    assert r.status_code == 200 and r.json() == []
    assert list(path.parent.glob("recommendations.json.corrupt-*"))
    assert json.loads(path.read_text()) == {"records": []}


def test_storage_path_blocks_traversal(use_trained_project: Path) -> None:
    with pytest.raises(ValueError):
        storage_service.storage_path("..", "secret.txt")
    with pytest.raises(ValueError):
        storage_service.storage_path("reports", "../../x")
