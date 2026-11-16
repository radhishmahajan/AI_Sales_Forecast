"""
Central configuration for the ML pipeline.

Every path in the project is built from PROJECT_ROOT, so the code works the same
on Windows, Linux, macOS and Google Colab, no matter which folder you run it from.

Why one config file?
    If a folder name or a constant (for example the random seed) changes, we change it
    in ONE place instead of hunting through every script.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
# ml/config.py -> parent is ml/ -> parent of that is the project root.
PROJECT_ROOT: Path = Path(
    os.environ.get("SFIO_PROJECT_ROOT", Path(__file__).resolve().parent.parent)
).resolve()

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"            # Online Retail.xlsx lives here
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"  # cleaned CSV / Parquet outputs
REPORTS_DIR: Path = DATA_DIR / "reports"          # JSON/Markdown reports + charts
FIGURES_DIR: Path = REPORTS_DIR / "figures"       # saved Matplotlib/Seaborn charts

ARTIFACTS_DIR: Path = PROJECT_ROOT / "artifacts"  # trained model + metadata
STORAGE_DIR: Path = PROJECT_ROOT / "storage"      # application runtime records

# ---------------------------------------------------------------------------
# Dataset definition (UCI Online Retail, dataset id 352)
# ---------------------------------------------------------------------------
DATASET_FILENAME: str = "Online Retail.xlsx"
DEFAULT_DATASET_PATH: Path = RAW_DATA_DIR / DATASET_FILENAME
DATASET_SOURCE_URL: str = "https://archive.ics.uci.edu/dataset/352/online+retail"

# The eight original columns, in their original order.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
)

# What each column SHOULD become after type coercion (see data_loader.coerce_types).
# "string"          -> pandas nullable string
# "Int64"           -> pandas nullable integer (allows missing values)
# "float64"         -> decimal number
# "datetime64[ns]"  -> timestamp
EXPECTED_DTYPES: dict[str, str] = {
    "InvoiceNo": "string",
    "StockCode": "string",
    "Description": "string",
    "Quantity": "Int64",
    "InvoiceDate": "datetime64[ns]",
    "UnitPrice": "float64",
    "CustomerID": "Int64",
    "Country": "string",
}

# Plain-language meaning of each original column (used in reports and the API).
COLUMN_DESCRIPTIONS: dict[str, str] = {
    "InvoiceNo": "Invoice number. A 6-digit number per transaction; a leading 'C' means the invoice was cancelled.",
    "StockCode": "Product (item) code that uniquely identifies a product.",
    "Description": "Product name / description text.",
    "Quantity": "Number of units of the product on that invoice line. Negative values indicate returns/cancellations.",
    "InvoiceDate": "Date and time when the invoice was generated.",
    "UnitPrice": "Price per unit in pounds sterling (GBP).",
    "CustomerID": "5-digit customer identifier. Missing for some (often guest) transactions.",
    "Country": "Country where the customer resides.",
}

# ---------------------------------------------------------------------------
# File-validation limits (security: never trust uploaded files blindly)
# ---------------------------------------------------------------------------
ALLOWED_DATASET_EXTENSIONS: frozenset[str] = frozenset({".xlsx"})
MAX_DATASET_SIZE_MB: int = int(os.environ.get("SFIO_MAX_DATASET_SIZE_MB", "60"))
# .xlsx files are ZIP containers, so they always start with these 4 bytes.
XLSX_MAGIC_BYTES: bytes = b"PK\x03\x04"

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 42

# Name of the fast Parquet cache created after the first (slow) Excel read.
RAW_CACHE_FILENAME: str = "online_retail_raw.parquet"
RAW_CACHE_META_FILENAME: str = "online_retail_raw.cache.json"


def ensure_directories() -> None:
    """Create every output directory used by the pipeline (safe to call many times)."""
    for directory in (
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        REPORTS_DIR,
        FIGURES_DIR,
        ARTIFACTS_DIR,
        STORAGE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Feature engineering & modelling (Stages 4-10)
# ---------------------------------------------------------------------------
# Number of products modelled: the products with the most days with sales. This keeps
# training feasible on a laptop and focuses on products with enough history to learn from.
MODEL_TOP_N_PRODUCTS: int = int(os.environ.get("SFIO_TOP_N_PRODUCTS", "500"))
MIN_HISTORY_DAYS: int = 28          # a row is used only after 28 days of product history (lag 28 exists)
LAG_DAYS: tuple[int, ...] = (1, 7, 14, 28)
ROLLING_MEAN_WINDOWS: tuple[int, ...] = (7, 14, 28)
TARGET_COLUMN: str = "NEXT_DAY_DEMAND"

TRAIN_FRACTION: float = 0.70        # earliest 70% of dates
VALIDATION_FRACTION: float = 0.15   # next 15%; the final 15% is the untouched test period
CV_FOLDS: int = 3                   # rolling-origin folds inside the training period
TUNING_ITERATIONS: dict[str, int] = {"random_forest": 6, "hist_gradient_boosting": 12, "xgboost": 12}
MAPE_MIN_ACTUAL: float = 5.0        # MAPE only on days with actual demand >= 5 units (see evaluate.py)
FORECAST_HORIZONS: tuple[int, ...] = (7, 14, 30)

# ---------------------------------------------------------------------------
# Inventory policy defaults (Stage: inventory optimisation)
# ---------------------------------------------------------------------------
DEFAULT_SERVICE_LEVEL: float = 0.95
DEFAULT_REVIEW_PERIOD_DAYS: int = 7
VARIABILITY_WINDOW_DAYS: int = 84   # last 12 weeks of history used for demand standard deviation
MIN_DAYS_FOR_VARIABILITY: int = 28  # fewer observed days -> "insufficient history" warning
OVERSTOCK_FACTOR: float = 1.5       # stock above 1.5 x target stock = overstocked
ABC_THRESHOLDS: tuple[float, float] = (0.80, 0.95)  # cumulative revenue share limits for A and B
