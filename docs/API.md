# REST API Reference

- Base URL: `http://127.0.0.1:8000/api`
- Interactive Swagger docs: `http://127.0.0.1:8000/docs`

Every error uses one JSON shape:

```json
{ "error": { "code": "PIPELINE_REQUIRED", "message": "Data not available yet. Upload the dataset and run the pipeline first." } }
```

Request-body validation errors return HTTP 422 with FastAPI's standard `detail` list.

| Status | Code | When |
|---|---|---|
| 400 | `INVALID_DATASET`, `UNSUPPORTED_FILE_TYPE`, `DATASET_REQUIRED` | Bad upload, or no dataset when starting the pipeline |
| 404 | `NOT_FOUND`, `PRODUCT_NOT_FORECASTABLE` | Unknown product, report or forecast record |
| 409 | `PIPELINE_REQUIRED`, `MODEL_NOT_AVAILABLE`, `PIPELINE_RUNNING` | Data or model not ready, or a run already in progress |
| 413 | `FILE_TOO_LARGE` | Upload above 60 MB |
| 422 | validation / `INVALID_INVENTORY_INPUT` | Invalid horizon, stock, lead time, service level, etc. |

## System

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check: dataset present, pipeline state, model loadable, storage warnings |
| POST | `/pipeline/run` | Start the full ML pipeline in a background process (202). Body `{ "fast": false }` |
| GET | `/pipeline/status` | Live step-by-step progress and log |
| GET / PUT | `/settings` | Application defaults (service level, lead time, review period, horizon) |

## Dataset

| Method | Path | Purpose |
|---|---|---|
| POST | `/dataset/upload` | Multipart upload of `Online Retail.xlsx`. Checks type, size, Excel signature and the 8 required columns |
| POST | `/dataset/validate` | Re-validate the stored file |
| GET | `/dataset/status` | File info and the availability of profile, cleaned data and model |
| GET | `/dataset/preview?section=head\|tail\|sample` | Five raw rows |
| GET | `/dataset/summary` | Stage 1 overview: dimensions, types, missing values, duplicates, unique counts |
| GET | `/dataset/preprocessing-report` | Stage 3 row accounting, transaction types, revenue definitions, outliers |

## Analytics and products

| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard` | KPIs, monthly/weekly trends, top products, model summary, inventory risk, ABC summary |
| GET | `/analytics/kpis` | Headline KPIs |
| GET | `/analytics/sales?freq=D\|W\|M` | Revenue, units, orders and customers per period |
| GET | `/analytics/top-products?by=quantity\|revenue&n=10` | Best sellers |
| GET | `/analytics/slow-moving?n=10` | Least-selling products |
| GET | `/analytics/countries?n=15` | Country-wise revenue |
| GET | `/analytics/time-patterns` | Day-of-week and hourly patterns |
| GET | `/analytics/customers` | Customer purchasing patterns |
| GET | `/analytics/variability?limit=50&min_sale_days=20` | Demand variability (CV) |
| GET | `/analytics/abc` | ABC classes and Pareto curve |
| GET | `/analytics/eda` | EDA chart interpretations |
| GET | `/products?search=&abc_class=&forecastable=&sort=&limit=&offset=` | Product list |
| GET | `/products/forecastable` | Products the model can forecast |
| GET | `/products/{stock_code}` | Product details, monthly and daily history, top countries |

## Forecasting and models

| Method | Path | Purpose |
|---|---|---|
| POST | `/forecast` | Body `{ "stock_code": "85123A", "horizon_days": 7\|14\|30 }`. Recursive forecast, saved to history |
| GET | `/forecast/history?stock_code=&limit=` | Saved forecast runs |
| GET | `/forecast/history/{record_id}` | One saved forecast |
| GET | `/models/performance` | All metrics, baselines, recursive backtests, residuals, errors by weekday and product |
| GET | `/models/feature-importance` | Permutation importance, feature families and business explanation |

## Inventory

| Method | Path | Purpose |
|---|---|---|
| POST | `/inventory/calculate` | What-if calculation (not saved) |
| POST | `/inventory/recommendations` | Calculate **and save** (201) |
| GET | `/inventory/recommendations?stock_code=&limit=` | Saved recommendations |
| GET | `/inventory/inputs` | Last saved inputs per product |
| GET | `/inventory/risk-summary` | Status distribution and alerts (latest saved recommendation per product) |

Example inventory request body:

```json
{ "stock_code": "85123A", "current_stock": 300, "lead_time_days": 10, "service_level": 0.95,
  "review_period_days": 7, "min_order_qty": 100, "pack_size": 12, "max_capacity": 2000 }
```

## Reports

| Method | Path | Purpose |
|---|---|---|
| POST | `/reports` | Body `{ "report_type": "sales\|forecast\|inventory", "format": "csv\|pdf" }` (201) |
| GET | `/reports` | Generated reports |
| GET | `/reports/{report_id}/download` | Download a report file |
