import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChevronLeft, ChevronRight, Search, TrendingUp } from "lucide-react";
import { api, toApiError, type ApiError } from "../services/api";
import { useApi } from "../hooks/useApi";
import { usePipeline } from "../hooks/usePipeline";
import { AbcBadge, AsyncView, Badge, Button, Card, CardBody, CardHeader, ErrorState, Input, KpiCard, PageHeader, Select, cx } from "../components/ui";
import { fmtCompact, fmtCompactGBP, fmtDate, fmtGBP, fmtMonth, fmtNum, fmtPct, fmtShortDate } from "../services/format";
import type { Forecast, ProductDetail } from "../types/api";

const PAGE = 25;

export default function ProductInsightsPage() {
  const { dataVersion } = usePipeline();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [abc, setAbc] = useState("");
  const [onlyForecastable, setOnlyForecastable] = useState(false);
  const [sort, setSort] = useState("revenue");
  const [offset, setOffset] = useState(0);
  const selected = params.get("code");

  useEffect(() => {
    const id = window.setTimeout(() => { setDebounced(search); setOffset(0); }, 300);
    return () => window.clearTimeout(id);
  }, [search]);

  const list = useApi(() => api.products({ search: debounced || undefined, abc_class: abc || undefined, forecastable: onlyForecastable ? true : undefined, sort, limit: PAGE, offset }),
    [debounced, abc, onlyForecastable, sort, offset, dataVersion]);

  useEffect(() => {
    if (!selected && list.data?.items.length) setParams({ code: list.data.items[0].StockCode }, { replace: true });
  }, [list.data, selected, setParams]);

  return (
    <>
      <PageHeader title="Products" description="Search any product to see its sales history, revenue share and forecast." />
      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        <Card className="self-start">
          <CardBody className="space-y-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input aria-label="Search products" className="pl-9" placeholder="Search code or name…" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Select aria-label="ABC class" value={abc} onChange={(e) => { setAbc(e.target.value); setOffset(0); }}>
                <option value="">All classes</option><option value="A">Class A</option><option value="B">Class B</option><option value="C">Class C</option>
              </Select>
              <Select aria-label="Sort by" value={sort} onChange={(e) => { setSort(e.target.value); setOffset(0); }}>
                <option value="revenue">Sort: revenue</option><option value="quantity">Sort: units</option><option value="variability">Sort: variability</option><option value="code">Sort: code</option>
              </Select>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
              <input type="checkbox" checked={onlyForecastable} onChange={(e) => { setOnlyForecastable(e.target.checked); setOffset(0); }} /> Only forecastable (modelled) products
            </label>
          </CardBody>
          <AsyncView state={list} empty={(l) => l.total === 0} emptyTitle="No products match" loadingHeight="h-64">
            {(l) => (
              <>
                <ul className="scrollbar-thin max-h-[520px] divide-y divide-slate-100 overflow-auto dark:divide-slate-800">
                  {l.items.map((p) => (
                    <li key={p.StockCode}>
                      <button onClick={() => setParams({ code: p.StockCode })} className={cx("flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800/60", selected === p.StockCode && "bg-indigo-50 dark:bg-indigo-950/40")}>
                        <span className="w-14 shrink-0 font-mono text-xs text-slate-500">{p.StockCode}</span>
                        <span className="min-w-0 flex-1"><span className="block truncate">{p.Description}</span><span className="text-xs text-slate-500">{fmtGBP(p.revenue)} · {fmtNum(p.quantity)} units</span></span>
                        <AbcBadge cls={p.abc_class} />
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-xs text-slate-500 dark:border-slate-800">
                  <span>{offset + 1}–{Math.min(offset + PAGE, l.total)} of {fmtNum(l.total)}</span>
                  <div className="flex gap-1">
                    <Button variant="ghost" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}><ChevronLeft className="h-4 w-4" /></Button>
                    <Button variant="ghost" aria-label="Next page" disabled={offset + PAGE >= l.total} onClick={() => setOffset(offset + PAGE)}><ChevronRight className="h-4 w-4" /></Button>
                  </div>
                </div>
              </>
            )}
          </AsyncView>
        </Card>
        <div>{selected ? <Detail code={selected} version={dataVersion} /> : null}</div>
      </div>
    </>
  );
}

function Detail({ code, version }: { code: string; version: number }) {
  const d = useApi(() => api.product(code), [code, version]);
  return <AsyncView state={d} loadingHeight="h-96">{(p) => <DetailView p={p} />}</AsyncView>;
}

function DetailView({ p }: { p: ProductDetail }) {
  const pr = p.product;
  const [fc, setFc] = useState<Forecast | null>(null);
  const [fcErr, setFcErr] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { setFc(null); setFcErr(null); }, [pr.StockCode]);

  async function forecast() {
    setLoading(true);
    setFcErr(null);
    try { setFc(await api.forecast(pr.StockCode, 14)); } catch (e) { setFcErr(toApiError(e)); } finally { setLoading(false); }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardBody className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="font-mono text-xs text-slate-500">{pr.StockCode}</p>
            <h2 className="text-lg font-semibold">{pr.Description}</h2>
            <p className="text-xs text-slate-500">Sold {fmtDate(pr.first_sale)} – {fmtDate(pr.last_sale)} · {fmtNum(p.orders)} orders · {fmtNum(p.customers)} customers</p>
          </div>
          <AbcBadge cls={pr.abc_class} />
          {pr.variability_class && <Badge tone={pr.variability_class === "Erratic" ? "red" : pr.variability_class === "Moderate" ? "amber" : "green"}>{pr.variability_class} demand</Badge>}
          {pr.is_forecastable ? <Badge tone="indigo">Forecastable</Badge> : <Badge>Not modelled</Badge>}
        </CardBody>
      </Card>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Revenue" value={fmtCompactGBP(pr.revenue)} hint={`rank #${pr.revenue_rank}`} source="dataset-derived" />
        <KpiCard label="Revenue contribution" value={fmtPct(pr.revenue_share_pct, 3)} hint={`cumulative ${fmtPct(pr.cumulative_share * 100)}`} tone="emerald" />
        <KpiCard label="Units sold" value={fmtNum(pr.quantity)} hint={`${pr.sale_days} sale days`} tone="sky" />
        <KpiCard label="Demand variability (CV)" value={pr.cv == null ? "—" : fmtNum(pr.cv, 2)} hint={`mean ${fmtNum(pr.mean_daily_demand, 1)} ± ${fmtNum(pr.std_daily_demand, 1)} /day`} tone="amber" />
      </div>
      <Card>
        <CardHeader title="Monthly sales" source="dataset-derived" />
        <CardBody>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={p.monthly}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" tickFormatter={fmtMonth} tick={{ fontSize: 11 }} />
                <YAxis yAxisId="q" tickFormatter={fmtCompact} tick={{ fontSize: 11 }} width={45} />
                <YAxis yAxisId="r" orientation="right" tickFormatter={fmtCompactGBP} tick={{ fontSize: 11 }} width={55} />
                <Tooltip labelFormatter={(l) => fmtMonth(String(l))} formatter={(v, n) => (n === "Revenue" ? fmtGBP(Number(v)) : fmtNum(Number(v)))} />
                <Legend />
                <Bar yAxisId="q" dataKey="quantity" name="Units" fill="#a5b4fc" radius={[3, 3, 0, 0]} />
                <Line yAxisId="r" dataKey="revenue" name="Revenue" stroke="#4f46e5" strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardBody>
      </Card>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Historical daily sales" subtitle="Units on days with sales" source="dataset-derived" />
          <CardBody>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={p.daily}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={fmtShortDate} tick={{ fontSize: 11 }} minTickGap={30} />
                  <YAxis tick={{ fontSize: 11 }} width={45} />
                  <Tooltip labelFormatter={(l) => fmtDate(String(l))} formatter={(v) => fmtNum(Number(v))} />
                  <Line dataKey="quantity" name="Units" stroke="#0ea5e9" dot={false} strokeWidth={1.2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Top countries" />
          <CardBody className="space-y-2 text-sm">
            {p.top_countries.map((c) => <div key={c.Country} className="flex justify-between"><span>{c.Country}</span><span className="font-semibold tabular-nums">{fmtGBP(c.Revenue)}</span></div>)}
          </CardBody>
        </Card>
      </div>
      <Card>
        <CardHeader title="Forecasted demand" source="model-predicted" actions={pr.is_forecastable && (
          <>
            <Button variant="secondary" icon={<TrendingUp className="h-4 w-4" />} onClick={forecast} loading={loading}>14-day forecast</Button>
            <Link to={`/forecast?code=${encodeURIComponent(pr.StockCode)}`} className="text-sm font-medium text-indigo-600 hover:underline">Open in Forecasting →</Link>
          </>
        )} />
        <CardBody>
          {!pr.is_forecastable ? (
            <p className="text-sm text-slate-500">This product is outside the {""}modelled set (products with the longest sales history), so no ML forecast is available.</p>
          ) : fcErr ? <ErrorState error={fcErr} /> : !fc ? (
            <p className="text-sm text-slate-500">Click "14-day forecast" to predict the next two weeks (saved to forecast history).</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-4">
              <KpiCard label="Next 14 days" value={fmtNum(fc.summary.total_forecast_units, 0)} hint="units" tone="violet" />
              <KpiCard label="Avg / day" value={fmtNum(fc.summary.average_daily_demand, 1)} tone="violet" />
              <div className="h-40 md:col-span-2">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={fc.daily}>
                    <XAxis dataKey="date" tickFormatter={fmtShortDate} tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} width={35} />
                    <Tooltip labelFormatter={(l) => fmtDate(String(l))} formatter={(v) => fmtNum(Number(v), 1)} />
                    <Line dataKey="predicted_demand" name="Predicted" stroke="#8b5cf6" strokeDasharray="6 3" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
