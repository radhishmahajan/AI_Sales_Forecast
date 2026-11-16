// Application shell: sidebar navigation, header with pipeline status, theme toggle.
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Boxes, ChartColumn, FileText, LayoutDashboard, LoaderCircle, Menu, Moon, Package, Sun, TrendingUp, X,
} from "lucide-react";
import { usePipeline } from "../hooks/usePipeline";
import { useTheme } from "../hooks/useTheme";
import { cx } from "../components/ui";

export const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/analytics", label: "Sales", icon: ChartColumn },
  { to: "/forecast", label: "Forecast", icon: TrendingUp },
  { to: "/inventory", label: "Inventory", icon: Boxes },
  { to: "/products", label: "Products", icon: Package },
  { to: "/reports", label: "Reports", icon: FileText },
];

function PipelinePill() {
  const { status, backendOnline } = usePipeline();
  if (!backendOnline) {
    return <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-100 px-2.5 py-1 text-xs font-medium text-rose-700 dark:bg-rose-950 dark:text-rose-300"><span className="h-1.5 w-1.5 rounded-full bg-rose-500" />Backend offline</span>;
  }
  if (!status) return null;
  if (status.state === "running") {
    return <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"><LoaderCircle className="h-3 w-3 animate-spin" />Preparing data…</span>;
  }
  if (status.state === "completed") {
    return <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />Ready</span>;
  }
  return <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300"><span className="h-1.5 w-1.5 rounded-full bg-amber-500" />Setup needed</span>;
}

export default function AppLayout() {
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const current = NAV.find((n) => (n.to === "/" ? location.pathname === "/" : location.pathname.startsWith(n.to)));

  const nav = (
    <nav className="flex flex-col gap-1 px-3">
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          onClick={() => setOpen(false)}
          className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
            isActive ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white")}
        >
          <Icon className="h-4 w-4" />
          {label}
        </NavLink>
      ))}
    </nav>
  );

  const brand = (
    <div className="flex items-center gap-2.5 px-6 py-5">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-md">
        <TrendingUp className="h-5 w-5" />
      </div>
      <div>
        <p className="text-sm font-bold text-slate-900 dark:text-white">ForecastIQ</p>
        <p className="text-[11px] text-slate-500">Sales &amp; Inventory</p>
      </div>
    </div>
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 lg:flex">
        {brand}
        {nav}
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white shadow-xl dark:bg-slate-900">
            <div className="flex items-center justify-between pr-3">{brand}<button aria-label="Close menu" onClick={() => setOpen(false)}><X className="h-5 w-5" /></button></div>
            {nav}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80 sm:px-6">
          <button aria-label="Open menu" className="lg:hidden" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button>
          <p className="truncate text-sm font-medium text-slate-500 dark:text-slate-400">{current?.label ?? ""}</p>
          <div className="ml-auto flex items-center gap-3">
            <PipelinePill />
            <button aria-label="Toggle dark mode" onClick={toggle} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
