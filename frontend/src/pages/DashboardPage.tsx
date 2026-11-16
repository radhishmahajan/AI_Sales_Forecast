import { Link } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Package, TrendingUp, PoundSterling, Receipt, ShoppingCart, TriangleAlert, Users } from "lucide-react";
import { api } from "../services/api";
import { useApi } from "../hooks/useApi";
import { usePipeline } from "../hooks/usePipeline";
import { AsyncView, Badge, Card, CardBody, CardHeader, EmptyState, KpiCard, PageHeader, StatusBadge } from "../components/ui";
import { CHART_COLORS, STATUS_COLORS, fmtCompact, fmtCompactGBP, fmtDate, fmtGBP, fmtMonth, fmtNum, fmtPct, fmtShortDate } from "../services/format";
import type { Dashboard } from "../types/api";

export default function DashboardPage() {
  const { dataVersion } = usePipeline();
  const state = useApi(api.dashboard, [dataVersion]);
  return (
    <>
      <PageHeader title="Dashboard" description="Sales, top products and stock risk at a glance." />
      <AsyncView state={state} loadingHeight="h-96">{(d) => <DashboardContent d={d} />}</AsyncView>
    </>
  );
}

function DashboardContent({ d }: { d: Dashboard }) {
  const k = d.kpis;
  const monthly = d.monthly.map((m) => ({ ...m, label: fmtMonth(m.period) + (m.is_partial ? "*" : "") }));
  const risk = d.inventory_risk;
  const riskData = Object.entries(risk.status_counts).map(([name, value]) => ({ name, value })).filter((x) => x.value > 0);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <KpiCard label="Total revenue" value={fmtCompactGBP(k.total_revenue)} hint={fmtGBP(k.total_revenue)} icon={<PoundSterling className="h-5 w-5" />} source="dataset-derived" />
        <KpiCard label="Units sold" value={fmtCompact(k.total_quantity)} hint={fmtNum(k.total_quantity)} icon={<ShoppingCart className="h-5 w-5" />} tone="sky" />
        <KpiCard label="Transactions" value={fmtNum(k.total_transactions)} hint="invoices (orders)" icon={<Receipt className="h-5 w-5" />} tone="emerald" />
        <KpiCard label="Products" value={fmtNum(k.total_products)} hint={`${fmtNum(k.total_customers)} customers`} icon={<Package className="h-5 w-5" />} tone="violet" />
        <KpiCard label="Avg order value" value={fmtGBP(k.average_order_value, 2)} hint={`${k.average_lines_per_order} lines / order`} icon={<Users className="h-5 w-5" />} tone="amber" />
      </div>
      <p className="-mt-3 text-xs text-slate-500">
        Period {fmtDate(k.first_date)} – {fmtDate(k.last_date)} · {k.trading_days} trading days · revenue = gross fulfilled sales (cancellations, returns, postage and fees excluded).
      </p>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Revenue trend" subtitle="Monthly revenue (* = partial month)" source="dataset-derived" />
          <CardBody>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={monthly} margin={{ left: 8, right: 8 }}>
                  <defs>
                    <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#4f46e5" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={fmtCompactGBP} tick={{ fontSize: 11 }} width={60} />
                  <Tooltip formatter={(v) => [fmtGBP(Number(v)), "Revenue"]} />
                  <Area type="monotone" dataKey="revenue" stroke="#4f46e5" strokeWidth={2} fill="url(#rev)" name="Revenue" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Forecast your next order" subtitle="Pick a product and see expected demand for the coming days" />
          <CardBody>
            <div className="flex flex-col items-start gap-4">
              <div className="rounded-xl bg-violet-50 p-3 text-violet-600 dark:bg-violet-950"><TrendingUp className="h-6 w-6" /></div>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {d.model
                  ? `Demand forecasts are ready for ${d.model.products_modelled} popular products.`
                  : "Forecasts become available once the data has been prepared."}
              </p>
              <Link to="/forecast" className="inline-flex items-center rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700">Open forecast →</Link>
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Sales trend" subtitle="Units sold per week (first/last weeks partial)" source="dataset-derived" />
          <CardBody>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={d.weekly} margin={{ left: 8, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="period" tickFormatter={fmtShortDate} tick={{ fontSize: 11 }} minTickGap={24} />
                  <YAxis tickFormatter={fmtCompact} tick={{ fontSize: 11 }} width={50} />
                  <Tooltip labelFormatter={(l) => `Week ending ${fmtDate(String(l))}`} formatter={(v) => [fmtNum(Number(v)), "Units"]} />
                  <Line type="monotone" dataKey="quantity" stroke="#0ea5e9" strokeWidth={2} dot={false} name="Units" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Inventory risk" subtitle="Latest saved recommendation per product" source="user-entered" />
          <CardBody>
            {risk.assessed_products === 0 ? (
              <EmptyState title="No stock levels entered yet" description="Enter your current stock on the Inventory page to see stock risk here."
                action={<Link to="/inventory" className="text-sm font-medium text-indigo-600 hover:underline">Open Inventory →</Link>} />
            ) : (
              <div className="space-y-3">
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={riskData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={64} paddingAngle={2}>
                        {riskData.map((r) => <Cell key={r.name} fill={STATUS_COLORS[r.name]} />)}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(risk.status_counts).map(([s, n]) => (
                    <div key={s} className="flex items-center justify-between rounded-lg bg-slate-50 px-2 py-1.5 dark:bg-slate-800"><StatusBadge status={s} /><span className="font-semibold">{n}</span></div>
                  ))}
                </div>
                {risk.alerts.slice(0, 3).map((a, i) => (
                  <div key={i} className="flex gap-2 text-xs text-slate-600 dark:text-slate-300"><TriangleAlert className="h-4 w-4 shrink-0 text-amber-500" />{a.message}</div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Top-selling products" subtitle="By units sold" source="dataset-derived" />
          <CardBody>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.top_products} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={fmtCompact} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="Description" width={220} tick={{ fontSize: 10 }} tickFormatter={(s: string) => (s.length > 34 ? s.slice(0, 33) + "…" : s)} />
                  <Tooltip formatter={(v) => [fmtNum(Number(v)), "Units"]} />
                  <Bar dataKey="quantity" fill="#10b981" radius={[0, 4, 4, 0]} name="Units" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="ABC analysis" subtitle="Share of products vs share of revenue" source="dataset-derived" />
          <CardBody className="space-y-3">
            {d.abc_summary.map((c, i) => (
              <div key={c.class}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="font-medium"><Badge tone={c.class === "A" ? "green" : c.class === "B" ? "amber" : "slate"}>Class {c.class}</Badge> {fmtNum(c.products)} products ({fmtPct(c.product_share_pct)})</span>
                  <span className="font-semibold">{fmtPct(c.revenue_share_pct)} of revenue</span>
                </div>
                <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-2 rounded-full" style={{ width: `${c.revenue_share_pct}%`, background: CHART_COLORS[i] }} /></div>
              </div>
            ))}
            <p className="pt-2 text-xs text-slate-500">A = first 80% of cumulative revenue, B = next 15%, C = last 5%.</p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
