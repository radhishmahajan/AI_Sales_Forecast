import { useState } from "react";
import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { api, toApiError } from "../services/api";
import { useApi } from "../hooks/useApi";
import { useToast } from "../components/Toast";
import { AsyncView, Badge, Button, Card, CardBody, CardHeader, DataTable, PageHeader } from "../components/ui";
import { fmtDateTime, fmtNum } from "../services/format";
import type { ReportInfo } from "../types/api";

const TYPES: { type: ReportInfo["report_type"]; title: string; text: string }[] = [
  { type: "sales", title: "Sales report", text: "KPIs, monthly sales and top products (CSV: full product performance + ABC class)." },
  { type: "forecast", title: "Forecasting report", text: "Model test metrics and every saved forecast (CSV: daily predicted demand per saved run)." },
  { type: "inventory", title: "Inventory report", text: "Saved recommendations with user-entered inputs and calculated outputs, plus status counts." },
];

export default function ReportsPage() {
  const reports = useApi(api.reports, []);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();

  async function create(type: ReportInfo["report_type"], format: ReportInfo["format"]) {
    setBusy(`${type}-${format}`);
    try {
      const r = await api.createReport(type, format);
      toast("success", "Report generated", r.file_name);
      reports.reload();
      window.open(api.downloadUrl(r), "_blank", "noopener");
    } catch (e) {
      toast("error", "Report failed", toApiError(e).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Reports" description="Download sales, forecast and inventory reports as CSV or PDF." />
      <div className="grid gap-6 md:grid-cols-3">
        {TYPES.map((t) => (
          <Card key={t.type}>
            <CardHeader title={t.title} />
            <CardBody className="space-y-4">
              <p className="text-sm text-slate-600 dark:text-slate-400">{t.text}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" icon={<FileSpreadsheet className="h-4 w-4" />} loading={busy === `${t.type}-csv`} disabled={!!busy} onClick={() => create(t.type, "csv")}>Export CSV</Button>
                <Button icon={<FileText className="h-4 w-4" />} loading={busy === `${t.type}-pdf`} disabled={!!busy} onClick={() => create(t.type, "pdf")}>Export PDF</Button>
              </div>
            </CardBody>
          </Card>
        ))}
      </div>
      <Card className="mt-6">
        <CardHeader title="Generated reports" subtitle="Newest first" />
        <AsyncView state={reports} empty={(r) => r.length === 0} emptyTitle="No reports yet" emptyDescription="Generate a report above; it will be listed here for download.">
          {(rows) => (
            <DataTable rows={rows} rowKey={(r) => r.report_id} columns={[
              { key: "created_at", header: "Created", render: (r) => fmtDateTime(r.created_at) },
              { key: "report_type", header: "Type", render: (r) => <span className="capitalize">{r.report_type}</span> },
              { key: "format", header: "Format", render: (r) => <Badge tone={r.format === "pdf" ? "red" : "green"}>{r.format.toUpperCase()}</Badge> },
              { key: "file_name", header: "File" },
              { key: "rows", header: "Rows", align: "right", render: (r) => (r.rows == null ? "—" : fmtNum(r.rows)) },
              { key: "size_bytes", header: "Size", align: "right", render: (r) => `${(r.size_bytes / 1024).toFixed(1)} KB` },
              { key: "dl", header: "", render: (r) => <a href={api.downloadUrl(r)} className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline" download><Download className="h-4 w-4" />Download</a> },
            ]} />
          )}
        </AsyncView>
      </Card>
    </>
  );
}
