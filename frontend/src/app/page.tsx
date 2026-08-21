"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart3, Database, FileSpreadsheet, Pencil, Plus, Save, Trash2, Upload, Zap } from "lucide-react";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:3001";
type View = "run" | "sources" | "dashboard" | "graphs";
type SourceKind = "bom" | "masters";
type Row = Record<string, unknown>;
type Preview = { reportDate: string; rows: number; preview: Row[]; failedRows: Row[]; failed: number; ssplValue: number; k12Value: number };
type DashboardData = { rows: Row[]; monthly: Row[] };

const money = (value: unknown) => `₹${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const display = (value: unknown) => value === null || value === undefined ? "" : String(value);

export default function Home() {
  const [view, setView] = useState<View>("run");
  const [inventoryFile, setInventoryFile] = useState<File | null>(null);
  const [reportDate, setReportDate] = useState(new Date().toISOString().slice(0, 10));
  const [preview, setPreview] = useState<Preview | null>(null);
  const [sourceKind, setSourceKind] = useState<SourceKind>("bom");
  const [sourceRows, setSourceRows] = useState<Row[]>([]);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<"replace" | "append">("append");
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [dashboardDate, setDashboardDate] = useState("all");
  const [dashboardYear, setDashboardYear] = useState("all");
  const [dashboardCategory, setDashboardCategory] = useState("all");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Ready.");

  async function request(path: string, options?: RequestInit) {
    const response = await fetch(`${backendUrl}${path}`, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? "Request failed.");
    return data;
  }
  async function runReport() {
    if (!inventoryFile) return setMessage("Choose an inventory Excel file first.");
    setBusy(true); setMessage("Running calculation from Supabase data...");
    try {
      const form = new FormData(); form.append("kind", "inventory"); form.append("file", inventoryFile);
      await request("/api/import", { method: "POST", body: form });
      const data = await request("/api/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reportDate }) });
      setPreview(data); setMessage("Preview ready. Review it before saving Final Inventory.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Calculation failed."); }
    setBusy(false);
  }
  async function saveReport() {
    if (!preview) return;
    setBusy(true); setMessage(`Saving Final Inventory for ${reportDate}...`);
    try { await request("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reportDate, rows: preview.preview }) }); setMessage(`Final Inventory saved for ${reportDate}.`); await loadDashboard(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Save failed."); }
    setBusy(false);
  }
  async function loadSources(kind = sourceKind) {
    setBusy(true);
    try { const data = await request(`/api/sources?kind=${kind}`); setSourceRows(data.rows); setMessage(`${data.rows.length.toLocaleString()} ${kind} rows loaded.`); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not load source rows."); }
    setBusy(false);
  }
  async function importSource() {
    if (!sourceFile) return;
    setBusy(true); setMessage(`Uploading ${sourceFile.name}...`);
    try { const form = new FormData(); form.append("kind", sourceKind); form.append("file", sourceFile); const data = await request("/api/import", { method: "POST", headers: { "X-Import-Mode": importMode }, body: form }); setMessage(`${data.rows.toLocaleString()} ${sourceKind} rows stored.`); setSourceFile(null); await loadSources(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Source import failed."); }
    setBusy(false);
  }
  async function saveSourceRows(rows = sourceRows) {
    setBusy(true);
    try { const data = await request("/api/sources", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: sourceKind, rows }) }); setSourceRows(rows); setMessage(`${data.rows.toLocaleString()} ${sourceKind} rows saved.`); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not save source rows."); }
    setBusy(false);
  }
  function updateSourceRow(index: number, column: string, value: string) { setSourceRows((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, [column]: value } : row)); }
  function addSourceRow() { setSourceRows((rows) => [...rows, {}]); }
  function deleteSourceRow(index: number) { setSourceRows((rows) => rows.filter((_, rowIndex) => rowIndex !== index)); }
  async function loadDashboard() { try { setDashboard(await request("/api/dashboard")); } catch (error) { setMessage(error instanceof Error ? error.message : "Could not load dashboard."); } }
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadDashboard(); }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (view === "sources") void loadSources();
      if (view === "dashboard" || view === "graphs") void loadDashboard();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [view, sourceKind]);

  const sourceColumns = useMemo(() => Array.from(new Set(sourceRows.flatMap((row) => Object.keys(row)))).slice(0, 12), [sourceRows]);
  const allRows = dashboard?.rows ?? [];
  const years = Array.from(new Set(allRows.map((row) => display(row.Year)).filter(Boolean))).sort();
  const categories = Array.from(new Set(allRows.map((row) => display(row["Eduvate/Private"])).filter(Boolean))).sort();
  const dates = Array.from(new Set(allRows.map((row) => display(row.report_date)).filter(Boolean))).sort();
  const filteredRows = allRows.filter((row) => (dashboardDate === "all" || row.report_date === dashboardDate) && (dashboardYear === "all" || display(row.Year) === dashboardYear) && (dashboardCategory === "all" || display(row["Eduvate/Private"]) === dashboardCategory));
  const monthly = Array.from(filteredRows.reduce((groups, row) => { const month = display(row.report_date).slice(0, 7); const current = groups.get(month) ?? { month, "SSPL Value": 0, "K12 Value": 0 } as Row; current["SSPL Value"] = Number(current["SSPL Value"] ?? 0) + Number(row["SSPL Value"] ?? 0); current["K12 Value"] = Number(current["K12 Value"] ?? 0) + Number(row["K12 Value"] ?? 0); groups.set(month, current); return groups; }, new Map<string, Row>()).values());
  const totalSspl = filteredRows.reduce((sum, row) => sum + Number(row["SSPL Value"] ?? 0), 0);
  const totalK12 = filteredRows.reduce((sum, row) => sum + Number(row["K12 Value"] ?? 0), 0);
  const nav: { id: View; label: string; icon: typeof Zap }[] = [{ id: "run", label: "Run Report", icon: Zap }, { id: "sources", label: "BOM & Masters", icon: FileSpreadsheet }, { id: "dashboard", label: "Dashboard", icon: Database }, { id: "graphs", label: "Bar Graphs", icon: BarChart3 }];

  return <main className="shell">
    <header className="topbar"><div className="brand"><span className="brand-mark"><Database size={18} /></span><span>Inventory Mapping</span></div><span className="connection"><i className="pulse" /> Supabase database</span></header>
    <nav className="nav">{nav.map((item) => { const Icon = item.icon; return <button className={view === item.id ? "nav-item active" : "nav-item"} onClick={() => setView(item.id)} key={item.id}><Icon size={16} />{item.label}</button>; })}</nav>
    <section className="page-title"><p className="eyebrow">{view === "run" ? "INVENTORY WORKFLOW" : view === "sources" ? "PERMANENT SOURCE DATA" : view === "dashboard" ? "SAVED FINAL INVENTORY" : "MONTHLY VALUE TRENDS"}</p><h1>{view === "run" ? <>Run, review,<br /><em>then save.</em></> : view === "sources" ? <>Edit the source<br /><em>of truth.</em></> : view === "dashboard" ? <>Final inventory<br /><em>at a glance.</em></> : <>Value over<br /><em>time.</em></>}</h1></section>
    {view === "run" && <RunView inventoryFile={inventoryFile} setInventoryFile={setInventoryFile} reportDate={reportDate} setReportDate={setReportDate} preview={preview} busy={busy} runReport={runReport} saveReport={saveReport} />}
    {view === "sources" && <SourcesView sourceKind={sourceKind} setSourceKind={setSourceKind} sourceRows={sourceRows} sourceColumns={sourceColumns} sourceFile={sourceFile} setSourceFile={setSourceFile} importMode={importMode} setImportMode={setImportMode} busy={busy} importSource={importSource} loadSources={loadSources} saveSourceRows={saveSourceRows} updateSourceRow={updateSourceRow} addSourceRow={addSourceRow} deleteSourceRow={deleteSourceRow} />}
    {(view === "dashboard" || view === "graphs") && <FilterBar dates={dates} years={years} categories={categories} date={dashboardDate} year={dashboardYear} category={dashboardCategory} setDate={setDashboardDate} setYear={setDashboardYear} setCategory={setDashboardCategory} />}
    {view === "dashboard" && <DashboardView rows={filteredRows} totalSspl={totalSspl} totalK12={totalK12} />}
    {view === "graphs" && <GraphsView monthly={monthly} />}
    <div className="status-line"><span className="status-dot" />{message}</div>
  </main>;
}

function RunView({ inventoryFile, setInventoryFile, reportDate, setReportDate, preview, busy, runReport, saveReport }: { inventoryFile: File | null; setInventoryFile: (file: File | null) => void; reportDate: string; setReportDate: (value: string) => void; preview: Preview | null; busy: boolean; runReport: () => void; saveReport: () => void }) {
  return <><section className="workflow-grid"><article className="panel upload-panel"><span className="step">01 / INPUT</span><FileSpreadsheet className="panel-icon" size={25} /><h2>Inventory snapshot</h2><p>Upload the current SAP inventory. BOM and Masters are read permanently from Supabase.</p><label className="file-picker"><span>{inventoryFile?.name ?? "Choose .xlsx or .xlsm"}</span><input type="file" accept=".xlsx,.xlsm" onChange={(event) => setInventoryFile(event.target.files?.[0] ?? null)} /></label><label className="field-label">Inventory date<input type="date" value={reportDate} onChange={(event) => setReportDate(event.target.value)} /></label><button className="primary-button" disabled={busy || !inventoryFile} onClick={runReport}><Zap size={16} />{busy ? "Running..." : "Run calculation"}</button></article><article className="panel process-panel"><span className="step">02 / APPROVAL</span><h2>Review before saving</h2><p>Run creates a preview only. Save it after checking the totals and rows.</p>{preview ? <><div className="result-grid"><Metric label="Final rows" value={preview.rows.toLocaleString()} /><Metric label="BOM failures" value={preview.failed.toLocaleString()} /><Metric label="SSPL value" value={money(preview.ssplValue)} /><Metric label="K12 value" value={money(preview.k12Value)} /></div><button className="primary-button" disabled={busy} onClick={saveReport}><Save size={16} />Save Final Inventory</button></> : <div className="empty-state">Your calculated preview will appear here.</div>}</article></section>{preview && <PreviewTable rows={preview.preview.slice(0, 100)} />}</>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
function FilterBar(props: { dates: string[]; years: string[]; categories: string[]; date: string; year: string; category: string; setDate: (value: string) => void; setYear: (value: string) => void; setCategory: (value: string) => void }) { return <section className="filter-bar"><label>Inventory date<select value={props.date} onChange={(event) => props.setDate(event.target.value)}><option value="all">All dates</option>{props.dates.map((value) => <option key={value}>{value}</option>)}</select></label><label>Year<select value={props.year} onChange={(event) => props.setYear(event.target.value)}><option value="all">All years</option>{props.years.map((value) => <option key={value}>{value}</option>)}</select></label><label>Eduvate / Private<select value={props.category} onChange={(event) => props.setCategory(event.target.value)}><option value="all">All categories</option>{props.categories.map((value) => <option key={value}>{value}</option>)}</select></label></section>; }
function PreviewTable({ rows }: { rows: Row[] }) { const columns = Object.keys(rows[0] ?? {}).slice(0, 8); return <section className="table-panel"><div className="section-heading"><div><p className="eyebrow">PREVIEW</p><h2>Calculated rows</h2></div><span className="locked">First 100 rows</span></div><DataTable rows={rows} columns={columns} /></section>; }
function SourcesView(props: { sourceKind: SourceKind; setSourceKind: (kind: SourceKind) => void; sourceRows: Row[]; sourceColumns: string[]; sourceFile: File | null; setSourceFile: (file: File | null) => void; importMode: "replace" | "append"; setImportMode: (mode: "replace" | "append") => void; busy: boolean; importSource: () => void; loadSources: () => void; saveSourceRows: (rows?: Row[]) => void; updateSourceRow: (index: number, column: string, value: string) => void; addSourceRow: () => void; deleteSourceRow: (index: number) => void }) {
  const { sourceKind, setSourceKind, sourceRows, sourceColumns, sourceFile, setSourceFile, importMode, setImportMode, busy, importSource, loadSources, saveSourceRows, updateSourceRow, addSourceRow, deleteSourceRow } = props;
  return <><section className="source-toolbar"><div className="segmented"><button className={sourceKind === "bom" ? "selected" : ""} onClick={() => setSourceKind("bom")}>BOM Report</button><button className={sourceKind === "masters" ? "selected" : ""} onClick={() => setSourceKind("masters")}>Masters</button></div><div className="bulk-tools"><label className="file-picker compact"><span>{sourceFile?.name ?? "Bulk upload Excel"}</span><input type="file" accept=".xlsx,.xlsm" onChange={(event) => setSourceFile(event.target.files?.[0] ?? null)} /></label><select value={importMode} onChange={(event) => setImportMode(event.target.value as "replace" | "append")}><option value="append">Add rows</option><option value="replace">Replace all</option></select><button className="secondary-button" disabled={!sourceFile || busy} onClick={importSource}><Upload size={15} />Bulk upload</button></div></section><section className="table-panel"><div className="section-heading"><div><p className="eyebrow">EDITABLE TABLE / {sourceRows.length.toLocaleString()} ROWS</p><h2>{sourceKind === "bom" ? "BOM mappings" : "Master pricing"}</h2></div><div className="table-actions"><button className="icon-button" onClick={addSourceRow} title="Add row"><Plus size={17} /></button><button className="secondary-button" disabled={busy} onClick={() => saveSourceRows()}><Save size={15} />Save changes</button><button className="icon-button" onClick={() => void loadSources()} title="Reload"><Pencil size={15} /></button></div></div><div className="editable-table">{sourceRows.length ? <table><thead><tr><th>#</th>{sourceColumns.map((column) => <th key={column}>{column}</th>)}<th /></tr></thead><tbody>{sourceRows.slice(0, 200).map((row, index) => <tr key={index}><td>{index + 1}</td>{sourceColumns.map((column) => <td key={column}><input value={display(row[column])} onChange={(event) => updateSourceRow(index, column, event.target.value)} /></td>)}<td><button className="danger-button" onClick={() => deleteSourceRow(index)} title="Delete row"><Trash2 size={14} /></button></td></tr>)}</tbody></table> : <div className="empty-state">No source rows found.</div>}</div></section></>;
}
function DataTable({ rows, columns }: { rows: Row[]; columns: string[] }) { return <div className="data-table"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{display(row[column])}</td>)}</tr>)}</tbody></table></div>; }
function DashboardView({ rows, totalSspl, totalK12 }: { rows: Row[]; totalSspl: number; totalK12: number }) { return <><section className="result-grid dashboard-metrics"><Metric label="Saved rows" value={rows.length.toLocaleString()} /><Metric label="SSPL value" value={money(totalSspl)} /><Metric label="K12 value" value={money(totalK12)} /></section><section className="table-panel"><div className="section-heading"><div><p className="eyebrow">SAVED SNAPSHOTS</p><h2>Final inventory records</h2></div></div><DataTable rows={rows.slice(0, 300)} columns={Object.keys(rows[0] ?? {}).slice(0, 12)} /></section></>; }
function GraphsView({ monthly }: { monthly: Row[] }) { const max = Math.max(...monthly.map((row) => Math.max(Number(row["SSPL Value"] ?? 0), Number(row["K12 Value"] ?? 0)), 1)); return <section className="graphs-panel"><div className="section-heading"><div><p className="eyebrow">MONTH-ON-MONTH</p><h2>SSPL and K12 value</h2></div></div>{monthly.length ? <div className="bar-chart">{monthly.map((row) => <div className="bar-group" key={String(row.month)}><div className="bars"><div className="bar sspl" style={{ height: `${Math.max(5, Number(row["SSPL Value"] ?? 0) / max * 100)}%` }} title={`SSPL ${money(row["SSPL Value"])}`} /><div className="bar k12" style={{ height: `${Math.max(5, Number(row["K12 Value"] ?? 0) / max * 100)}%` }} title={`K12 ${money(row["K12 Value"])}`} /></div><span>{String(row.month)}</span></div>)}</div> : <div className="empty-state">No saved Final Inventory reports yet.</div>}<div className="legend"><span className="legend-dot sspl" />SSPL Value <span className="legend-dot k12" />K12 Value</div></section>; }
