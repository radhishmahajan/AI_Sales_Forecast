import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TrendingUp } from "lucide-react";
import { api, toApiError } from "../services/api";
import { useApi } from "../hooks/useApi";
import { usePipeline } from "../hooks/usePipeline";
import { ProductPicker } from "../components/ProductPicker";
import { AsyncView, Callout, Card, CardBody, CardHeader, DataTable, ErrorState, KpiCard, LoadingState, PageHeader, Segmented } from "../components/ui";
import { fmtDate, fmtNum, fmtShortDate } from "../services/format";
import type { ApiError } from "../services/api";
import type { Forecast, Horizon } from "../types/api";

const weekday = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { weekday: "short" });

export default function ForecastPage() {
  const { dataVersion } = usePipeline();
  const products = useApi(api.forecastableProducts, [dataVersion]);
  const [params, setParams] = useSearchParams();
  const [code, setCode] = useState<string | null>(params.get("code"));
  const [horizon, setHorizon] = useState<Horizon>(14);
  const [result, setResult] = useState<Forecast | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  // Pick the first product once the list has loaded.
  useEffect(() => {
    if (!code && products.data?.length) setCode(products.data[0].StockCode);
  }, [products.data, code]);

  const generate = useCallback(async () => {
    if (!code) return;
    const id = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const f = await api.forecast(code, horizon);
      if (id !== latest.current) return; // a newer request replaced this one
      setResult(f);
      setParams({ code }, { replace: true });
    } catch (e) {
      if (id !== latest.current) return;
      setResult(null);
      setError(toApiError(e));
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }, [code, horizon, setParams]);

  // Forecast automatically whenever the product or the duration changes: no extra button press needed.
  useEffect(() => {
    void generate();
  }, [generate, dataVersion]);

  return (
    <>
      <PageHeader title="Forecast" description="Choose a product and how many days ahead you want to see. The forecast updates automatically." />
      <Card className="mb-6">
        <CardBody>
          <AsyncView state={products} empty={(p) => p.length === 0} emptyTitle="No products available" emptyDescription="Prepare the data first (python -m ml.pipeline)." loadingHeight="h-20">
            {(items) => (
              <div className="grid items-end gap-4 md:grid-cols-[1fr_auto]">
                <ProductPicker items={items} value={code} onChange={setCode} label="Product" />
                <div>
                  <p className="mb-1 text-xs font-medium text-slate-700 dark:text-slate-300">Days ahead</p>
                  <Segmented label="Days ahead" value={horizon} onChange={setHorizon} options={[{ value: 7, label: "7 days" }, { value: 14, label: "14 days" }, { value: 30, label: "30 days" }]} />
                </div>
              </div>
            )}
          </AsyncView>
        </CardBody>
      </Card>

      {loading && !result && <LoadingState label="Calculating forecast…" height="h-64" />}
      {error && <Card><ErrorState error={error} onRetry={() => void generate()} /></Card>}
      {result && (
        <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <ForecastView f={result} />
        </div>
      )}
    </>
  );
}

function ForecastView({ f }: { f: Forecast }) {
  const s = f.summary;
  const combined = useMemo(() => [
    ...f.history.map((h) => ({ date: h.date, actual: h.demand, forecast: null as number | null })),
    ...f.daily.map((d) => ({ date: d.date, actual: null as number | null, forecast: d.predicted_demand })),
  ], [f]);
  const last = s.historical_avg_daily_demand_last_30_days;
  const change = last && last > 0 ? ((s.average_daily_demand - last) / last) * 100 : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">{f.description ?? f.stock_code}</h2>
        <p className="text-xs text-slate-500">
          Product {f.stock_code} · forecast for {fmtDate(f.daily[0]?.date)} – {fmtDate(f.daily[f.daily.length - 1]?.date)}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label={`Expected units (${f.horizon_days} days)`} value={fmtNum(s.total_forecast_units, 0)} tone="violet" icon={<TrendingUp className="h-5 w-5" />} />
        <KpiCard label="Per open day" value={fmtNum(s.average_demand_per_open_day, 1)} hint={`${s.open_days_in_horizon} open days`} tone="violet" />
        <KpiCard label="Recent daily average" value={fmtNum(last, 1)} hint="last 30 days" tone="sky" />
        <KpiCard label="Compared with recent" value={change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(0)}%`} hint="avg per calendar day" tone={change !== null && change < 0 ? "amber" : "emerald"} />
      </div>

      <Card>
        <CardHeader title="Past sales and forecast" subtitle="Solid line: units sold in the last 90 days. Dashed line: forecast. The shop is closed on Saturdays." />
        <CardBody>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={combined} margin={{ left: 8, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={fmtShortDate} tick={{ fontSize: 11 }} minTickGap={24} />
                <YAxis tick={{ fontSize: 11 }} width={45} />
                <Tooltip labelFormatter={(l) => fmtDate(String(l))} formatter={(v) => (v == null ? "—" : fmtNum(Number(v), 1))} />
                <Legend />
                {f.daily[0] && <ReferenceLine x={f.daily[0].date} stroke="#94a3b8" strokeDasharray="4 4" />}
                <Line dataKey="actual" name="Units sold" stroke="#0ea5e9" dot={false} strokeWidth={1.5} connectNulls={false} />
                <Line dataKey="forecast" name="Forecast" stroke="#8b5cf6" strokeDasharray="6 3" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Day by day" />
          <DataTable maxHeight="max-h-80" rows={f.daily} rowKey={(d) => d.date} columns={[
            { key: "date", header: "Date", render: (d) => `${weekday(d.date)}, ${fmtDate(d.date)}` },
            { key: "predicted_demand", header: "Expected units", align: "right", render: (d) => (d.is_open ? fmtNum(d.predicted_demand, 0) : "Closed") },
          ]} />
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Week by week" />
            <DataTable rows={f.weekly} rowKey={(w) => w.week_start} columns={[
              { key: "week_start", header: "Week of", render: (w) => fmtDate(w.week_start) },
              { key: "predicted_units", header: "Units", align: "right", render: (w) => fmtNum(w.predicted_units, 0) },
            ]} />
          </Card>
          {s.days_since_last_sale !== null && s.days_since_last_sale > 28 && (
            <Callout tone="warning">This product has not sold for {s.days_since_last_sale} days, so it may be discontinued.</Callout>
          )}
          <Callout tone="info">Forecasts further ahead are less certain than the next few days.</Callout>
        </div>
      </div>
    </div>
  );
}
