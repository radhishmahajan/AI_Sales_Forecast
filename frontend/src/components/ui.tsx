// Reusable UI building blocks: cards, KPI tiles, buttons, badges, form fields and state views.
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { CircleAlert, Inbox, LoaderCircle, RefreshCw, ServerCrash } from "lucide-react";
import type { ApiError } from "../services/api";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// ------------------------------------------------------------------ layout primitives
export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900", className)}>
      {children}
    </section>
  );
}

export function CardHeader({ title, subtitle, actions, source }: { title: string; subtitle?: ReactNode; actions?: ReactNode; source?: SourceKind }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
          {source && <SourceTag kind={source} />}
        </div>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("p-5", className)}>{children}</div>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ data provenance
export type SourceKind = "dataset-derived" | "user-entered" | "model-predicted" | "calculated";
/** Provenance tags (dataset-derived, model-predicted, ...) are intentionally not shown any more. */
export function SourceTag(_props: { kind: SourceKind }) {
  return null;
}

// ------------------------------------------------------------------ KPI tile
export function KpiCard({ label, value, hint, icon, source, tone = "brand" }: {
  label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; source?: SourceKind; tone?: "brand" | "sky" | "emerald" | "amber" | "rose" | "violet";
}) {
  const toneCls = {
    brand: "bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300",
    sky: "bg-sky-50 text-sky-600 dark:bg-sky-950 dark:text-sky-300",
    emerald: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-300",
    amber: "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-300",
    rose: "bg-rose-50 text-rose-600 dark:bg-rose-950 dark:text-rose-300",
    violet: "bg-violet-50 text-violet-600 dark:bg-violet-950 dark:text-violet-300",
  }[tone];
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
          <p className="mt-1.5 truncate text-2xl font-semibold tabular-nums text-slate-900 dark:text-white">{value}</p>
        </div>
        {icon && <div className={cx("rounded-xl p-2.5", toneCls)}>{icon}</div>}
      </div>
      {(hint || source) && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          {source && <SourceTag kind={source} />}
          {hint}
        </div>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ controls
type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
export function Button({ variant = "primary", loading, icon, children, className, disabled, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant; loading?: boolean; icon?: ReactNode;
}) {
  const v = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm disabled:bg-indigo-300 dark:disabled:bg-indigo-900",
    secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
    ghost: "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
  }[variant];
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-70", v, className)}
    >
      {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Segmented<T extends string | number>({ options, value, onChange, label }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-700 dark:bg-slate-800">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx("rounded-md px-3 py-1 text-xs font-medium transition",
            o.value === value ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-950 dark:text-indigo-300" : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const fieldCls = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(fieldCls, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(fieldCls, props.className)} />;
}

export function Field({ label, help, error, children, htmlFor }: { label: string; help?: ReactNode; error?: string | null; children: ReactNode; htmlFor?: string }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-300">{label}</label>
      {children}
      {error ? <p className="mt-1 text-xs text-rose-600">{error}</p> : help ? <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{help}</p> : null}
    </div>
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "indigo" | "sky" }) {
  const t = {
    slate: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    red: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
    indigo: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300",
    sky: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  }[tone];
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", t)}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone = ({ "Critical Stock": "red", "Low Stock": "amber", "Healthy Stock": "green", Overstocked: "indigo" } as const)[status as "Low Stock"] ?? "slate";
  return <Badge tone={tone}>{status}</Badge>;
}

export function AbcBadge({ cls }: { cls: string }) {
  return <Badge tone={cls === "A" ? "green" : cls === "B" ? "amber" : "slate"}>Class {cls}</Badge>;
}

// ------------------------------------------------------------------ state views
export function LoadingState({ label = "Loading…", height = "h-48" }: { label?: string; height?: string }) {
  return (
    <div role="status" className={cx("flex flex-col items-center justify-center gap-2 text-sm text-slate-500", height)}>
      <LoaderCircle className="h-6 w-6 animate-spin text-indigo-500" />
      {label}
    </div>
  );
}

export function EmptyState({ title, description, action, icon }: { title: string; description?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <div className="rounded-full bg-slate-100 p-3 text-slate-500 dark:bg-slate-800">{icon ?? <Inbox className="h-6 w-6" />}</div>
      <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</p>
      {description && <p className="max-w-md text-sm text-slate-500 dark:text-slate-400">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const needsPipeline = ["PIPELINE_REQUIRED", "MODEL_NOT_AVAILABLE"].includes(error.code);
  if (needsPipeline) {
    return (
      <EmptyState
        icon={<CircleAlert className="h-6 w-6 text-amber-500" />}
        title="Setup needed"
        description={<>{error.message} Run <code className="rounded bg-slate-100 px-1 py-0.5 text-xs dark:bg-slate-800">python -m ml.pipeline</code> once from the project folder, then refresh.</>}
      />
    );
  }
  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <div className="rounded-full bg-rose-50 p-3 text-rose-600 dark:bg-rose-950">
        {error.code === "NETWORK_ERROR" ? <ServerCrash className="h-6 w-6" /> : <CircleAlert className="h-6 w-6" />}
      </div>
      <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Something went wrong</p>
      <p className="max-w-lg text-sm text-slate-500 dark:text-slate-400">{error.message}</p>
      {onRetry && <Button variant="secondary" icon={<RefreshCw className="h-4 w-4" />} onClick={onRetry}>Retry</Button>}
    </div>
  );
}

/** Render loading / error / empty / success for one API state. */
export function AsyncView<T>({ state, empty, emptyTitle = "No data", emptyDescription, children, loadingHeight }: {
  state: { data: T | null; error: ApiError | null; loading: boolean; reload: () => void };
  empty?: (d: T) => boolean; emptyTitle?: string; emptyDescription?: ReactNode; children: (d: T) => ReactNode; loadingHeight?: string;
}) {
  if (state.loading && state.data === null) return <LoadingState height={loadingHeight} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (state.data === null) return <LoadingState height={loadingHeight} />;
  if (empty?.(state.data)) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  return <>{children(state.data)}</>;
}

// ------------------------------------------------------------------ table
export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right";
}
export function DataTable<T>({ columns, rows, rowKey, maxHeight, onRowClick }: {
  columns: Column<T>[]; rows: T[]; rowKey: (r: T, i: number) => string; maxHeight?: string; onRowClick?: (r: T) => void;
}) {
  return (
    <div className={cx("scrollbar-thin overflow-auto", maxHeight)}>
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-900 dark:text-slate-400">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={cx("whitespace-nowrap px-4 py-2.5 font-medium", c.align === "right" ? "text-right" : "text-left")}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((r, i) => (
            <tr key={rowKey(r, i)} onClick={onRowClick ? () => onRowClick(r) : undefined}
                className={cx("hover:bg-slate-50 dark:hover:bg-slate-800/50", onRowClick && "cursor-pointer")}>
              {columns.map((c) => (
                <td key={c.key} className={cx("whitespace-nowrap px-4 py-2.5 text-slate-700 dark:text-slate-300", c.align === "right" && "text-right tabular-nums")}>
                  {c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Callout({ tone = "info", title, children }: { tone?: "info" | "warning" | "success" | "danger"; title?: string; children: ReactNode }) {
  const t = {
    info: "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-200",
    warning: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-200",
    danger: "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-200",
  }[tone];
  return (
    <div className={cx("rounded-xl border px-4 py-3 text-sm", t)}>
      {title && <p className="mb-0.5 font-semibold">{title}</p>}
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}
