// Number/date formatting helpers used across the dashboard.
export const fmtNum = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const fmtGBP = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `£${fmtNum(v, digits)}`;

export const fmtCompactGBP = (v: number) =>
  Math.abs(v) >= 1e6 ? `£${(v / 1e6).toFixed(2)}M` : Math.abs(v) >= 1e3 ? `£${(v / 1e3).toFixed(1)}k` : `£${v.toFixed(0)}`;

export const fmtCompact = (v: number) =>
  Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(1)}k` : `${Math.round(v)}`;

export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v.toFixed(digits)}%`;

export const fmtDate = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export const fmtShortDate = (v: string) => new Date(v).toLocaleDateString("en-GB", { day: "2-digit", month: "short" });

export const fmtMonth = (v: string) => new Date(v).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });

export const fmtDateTime = (v: string | null | undefined) =>
  v ? new Date(/([zZ]|[+-]\d\d:\d\d)$/.test(v) ? v : `${v}Z`).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

export const prettyModel = (m: string) =>
  ({
    linear_regression: "Linear Regression",
    random_forest: "Random Forest",
    hist_gradient_boosting: "HistGradientBoosting",
    xgboost: "XGBoost",
    baseline_previous_day: "Baseline: previous day",
    baseline_same_day_last_week: "Baseline: same day last week",
    baseline_moving_average_7: "Baseline: 7-day moving avg",
    "model (recursive)": "Model (recursive)",
    baseline_repeat_last_week: "Baseline: repeat last week",
  })[m] ?? m;

export const CHART_COLORS = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#ec4899"];
export const STATUS_COLORS: Record<string, string> = {
  "Critical Stock": "#ef4444",
  "Low Stock": "#f59e0b",
  "Healthy Stock": "#10b981",
  Overstocked: "#6366f1",
};
