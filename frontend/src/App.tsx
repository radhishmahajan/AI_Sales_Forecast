import { Suspense, lazy } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import { EmptyState, LoadingState } from "./components/ui";

// Each page is loaded on demand (smaller initial download).
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const SalesAnalyticsPage = lazy(() => import("./pages/SalesAnalyticsPage"));
const ForecastPage = lazy(() => import("./pages/ForecastPage"));
const InventoryPage = lazy(() => import("./pages/InventoryPage"));
const ProductInsightsPage = lazy(() => import("./pages/ProductInsightsPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));

const page = (el: React.ReactNode) => <Suspense fallback={<LoadingState height="h-96" />}>{el}</Suspense>;

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={page(<DashboardPage />)} />
        <Route path="analytics" element={page(<SalesAnalyticsPage />)} />
        <Route path="forecast" element={page(<ForecastPage />)} />
        <Route path="inventory" element={page(<InventoryPage />)} />
        <Route path="products" element={page(<ProductInsightsPage />)} />
        <Route path="reports" element={page(<ReportsPage />)} />
        {/* The Dataset and Model Performance pages were removed; old links go to the dashboard. */}
        <Route path="dataset" element={<Navigate to="/" replace />} />
        <Route path="models" element={<Navigate to="/" replace />} />
        <Route path="*" element={<EmptyState title="Page not found" action={<Link className="text-sm text-indigo-600" to="/">Back to dashboard</Link>} />} />
      </Route>
    </Routes>
  );
}
