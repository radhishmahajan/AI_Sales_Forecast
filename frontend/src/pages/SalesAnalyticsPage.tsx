import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Lightbulb } from "lucide-react";
import { api } from "../services/api";
import { useApi } from "../hooks/useApi";
import { usePipeline } from "../hooks/usePipeline";
import { AsyncView, Badge, Card, CardBody, CardHeader, DataTable, KpiCard, PageHeader, Segmented } from "../components/ui";
import { fmtCompact, fmtCompactGBP, fmtDate, fmtGBP, fmtMonth, fmtNum, fmtPct, fmtShortDate } from "../services/format";

type Freq = "D" | "W" | "M";

export default function SalesAnalyticsPage() {
  const { dataVersion: v } = usePipeline();
  const [freq, setFreq] = useState<Freq>("W");
  const [by, setBy] = useState<"quantity" | "revenue">("quantity");
  const sales = useApi(() => api.sales(freq), [freq, v]);
  const countries = useApi(() => api.countries(12), [v]);
  const top = useApi(() => api.topProducts(by, 10), [by, v]);
  const slow = useApi(() => api.slowMoving(10), [v]);
  const patterns = useApi(api.timePatterns, [v]);
  const variability = useApi(() => api.variability(15, 20), [v]);
  const customers = useApi(api.customers, [v]);
  const eda = useApi(api.eda, [v]);

  const tickFmt = freq === "M" ? fmtMonth : fmtShortDate;
  return (
    <>
      <PageHeader title="Sales" description="Trends, best sellers, countries, customers and busy times." />
      <div className="space-y-6">
        <Card>
          <CardHeader title="Revenue and units sold over time" source="dataset-derived"
            subtitle={freq === "D" ? "Trading days only (shop closed on Saturdays and holidays)" : freq === "W" ? "Weeks ending Sunday; first and last weeks are partial" : "Calendar months; Dec 2011 is partial (to 9 Dec)"}
            actions={<Segmented label="Granularity" value={freq} onChange={setFreq} options={[{ value: "D", label: "Daily" }, { value: "W", label: "Weekly" }, { value: "M", label: "Monthly" }]} />} />
          <CardBody>
            <AsyncView state={sales} loadingHeight="h-80">
              {(data) => (
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={data} margin={{ left: 8, right: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="period" tickFormatter={tickFmt} tick={{ fontSize: 11 }} minTickGap={20} />
                      <YAxis yAxisId="q" tickFormatter={fmtCompact} tick={{ fontSize: 11 }} width={50} label={{ value: "Units", angle: -90, position: "insideLeft", fontSize: 11 }} />
                      <YAxis yAxisId="r" orientation="right" tickFormatter={fmtCompactGBP} tick={{ fontSize: 11 }} width={60} />
                      <Tooltip labelFormatter={(l) => fmtDate(String(l))} formatter={(val, name) => (name === "Revenue" ? fmtGBP(Number(val)) : fmtNum(Number(val)))} />
                      <Legend />
                      <Bar yAxisId="q" dataKey="quantity" name="Units sold" fill="#a5b4fc" radius={[3, 3, 0, 0]} />
                      <Line yAxisId="r" dataKey="revenue" name="Revenue" stroke="#4f46e5" strokeWidth={2} dot={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}
            </AsyncView>
          </CardBody>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Best-selling products" source="dataset-derived" actions={
              <Segmented label="Rank by" value={by} onChange={setBy} options={[{ value: "quantity", label: "Units" }, { value: "revenue", label: "Revenue" }]} />} />
            <CardBody>
              <AsyncView state={top}>
                {(rows) => (
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                        <XAxis type="number" tickFormatter={by === "revenue" ? fmtCompactGBP : fmtCompact} tick={{ fontSize: 11 }} />
                        <YAxis type="category" dataKey="Description" width={200} tick={{ fontSize: 10 }} tickFormatter={(s: string) => (s.length > 30 ? s.slice(0, 29) + "…" : s)} />
                        <Tooltip formatter={(val) => [by === "revenue" ? fmtGBP(Number(val)) : fmtNum(Number(val)), by === "revenue" ? "Revenue" : "Units"]} />
                        <Bar dataKey={by} fill={by === "revenue" ? "#4f46e5" : "#10b981"} radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </AsyncView>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Country-wise revenue" subtitle="Top 12 countries — logarithmic scale so smaller markets stay visible" source="dataset-derived" />
            <CardBody>
              <AsyncView state={countries}>
                {(rows) => (
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                        <XAxis type="number" scale="log" domain={["auto", "auto"]} tickFormatter={fmtCompactGBP} tick={{ fontSize: 11 }} />
                        <YAxis type="category" dataKey="Country" width={110} tick={{ fontSize: 11 }} />
                        <Tooltip formatter={(val, _n, item) => [`${fmtGBP(Number(val))} (${fmtPct((item.payload as { revenue_share_pct: number }).revenue_share_pct)})`, "Revenue"]} />
                        <Bar dataKey="revenue" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </AsyncView>
            </CardBody>
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Day-of-week pattern" subtitle="Average revenue per trading day" source="dataset-derived" />
            <CardBody>
              <AsyncView state={patterns}>
                {(p) => (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={p.day_of_week}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="day_of_week" tick={{ fontSize: 11 }} tickFormatter={(d: string) => d.slice(0, 3)} />
                        <YAxis tickFormatter={fmtCompactGBP} tick={{ fontSize: 11 }} width={55} />
                        <Tooltip formatter={(val, _n, item) => [`${fmtGBP(Number(val))} (${(item.payload as { trading_days: number }).trading_days} trading days)`, "Avg revenue"]} />
                        <Bar dataKey="avg_revenue_per_trading_day" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </AsyncView>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Hourly transaction pattern" subtitle="Number of orders by hour of day" source="dataset-derived" />
            <CardBody>
              <AsyncView state={patterns}>
                {(p) => (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={p.hourly}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="hour" tick={{ fontSize: 11 }} tickFormatter={(h) => `${h}:00`} />
                        <YAxis tick={{ fontSize: 11 }} tickFormatter={fmtCompact} width={45} />
                        <Tooltip labelFormatter={(h) => `${h}:00 – ${h}:59`} formatter={(val) => [fmtNum(Number(val)), "Orders"]} />
                        <Bar dataKey="transactions" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </AsyncView>
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader title="Product demand variability" subtitle="Each dot is a product (≥ 20 sale days). CV = std ÷ mean of daily demand; above 1 = erratic." source="dataset-derived" />
          <CardBody>
            <AsyncView state={variability}>
              {(vd) => (
                <div className="grid gap-6 lg:grid-cols-3">
                  <div className="h-72 lg:col-span-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ left: 8, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" dataKey="mean_daily_demand" name="Mean daily units" scale="log" domain={[0.1, 300]} allowDataOverflow ticks={[0.1, 0.3, 1, 3, 10, 30, 100, 300]} tickFormatter={(t) => String(t)} tick={{ fontSize: 11 }} label={{ value: "Mean daily units (log)", position: "insideBottom", offset: -2, fontSize: 11 }} />
                        <YAxis type="number" dataKey="cv" name="CV" tick={{ fontSize: 11 }} width={40} />
                        <ZAxis range={[24, 24]} />
                        <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(val, name) => [Number(val).toFixed(2), String(name)]} labelFormatter={() => ""} />
                        <Scatter data={vd.scatter} fill="#4f46e5" fillOpacity={0.55} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-2">{Object.entries(vd.summary).map(([k, n]) => <Badge key={k} tone={k === "Erratic" ? "red" : k === "Moderate" ? "amber" : "green"}>{k}: {fmtNum(n)}</Badge>)}</div>
                    <p className="text-xs text-slate-500">{vd.explanation}</p>
                    <p className="text-xs font-semibold uppercase text-slate-500">Most erratic products</p>
                    <ul className="space-y-1 text-xs">{vd.products.slice(0, 8).map((p) => <li key={p.StockCode} className="flex justify-between gap-2"><span className="truncate">{p.Description}</span><span className="font-semibold tabular-nums">CV {p.cv.toFixed(1)}</span></li>)}</ul>
                  </div>
                </div>
              )}
            </AsyncView>
          </CardBody>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Slow-moving products" subtitle="Lowest total units sold" source="dataset-derived" />
            <AsyncView state={slow}>
              {(rows) => (
                <DataTable rows={rows} rowKey={(r) => r.StockCode} columns={[
                  { key: "StockCode", header: "Code" },
                  { key: "Description", header: "Product", render: (r) => <span className="block max-w-[220px] truncate">{r.Description}</span> },
                  { key: "quantity", header: "Units", align: "right", render: (r) => fmtNum(r.quantity) },
                  { key: "sale_days", header: "Sale days", align: "right" },
                  { key: "last_sale", header: "Last sale", render: (r) => fmtDate(r.last_sale) },
                ]} />
              )}
            </AsyncView>
          </Card>
          <Card>
            <CardHeader title="Customer purchasing patterns" subtitle="Identified customers only (CustomerID present)" source="dataset-derived" />
            <CardBody>
              <AsyncView state={customers}>
                {(c) => (
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-3">
                      <KpiCard label="Customers" value={fmtNum(c.identified_customers)} />
                      <KpiCard label="Repeat buyers" value={fmtPct(c.repeat_customers_pct, 0)} tone="emerald" />
                      <KpiCard label="Median orders" value={fmtNum(c.orders_per_customer.median)} tone="sky" />
                    </div>
                    <DataTable rows={c.top_customers.slice(0, 6)} rowKey={(r) => String(r.CustomerID)} columns={[
                      { key: "CustomerID", header: "Customer" }, { key: "country", header: "Country" },
                      { key: "orders", header: "Orders", align: "right" },
                      { key: "revenue", header: "Revenue", align: "right", render: (r) => fmtGBP(r.revenue) }]} />
                  </div>
                )}
              </AsyncView>
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader title="Business interpretation" subtitle="Generated from the data by the EDA stage (each statement is computed, not hand-written)" />
          <CardBody>
            <AsyncView state={eda}>
              {(r) => (
                <div className="grid gap-3 md:grid-cols-2">
                  {r.charts.map((c) => (
                    <div key={c.title} className="flex gap-3 rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                      <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                      <div><p className="text-sm font-semibold">{c.title}</p><p className="text-xs text-slate-600 dark:text-slate-400">{c.interpretation}</p></div>
                    </div>
                  ))}
                  <p className="text-xs text-slate-500 md:col-span-2">{r.seasonality_note}</p>
                </div>
              )}
            </AsyncView>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
