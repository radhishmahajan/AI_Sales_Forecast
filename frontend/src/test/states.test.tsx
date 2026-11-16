// Frontend state tests: loading, empty, error and success. API calls are mocked HERE ONLY (tests);
// the delivered application always talks to the real FastAPI backend.
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AsyncView, ErrorState } from "../components/ui";
import { ToastProvider } from "../components/Toast";
import { ApiError, toApiError } from "../services/api";

const mocks = vi.hoisted(() => ({ reports: vi.fn(), dashboard: vi.fn(), pipelineStatus: vi.fn() }));
vi.mock("../services/api", async (orig) => {
  const actual = await orig<typeof import("../services/api")>();
  return { ...actual, api: { ...actual.api, ...mocks } };
});

import ReportsPage from "../pages/ReportsPage";
import DashboardPage from "../pages/DashboardPage";

const wrap = (ui: React.ReactNode) => render(<MemoryRouter><ToastProvider>{ui}</ToastProvider></MemoryRouter>);

describe("AsyncView", () => {
  const base = { reload: () => {} };
  it("shows loading", () => {
    render(<AsyncView state={{ ...base, data: null, error: null, loading: true }}>{() => <p>data</p>}</AsyncView>);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });
  it("shows empty state", () => {
    render(<AsyncView state={{ ...base, data: [] as number[], error: null, loading: false }} empty={(d) => d.length === 0} emptyTitle="Nothing here">{() => <p>data</p>}</AsyncView>);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
  it("shows error state with retry", () => {
    render(<AsyncView state={{ ...base, data: null, error: new ApiError("Boom", "INTERNAL_ERROR", 500), loading: false }}>{() => <p>data</p>}</AsyncView>);
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
  it("shows success content", () => {
    render(<AsyncView state={{ ...base, data: [1, 2], error: null, loading: false }}>{(d) => <p>{d.length} items</p>}</AsyncView>);
    expect(screen.getByText("2 items")).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("tells the user how to set up when the pipeline has not run", () => {
    render(<MemoryRouter><ErrorState error={new ApiError("Run the pipeline first.", "PIPELINE_REQUIRED", 409)} /></MemoryRouter>);
    expect(screen.getByText("Setup needed")).toBeInTheDocument();
    expect(screen.getByText(/python -m ml.pipeline/)).toBeInTheDocument();
  });
});

describe("toApiError", () => {
  it("maps backend error bodies, validation errors and network errors", () => {
    const http = (status: number, data: unknown) => ({ isAxiosError: true, message: "x", response: { status, data } });
    expect(toApiError(http(404, { error: { code: "NOT_FOUND", message: "Missing" } }))).toMatchObject({ code: "NOT_FOUND", message: "Missing", status: 404 });
    expect(toApiError(http(422, { detail: [{ loc: ["body", "horizon_days"], msg: "Input should be 7, 14 or 30" }] })).message).toContain("horizon_days");
    expect(toApiError({ isAxiosError: true, message: "Network Error" }).code).toBe("NETWORK_ERROR");
  });
});

describe("ReportsPage", () => {
  beforeEach(() => vi.clearAllMocks());
  it("renders the empty state when no reports exist", async () => {
    mocks.reports.mockResolvedValue([]);
    wrap(<ReportsPage />);
    expect(await screen.findByText("No reports yet")).toBeInTheDocument();
  });
  it("renders generated reports (success)", async () => {
    mocks.reports.mockResolvedValue([{ report_id: "r1", report_type: "sales", format: "pdf", file_name: "sales_report_x.pdf", created_at: "2026-01-01T10:00:00Z", size_bytes: 2048, rows: null, download_url: "/api/reports/r1/download" }]);
    wrap(<ReportsPage />);
    expect(await screen.findByText("sales_report_x.pdf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute("href", expect.stringContaining("/api/reports/r1/download"));
  });
  it("renders the error state when the backend is unreachable", async () => {
    mocks.reports.mockRejectedValue(new ApiError("Cannot reach the backend", "NETWORK_ERROR", null));
    wrap(<ReportsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the backend");
  });
});

describe("DashboardPage", () => {
  it("shows a setup prompt before the pipeline has run", async () => {
    mocks.dashboard.mockRejectedValue(new ApiError("Data not available yet.", "PIPELINE_REQUIRED", 409));
    wrap(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("No processed data yet")).toBeInTheDocument());
  });
});
