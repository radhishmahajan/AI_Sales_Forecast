import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Calculator, LoaderCircle, Save, TriangleAlert } from "lucide-react";
import { api, toApiError, type ApiError } from "../services/api";
import { useApi } from "../hooks/useApi";
import { usePipeline } from "../hooks/usePipeline";
import { useToast } from "../components/Toast";
import { ProductPicker } from "../components/ProductPicker";
import { AsyncView, Button, Callout, Card, CardBody, CardHeader, DataTable, EmptyState, ErrorState, Field, Input, KpiCard, PageHeader, Select, StatusBadge } from "../components/ui";
import { STATUS_COLORS, fmtDateTime, fmtNum } from "../services/format";
import type { InventoryRequest, InventoryResult } from "../types/api";

interface FormState { current_stock: string; lead_time_days: string; service_level: string; review_period_days: string; min_order_qty: string; pack_size: string; max_capacity: string }

const blank: FormState = { current_stock: "", lead_time_days: "7", service_level: "0.95", review_period_days: "7", min_order_qty: "", pack_size: "", max_capacity: "" };

function validate(f: FormState): Record<string, string> {
  const e: Record<string, string> = {};
  const num = (s: string) => (s.trim() === "" ? NaN : Number(s));
  if (f.current_stock.trim() === "" || !(num(f.current_stock) >= 0)) e.current_stock = "Enter current stock (0 or more).";
  const lt = num(f.lead_time_days);
  if (!Number.isInteger(lt) || lt < 1 || lt > 365) e.lead_time_days = "Whole number of days, 1–365.";
  const sl = num(f.service_level);
  if (!(sl >= 0.5 && sl <= 0.999)) e.service_level = "Between 0.50 and 0.999.";
  const rp = num(f.review_period_days);
  if (!Number.isInteger(rp) || rp < 1 || rp > 90) e.review_period_days = "Whole number of days, 1–90.";
  if (f.min_order_qty && !(Number.isInteger(num(f.min_order_qty)) && num(f.min_order_qty) >= 0)) e.min_order_qty = "Whole number ≥ 0.";
  if (f.pack_size && !(Number.isInteger(num(f.pack_size)) && num(f.pack_size) >= 1)) e.pack_size = "Whole number ≥ 1.";
  if (f.max_capacity && !(Number.isInteger(num(f.max_capacity)) && num(f.max_capacity) > 0)) e.max_capacity = "Whole number > 0.";
  return e;
}

function toRequest(code: string, f: FormState): InventoryRequest {
  const opt = (s: string) => (s.trim() === "" ? null : Number(s));
  return { stock_code: code, current_stock: Number(f.current_stock), lead_time_days: Number(f.lead_time_days), service_level: Number(f.service_level),
    review_period_days: Number(f.review_period_days), min_order_qty: opt(f.min_order_qty), pack_size: opt(f.pack_size), max_capacity: opt(f.max_capacity) };
}

export default function InventoryPage() {
  const { dataVersion } = usePipeline();
  const products = useApi(api.forecastableProducts, [dataVersion]);
  const saved = useApi(api.inventoryInputs, []);
  const settings = useApi(api.settings, []);
  const [code, setCode] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(blank);
  const [result, setResult] = useState<InventoryResult | null>(null);
  const [calcError, setCalcError] = useState<ApiError | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [historyTick, setHistoryTick] = useState(0);
  const toast = useToast();
  const errors = useMemo(() => validate(form), [form]);
  const valid = Object.keys(errors).length === 0 && !!code;
  const recs = useApi(() => api.inventoryRecommendations(undefined, 50), [historyTick]);
  const risk = useApi(api.riskSummary, [historyTick]);

  useEffect(() => {
    if (!code && products.data?.length) setCode(products.data[0].StockCode);
  }, [products.data, code]);

  // pre-fill ONCE per selected product: last saved inputs for it, otherwise app defaults
  const prefilledFor = useRef<string | null>(null);
  useEffect(() => {
    if (!code || saved.loading || settings.loading || prefilledFor.current === code) return;
    prefilledFor.current = code;
    const s = saved.data?.[code];
    const d = settings.data;
    setForm(s ? {
      current_stock: String(s.current_stock), lead_time_days: String(s.lead_time_days), service_level: String(s.service_level),
      review_period_days: String(s.review_period_days), min_order_qty: s.min_order_qty != null ? String(s.min_order_qty) : "",
      pack_size: s.pack_size != null ? String(s.pack_size) : "", max_capacity: s.max_capacity != null ? String(s.max_capacity) : "",
    } : { ...blank, lead_time_days: String(d?.default_lead_time_days ?? 7), service_level: String(d?.default_service_level ?? 0.95), review_period_days: String(d?.default_review_period_days ?? 7) });
    setResult(null);
  }, [code, saved.data, saved.loading, settings.data, settings.loading]);

  // live "what-if" simulator: recalculate (not saved) 500 ms after inputs stop changing
  useEffect(() => {
    if (!valid || !code) return;
    const req = toRequest(code, form);
    const id = window.setTimeout(() => {
      setCalculating(true);
      setCalcError(null);
      api.calculateInventory(req).then(setResult).catch((e) => setCalcError(toApiError(e))).finally(() => setCalculating(false));
    }, 500);
    return () => window.clearTimeout(id);
  }, [form, code, valid]);

  async function save() {
    if (!valid || !code) return;
    setSaving(true);
    try {
      const r = await api.saveInventory(toRequest(code, form));
      setResult(r);
      toast("success", "Recommendation saved", `${r.stock_code}: ${r.status}, order ${r.suggested_order_quantity} units.`);
      setHistoryTick((t) => t + 1);
      saved.reload();
    } catch (e) {
      toast("error", "Could not save", toApiError(e).message);
    } finally {
      setSaving(false);
    }
  }

  const set = (k: keyof FormState) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <>
      <PageHeader title="Inventory" description="Find out when to reorder and how much to order. Enter your current stock and supplier lead time; results update as you type." />
      <Callout tone="info">Your sales data does not include stock levels, so please enter your current stock and lead time below. Recommendations are based on the demand forecast and these inputs.</Callout>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card>
          <CardHeader title="Inputs" source="user-entered" />
          <CardBody className="space-y-4">
            <AsyncView state={products} loadingHeight="h-16">{(items) => <ProductPicker items={items} value={code} onChange={setCode} />}</AsyncView>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Current stock (units)" error={errors.current_stock} htmlFor="cs"><Input id="cs" type="number" min={0} value={form.current_stock} onChange={set("current_stock")} placeholder="e.g. 250" /></Field>
              <Field label="Supplier lead time (days)" error={errors.lead_time_days} htmlFor="lt"><Input id="lt" type="number" min={1} max={365} value={form.lead_time_days} onChange={set("lead_time_days")} /></Field>
              <Field label="Service level" error={errors.service_level} help="Chance of no stockout during lead time" htmlFor="sl">
                <Select id="sl" value={form.service_level} onChange={set("service_level")}>
                  {["0.8", "0.85", "0.9", "0.95", "0.975", "0.99", "0.995"].map((v) => <option key={v} value={v}>{(Number(v) * 100).toFixed(1).replace(".0", "")}%</option>)}
                  {!["0.8", "0.85", "0.9", "0.95", "0.975", "0.99", "0.995"].includes(form.service_level) && <option value={form.service_level}>{form.service_level}</option>}
                </Select>
              </Field>
              <Field label="Review period (days)" error={errors.review_period_days} help="Days until the next stock review" htmlFor="rp"><Input id="rp" type="number" min={1} max={90} value={form.review_period_days} onChange={set("review_period_days")} /></Field>
              <Field label="Min order qty (optional)" error={errors.min_order_qty} htmlFor="moq"><Input id="moq" type="number" min={0} value={form.min_order_qty} onChange={set("min_order_qty")} /></Field>
              <Field label="Pack size (optional)" error={errors.pack_size} htmlFor="ps"><Input id="ps" type="number" min={1} value={form.pack_size} onChange={set("pack_size")} /></Field>
              <Field label="Max storage capacity (optional)" error={errors.max_capacity} htmlFor="cap"><Input id="cap" type="number" min={1} value={form.max_capacity} onChange={set("max_capacity")} /></Field>
            </div>
            <div className="flex items-center gap-2">
              <Button icon={<Save className="h-4 w-4" />} onClick={save} loading={saving} disabled={!valid}>Save recommendation</Button>
              {calculating && <span className="inline-flex items-center gap-1 text-xs text-slate-500"><LoaderCircle className="h-3 w-3 animate-spin" />recalculating…</span>}
            </div>
          </CardBody>
        </Card>

        <div className="space-y-6 xl:col-span-2">
          {calcError ? <Card><ErrorState error={calcError} /></Card>
            : !result ? <Card><EmptyState icon={<Calculator className="h-6 w-6" />} title="Enter current stock to calculate" description="Results update automatically as you type (what-if simulation). Click Save to keep a recommendation." /></Card>
            : <Result r={result} />}
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card>
          <CardHeader title="Inventory status distribution" subtitle="Latest saved recommendation per product" source="calculated" />
          <CardBody>
            <AsyncView state={risk} empty={(r) => r.assessed_products === 0} emptyTitle="No saved recommendations" emptyDescription="Save a recommendation to start tracking inventory risk.">
              {(r) => (
                <div className="space-y-3">
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={Object.entries(r.status_counts).map(([status, n]) => ({ status, n }))}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="status" tick={{ fontSize: 10 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={30} />
                        <Tooltip />
                        <Bar dataKey="n" name="Products" radius={[4, 4, 0, 0]}>{Object.keys(r.status_counts).map((s) => <Cell key={s} fill={STATUS_COLORS[s]} />)}</Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="text-xs font-semibold uppercase text-slate-500">Reorder alerts</p>
                  {r.alerts.length === 0 ? <p className="text-xs text-slate-500">No alerts.</p> : r.alerts.slice(0, 8).map((a, i) => (
                    <div key={i} className="flex gap-2 text-xs"><TriangleAlert className={a.level === "critical" ? "h-4 w-4 shrink-0 text-rose-500" : "h-4 w-4 shrink-0 text-amber-500"} />{a.message}</div>
                  ))}
                </div>
              )}
            </AsyncView>
          </CardBody>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title="Saved recommendations" subtitle="History in storage/inventory/recommendations.json (newest first)" />
          <AsyncView state={recs} empty={(r) => r.length === 0} emptyTitle="Nothing saved yet">
            {(rows) => (
              <DataTable maxHeight="max-h-96" rows={rows} rowKey={(r) => r.record_id ?? r.stock_code} columns={[
                { key: "created_at", header: "Saved", render: (r) => fmtDateTime(r.created_at) },
                { key: "stock_code", header: "Product", render: (r) => <span title={r.description ?? ""}>{r.stock_code}</span> },
                { key: "stock", header: "Stock", align: "right", render: (r) => fmtNum(r.inputs.current_stock) },
                { key: "lt", header: "Lead time", align: "right", render: (r) => `${r.inputs.lead_time_days}d` },
                { key: "reorder_point", header: "ROP", align: "right", render: (r) => fmtNum(r.reorder_point, 0) },
                { key: "suggested_order_quantity", header: "Order", align: "right", render: (r) => fmtNum(r.suggested_order_quantity) },
                { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
              ]} />
            )}
          </AsyncView>
        </Card>
      </div>
    </>
  );
}

function Result({ r }: { r: InventoryResult }) {
  const pos = [
    { name: "Current stock", value: r.inputs.current_stock, color: "#f59e0b" },
    { name: "Safety stock", value: r.safety_stock, color: "#ef4444" },
    { name: "Reorder point", value: r.reorder_point, color: "#0ea5e9" },
    { name: "Target stock", value: r.target_stock, color: "#10b981" },
  ];
  const L = r.inputs.lead_time_days;
  const R = r.inputs.review_period_days;
  return (
    <>
      <Card>
        <CardBody className="flex flex-wrap items-center gap-4">
          <StatusBadge status={r.status} />
          <p className="flex-1 text-sm text-slate-600 dark:text-slate-300">{r.status_reason}</p>
          <div className="text-right">
            <p className="text-xs text-slate-500">Suggested order</p>
            <p className="text-3xl font-bold tabular-nums text-indigo-600">{fmtNum(r.suggested_order_quantity)} <span className="text-sm font-medium text-slate-500">units</span></p>
          </div>
        </CardBody>
      </Card>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Forecast demand (30d)" value={fmtNum(r.forecast_total, 0)} source="model-predicted" tone="violet" />
        <KpiCard label="Avg daily demand" value={fmtNum(r.average_daily_demand, 2)} hint="units/day" tone="violet" />
        <KpiCard label="Daily demand std" value={r.demand_std_daily == null ? "n/a" : fmtNum(r.demand_std_daily, 2)} hint={`last ${r.variability_observed_days} days`} source="dataset-derived" tone="sky" />
        <KpiCard label="Days of cover" value={r.days_of_cover == null ? "—" : fmtNum(r.days_of_cover, 1)} hint="stock ÷ daily demand" tone="amber" />
        <KpiCard label="Safety stock" value={fmtNum(r.safety_stock, 1)} source="calculated" tone="rose" />
        <KpiCard label="Reorder point" value={fmtNum(r.reorder_point, 1)} tone="sky" />
        <KpiCard label="Target stock" value={fmtNum(r.target_stock, 1)} tone="emerald" />
        <KpiCard label="Lead-time demand" value={fmtNum(r.lead_time_demand, 1)} hint={`${L} days`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Inventory position" subtitle="Current stock compared with the policy levels" />
          <CardBody>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pos}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} />
                  <YAxis tick={{ fontSize: 11 }} width={50} />
                  <Tooltip formatter={(v) => fmtNum(Number(v), 1)} />
                  <ReferenceLine y={r.inputs.current_stock} stroke="#f59e0b" strokeDasharray="4 4" />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>{pos.map((p) => <Cell key={p.name} fill={p.color} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="How it was calculated" source="calculated" />
          <CardBody className="space-y-2 font-mono text-xs leading-relaxed text-slate-700 dark:text-slate-300">
            <p>Z = NormInv({r.inputs.service_level}) = {r.z_value}</p>
            <p>SS = Z × σ × √L = {r.z_value} × {fmtNum(r.demand_std_daily ?? 0, 2)} × √{L} = {fmtNum(r.safety_stock, 2)}</p>
            <p>ROP = d × L + SS = {fmtNum(r.average_daily_demand, 2)} × {L} + {fmtNum(r.safety_stock, 2)} = {fmtNum(r.reorder_point, 2)}</p>
            <p>T = d × (L + R) + SS = {fmtNum(r.average_daily_demand, 2)} × ({L} + {R}) + {fmtNum(r.safety_stock, 2)} = {fmtNum(r.target_stock, 2)}</p>
            <p>Q = max(0, T − stock) = max(0, {fmtNum(r.target_stock, 2)} − {fmtNum(r.inputs.current_stock)}) = {fmtNum(r.raw_order_quantity, 2)}</p>
            <ul className="list-disc pl-5 font-sans">{r.order_adjustments.map((s) => <li key={s}>{s}</li>)}</ul>
            <p className="font-sans text-[11px] text-slate-500">{r.policy.assumptions} Overstock rule: {r.policy.overstock_rule}.</p>
          </CardBody>
        </Card>
      </div>
      {(r.alerts.length > 0 || r.warnings.length > 0) && (
        <div className="space-y-2">
          {r.alerts.map((a) => <Callout key={a.message} tone={a.level === "critical" ? "danger" : a.level === "warning" ? "warning" : "info"}>{a.message}</Callout>)}
          {r.warnings.map((w) => <Callout key={w} tone="warning">{w}</Callout>)}
        </div>
      )}
      <p className="text-xs text-slate-500">{r.disclaimer}</p>
    </>
  );
}
