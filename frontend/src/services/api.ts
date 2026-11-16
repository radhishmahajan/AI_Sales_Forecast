// Central API client: every request to the FastAPI backend goes through this file.
import axios, { AxiosError } from "axios";
import type {
  AppSettings, CustomerSummary, Country, Dashboard, DatasetOverview, DatasetStatus, DatasetValidation, EdaReport,
  FeatureImportance, Forecast, ForecastHistoryRow, ForecastableProduct, Health, Horizon, InventoryRequest,
  InventoryResult, Kpis, ModelPerformance, PipelineStatus, PreprocessingReport, ProductDetail, ProductList,
  ProductPerf, ReportInfo, RiskSummary, Row, TimePatterns, TimePoint, Variability,
} from "../types/api";

export const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api").replace(/\/$/, "");
export const SERVER_ROOT = API_BASE_URL.replace(/\/api$/, "");

export const http = axios.create({ baseURL: API_BASE_URL, timeout: 120_000 });

export class ApiError extends Error {
  code: string;
  status: number | null;
  constructor(message: string, code: string, status: number | null) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

/** Turn any axios/network error into a readable ApiError (shown in error states and toasts). */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  const ax = err as AxiosError<{ error?: { code: string; message: string }; detail?: { msg: string; loc: string[] }[] }>;
  if (ax?.isAxiosError) {
    if (!ax.response) {
      return new ApiError(`Cannot reach the backend at ${API_BASE_URL}. Is it running (uvicorn app.main:app)?`, "NETWORK_ERROR", null);
    }
    const data = ax.response.data;
    if (data?.error) return new ApiError(data.error.message, data.error.code, ax.response.status);
    if (Array.isArray(data?.detail)) {
      const msg = data.detail.map((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join("; ");
      return new ApiError(msg, "VALIDATION_ERROR", ax.response.status);
    }
    return new ApiError(ax.message, "HTTP_ERROR", ax.response.status);
  }
  return new ApiError(String((err as Error)?.message ?? err), "UNKNOWN", null);
}

async function get<T>(url: string, params?: object): Promise<T> {
  try {
    return (await http.get<T>(url, { params })).data;
  } catch (e) {
    throw toApiError(e);
  }
}

async function post<T>(url: string, body?: unknown, config?: object): Promise<T> {
  try {
    return (await http.post<T>(url, body, config)).data;
  } catch (e) {
    throw toApiError(e);
  }
}

async function put<T>(url: string, body?: unknown): Promise<T> {
  try {
    return (await http.put<T>(url, body)).data;
  } catch (e) {
    throw toApiError(e);
  }
}

export const api = {
  // system
  health: () => get<Health>("/health"),
  pipelineStatus: () => get<PipelineStatus>("/pipeline/status"),
  runPipeline: (fast = false) => post<{ started: boolean; message: string }>("/pipeline/run", { fast }),
  settings: () => get<AppSettings>("/settings"),
  saveSettings: (s: AppSettings) => put<AppSettings>("/settings", s),
  // dataset
  datasetStatus: () => get<DatasetStatus>("/dataset/status"),
  validateDataset: () => post<DatasetValidation>("/dataset/validate"),
  uploadDataset: (file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    form.append("file", file);
    return post<DatasetValidation>("/dataset/upload", form, {
      onUploadProgress: (e: { loaded: number; total?: number }) => onProgress?.(e.total ? Math.round((100 * e.loaded) / e.total) : 0),
    });
  },
  datasetSummary: () => get<DatasetOverview>("/dataset/summary"),
  datasetPreview: (section: "head" | "tail" | "sample") => get<{ section: string; rows: Row[]; columns: string[] }>("/dataset/preview", { section }),
  preprocessingReport: () => get<PreprocessingReport>("/dataset/preprocessing-report"),
  // analytics
  dashboard: () => get<Dashboard>("/dashboard"),
  kpis: () => get<Kpis>("/analytics/kpis"),
  sales: (freq: "D" | "W" | "M") => get<TimePoint[]>("/analytics/sales", { freq }),
  topProducts: (by: "quantity" | "revenue", n = 10) => get<ProductPerf[]>("/analytics/top-products", { by, n }),
  slowMoving: (n = 10) => get<ProductPerf[]>("/analytics/slow-moving", { n }),
  countries: (n = 15) => get<Country[]>("/analytics/countries", { n }),
  timePatterns: () => get<TimePatterns>("/analytics/time-patterns"),
  customers: () => get<CustomerSummary>("/analytics/customers"),
  variability: (limit = 50, minSaleDays = 20) => get<Variability>("/analytics/variability", { limit, min_sale_days: minSaleDays }),
  abc: () => get<{ thresholds: Record<string, number>; summary: Dashboard["abc_summary"]; curve: { rank: number; cumulative_share: number; abc_class: string }[] }>("/analytics/abc"),
  eda: () => get<EdaReport>("/analytics/eda"),
  // products
  products: (params: { search?: string; abc_class?: string; forecastable?: boolean; sort?: string; limit?: number; offset?: number }) =>
    get<ProductList>("/products", params),
  forecastableProducts: () => get<ForecastableProduct[]>("/products/forecastable"),
  product: (code: string) => get<ProductDetail>(`/products/${encodeURIComponent(code)}`),
  // forecasting
  forecast: (stock_code: string, horizon_days: Horizon) => post<Forecast>("/forecast", { stock_code, horizon_days }),
  forecastHistory: (stock_code?: string, limit = 50) => get<ForecastHistoryRow[]>("/forecast/history", { stock_code, limit }),
  forecastRecord: (id: string) => get<Forecast>(`/forecast/history/${id}`),
  // models
  modelPerformance: () => get<ModelPerformance>("/models/performance"),
  featureImportance: () => get<FeatureImportance>("/models/feature-importance"),
  // inventory
  calculateInventory: (req: InventoryRequest) => post<InventoryResult>("/inventory/calculate", req),
  saveInventory: (req: InventoryRequest) => post<InventoryResult>("/inventory/recommendations", req),
  inventoryRecommendations: (stock_code?: string, limit = 100) => get<InventoryResult[]>("/inventory/recommendations", { stock_code, limit }),
  inventoryInputs: () => get<Record<string, InventoryRequest & { saved_at: string }>>("/inventory/inputs"),
  riskSummary: () => get<RiskSummary>("/inventory/risk-summary"),
  // reports
  reports: () => get<ReportInfo[]>("/reports"),
  createReport: (report_type: ReportInfo["report_type"], format: ReportInfo["format"]) => post<ReportInfo>("/reports", { report_type, format }),
  downloadUrl: (r: ReportInfo) => `${SERVER_ROOT}${r.download_url}`,
};
