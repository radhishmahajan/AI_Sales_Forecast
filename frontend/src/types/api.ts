// TypeScript mirrors of the FastAPI responses. Every chart and KPI is typed against these.

export type InventoryStatus = "Critical Stock" | "Low Stock" | "Healthy Stock" | "Overstocked";
export type Horizon = 7 | 14 | 30;

export interface ApiErrorBody {
  code: string;
  message: string;
}

export interface Kpis {
  total_revenue: number;
  total_quantity: number;
  total_transactions: number;
  total_invoice_lines: number;
  total_products: number;
  total_customers: number;
  total_countries: number;
  average_order_value: number;
  average_lines_per_order: number;
  trading_days: number;
  average_daily_revenue: number;
  first_date: string;
  last_date: string;
}

export interface TimePoint {
  period: string;
  revenue: number;
  quantity: number;
  transactions: number;
  customers: number;
  is_partial: boolean;
}

export interface ProductPerf {
  StockCode: string;
  Description: string;
  quantity: number;
  revenue: number;
  transactions: number;
  sale_days: number;
  customers: number;
  first_sale: string;
  last_sale: string;
  revenue_share_pct: number;
}

export interface Metrics {
  n: number;
  mae: number | null;
  rmse: number | null;
  wape_pct: number | null;
  mape_pct: number | null;
  mape_coverage_pct: number;
  r2: number | null;
  bias: number | null;
}

export interface ComparisonRow extends Metrics {
  model: string;
  type: "baseline" | "ml";
  split: "validation" | "test";
}

export interface BaselineComparison {
  best_model: string;
  best_baseline: string;
  test_mae_model: number;
  test_mae_baseline: number;
  mae_improvement_pct: number | null;
  test_wape_model: number;
  test_wape_baseline: number;
  beats_baseline: boolean;
}

export interface ModelSummary {
  best_model: string;
  trained_at: string;
  metrics_test: ComparisonRow;
  baseline_comparison: BaselineComparison;
  products_modelled: number;
  data_end_date: string;
}

export interface Alert {
  stock_code?: string;
  description?: string | null;
  level: "critical" | "warning" | "info";
  message: string;
  created_at?: string;
}

export interface RiskProduct {
  stock_code: string;
  description: string | null;
  status: InventoryStatus;
  inputs: InventoryRequest & { source: string };
  reorder_point: number;
  safety_stock: number;
  target_stock: number;
  suggested_order_quantity: number;
  days_of_cover: number | null;
  created_at: string;
  record_id: string;
}

export interface RiskSummary {
  assessed_products: number;
  status_counts: Record<InventoryStatus, number>;
  products: RiskProduct[];
  alerts: Alert[];
  note: string;
  overstock_rule: string;
}

export interface AbcClassSummary {
  class: "A" | "B" | "C";
  products: number;
  product_share_pct: number;
  revenue: number;
  revenue_share_pct: number;
}

export interface Dashboard {
  kpis: Kpis;
  monthly: TimePoint[];
  weekly: TimePoint[];
  top_products: ProductPerf[];
  model: ModelSummary | null;
  inventory_risk: RiskSummary;
  abc_summary: AbcClassSummary[];
  source: string;
}

export interface PipelineStep {
  name: string;
  label: string;
  state: "pending" | "running" | "completed" | "failed";
  seconds?: number | null;
}

export interface PipelineStatus {
  state: "never_run" | "running" | "completed" | "failed" | "interrupted";
  run_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  current_step?: string | null;
  error?: string | null;
  steps: PipelineStep[];
  log: string[];
  result?: { best_model: string; test_mae: number; test_wape_pct: number } | null;
}

export interface DatasetValidation {
  valid: boolean;
  file_name: string;
  file_size_mb: number;
  columns_found: string[];
  missing_columns: string[];
  warnings: string[];
  message: string;
}

export interface DatasetStatus {
  dataset_present: boolean;
  file_name: string | null;
  file_size_mb: number | null;
  uploaded_at: string | null;
  overview_available: boolean;
  preprocessing_available: boolean;
  model_available: boolean;
  pipeline: PipelineStatus;
}

export type Row = Record<string, string | number | boolean | null>;

export interface DatasetOverview {
  generated_at: string;
  file_info: { file_name: string; file_size_mb: number; sha256: string };
  dimensions: { rows: number; columns: number };
  columns: { name: string; dtype: string; expected_dtype: string; description: string; non_null: number; missing: number; missing_pct: number; unique: number }[];
  head: Row[];
  tail: Row[];
  sample: Row[];
  missing_values: { per_column: Record<string, number>; per_column_pct: Record<string, number>; rows_with_any_missing: number; total_missing_cells: number };
  duplicates: { exact_duplicate_rows: number; exact_duplicate_pct: number; rows_involved_in_duplication: number; duplicate_groups: number };
  unique_counts: Record<string, number>;
  quality_observations: Record<string, number | string | Record<string, number>>;
  date_range: { min: string; max: string; span_days: number; distinct_transaction_days: number; months_covered: string[] };
  numeric_summary: Record<string, Record<string, number | null>>;
  uci_documented_check: { rows_match: boolean; columns_match: boolean; period_match: boolean; documented: Record<string, string | number>; observed: Record<string, string | number> };
  purposes: Record<string, string>;
}

export interface PreprocessingReport {
  generated_at: string;
  forecast_target_policy: string;
  counts: Record<string, number | Record<string, number>>;
  transaction_types: Record<string, { rows: number; revenue: number; meaning: string }>;
  revenue: Record<string, number | string>;
  outliers: { rule: string; flagged_lines: number; largest_flagged_lines: Row[]; largest_reversed_sales: Row[] };
  steps: string[];
}

export interface Country {
  Country: string;
  revenue: number;
  quantity: number;
  transactions: number;
  customers: number;
  revenue_share_pct: number;
  average_order_value: number;
}

export interface TimePatterns {
  day_of_week: { day_of_week: string; revenue: number; quantity: number; transactions: number; trading_days: number; avg_revenue_per_trading_day: number }[];
  hourly: { hour: number; transactions: number; revenue: number; quantity: number }[];
}

export interface VariabilityRow {
  StockCode: string;
  Description: string;
  mean_daily_demand: number;
  std_daily_demand: number;
  cv: number;
  sale_days: number;
  window_days: number;
  sale_day_ratio: number;
  variability_class: string;
}

export interface Variability {
  summary: Record<string, number>;
  products: VariabilityRow[];
  scatter: { StockCode: string; Description: string; mean_daily_demand: number; cv: number }[];
  explanation: string;
}

export interface CustomerSummary {
  identified_customers: number;
  revenue_share_identified_pct: number;
  orders_per_customer: { mean: number; median: number; max: number };
  one_time_customers_pct: number;
  repeat_customers_pct: number;
  top_customers: { CustomerID: number; revenue: number; orders: number; country: string }[];
}

export interface EdaChart {
  title: string;
  file: string;
  interpretation: string;
}

export interface EdaReport {
  generated_at: string;
  data_used: string;
  charts: EdaChart[];
  seasonality_note: string;
}

export interface ProductListItem {
  StockCode: string;
  Description: string;
  quantity: number;
  revenue: number;
  revenue_share_pct: number;
  sale_days: number;
  abc_class: "A" | "B" | "C";
  cv: number | null;
  variability_class: string | null;
  is_forecastable: boolean;
  last_sale: string;
  last_unit_price: number;
}

export interface ProductList {
  total: number;
  offset: number;
  limit: number;
  items: ProductListItem[];
}

export interface ProductDetail {
  product: ProductListItem & {
    transactions: number;
    customers: number;
    first_sale: string;
    cumulative_share: number;
    revenue_rank: number;
    mean_daily_demand: number | null;
    std_daily_demand: number | null;
    sale_day_ratio: number | null;
  };
  monthly: { month: string; quantity: number; revenue: number }[];
  daily: { date: string; quantity: number; revenue: number }[];
  top_countries: { Country: string; Revenue: number }[];
  customers: number;
  orders: number;
}

export interface ForecastableProduct {
  StockCode: string;
  Description: string;
  abc_class: string;
}

export interface ForecastDay {
  date: string;
  predicted_demand: number;
  is_open: boolean;
  source: string;
}

export interface Forecast {
  record_id: string;
  created_at: string;
  stock_code: string;
  description: string | null;
  horizon_days: Horizon;
  forecast_origin: string;
  model_name: string;
  daily: ForecastDay[];
  summary: {
    total_forecast_units: number;
    average_daily_demand: number;
    average_demand_per_open_day: number;
    open_days_in_horizon: number;
    historical_avg_daily_demand_last_30_days: number | null;
    historical_total_last_30_days: number;
    days_since_last_sale: number | null;
  };
  weekly: { week_start: string; predicted_units: number; days: number }[];
  history: { date: string; demand: number; is_open: boolean }[];
  backtest: { date: string; actual: number; predicted: number }[];
  warnings: string[];
  uncertainty: string;
}

export interface ForecastHistoryRow {
  record_id: string;
  created_at: string;
  stock_code: string;
  description: string;
  horizon_days: number;
  model_name: string;
  forecast_origin: string;
  total_forecast_units: number;
  average_daily_demand: number;
}

export interface BacktestRow extends Metrics {
  horizon_days: number;
  method: string;
  products: number;
}

export interface ModelPerformance {
  best_model: string;
  best_model_description: string;
  selection_rule: string;
  trained_at: string;
  hyperparameters: Record<string, string | number>;
  all_tuning: Record<string, { best_params: Record<string, string | number>; cv_mae: number | null }>;
  loss_function_experiment: { loss: string; validation_mae: number; validation_wape_pct: number; validation_bias: number; bias_pct_of_mean_demand: number }[];
  loss_function_note: string;
  split: { train: { start: string; end: string }; validation: { start: string; end: string }; test: { start: string; end: string }; rows: Record<string, number> };
  metrics_validation: ComparisonRow;
  metrics_test: ComparisonRow;
  baseline_comparison: BaselineComparison;
  comparison: ComparisonRow[];
  model_descriptions: Record<string, string>;
  metric_explanations: Record<string, string>;
  recursive_backtest_test: BacktestRow[];
  recursive_backtest_test_origin: string;
  recursive_backtest_validation: BacktestRow[];
  recursive_backtest_validation_origin: string;
  error_by_weekday: { day_of_week: string; mae: number; wape_pct: number; rows: number }[];
  error_by_product_top20: { StockCode: string; mae: number; wape_pct: number; total_abs_error: number; total_actual: number }[];
  residuals: { mean: number; median: number; histogram: { bin_start: number; bin_end: number; count: number }[] };
  products_modelled: number;
  clip_rule: string;
  price_policy: string;
  uncertainty: string;
  final_fit: string;
  features: string[];
}

export interface FeatureImportance {
  model_name: string;
  method: string;
  features: { feature: string; importance_mae_increase: number; importance_std: number; family: string; importance_share_pct: number; direction_rank_corr: number }[];
  families: Record<string, number>;
  business_summary: string;
  top_feature_explanations: string[];
  feature_dictionary: Record<string, { family: string; description: string }>;
}

export interface InventoryRequest {
  stock_code: string;
  current_stock: number;
  lead_time_days: number;
  service_level: number;
  review_period_days: number;
  min_order_qty?: number | null;
  pack_size?: number | null;
  max_capacity?: number | null;
}

export interface InventoryResult {
  stock_code: string;
  description: string | null;
  status: InventoryStatus;
  status_reason: string;
  z_value: number;
  average_daily_demand: number;
  forecast_total: number;
  forecast_horizon_days: number;
  demand_std_daily: number | null;
  variability_window_days: number;
  variability_observed_days: number;
  lead_time_demand: number;
  safety_stock: number;
  reorder_point: number;
  target_stock: number;
  raw_order_quantity: number;
  suggested_order_quantity: number;
  order_adjustments: string[];
  capacity_limited: boolean;
  capacity_shortfall: number;
  days_of_cover: number | null;
  alerts: Alert[];
  confidence: "normal" | "low";
  warnings: string[];
  value_sources: Record<string, string>;
  policy: Record<string, string>;
  disclaimer: string;
  inputs: InventoryRequest & { source: string };
  forecast_origin: string;
  model_name: string;
  forecast_daily?: ForecastDay[];
  record_id?: string;
  created_at?: string;
}

export interface ReportInfo {
  report_id: string;
  report_type: "sales" | "forecast" | "inventory";
  format: "csv" | "pdf";
  file_name: string;
  created_at: string;
  size_bytes: number;
  rows: number | null;
  download_url: string;
}

export interface AppSettings {
  default_service_level: number;
  default_lead_time_days: number;
  default_review_period_days: number;
  default_forecast_horizon: Horizon;
  currency_symbol: string;
}

export interface Health {
  status: "ok";
  version: string;
  dataset_present: boolean;
  pipeline_state: string;
  model_available: boolean;
  storage_warnings: string[];
}
