"use client";

import { useEffect, useState } from "react";
import { Activity, ArrowUpFromLine, Database, FileSpreadsheet, RefreshCw } from "lucide-react";

type ImportKind = "bom" | "masters" | "inventory";
type Counts = { bom_records: number; master_records: number; inventory_records: number };
const imports: { kind: ImportKind; title: string; description: string; table: keyof Counts }[] = [
  { kind: "bom", title: "BOM report", description: "Upload the SAP component mapping once.", table: "bom_records" },
  { kind: "masters", title: "Masters", description: "Upload pricing and classification data once.", table: "master_records" },
  { kind: "inventory", title: "Inventory snapshot", description: "Upload a new stock snapshot when you generate a report.", table: "inventory_records" },
];

export default function Home() {
  const [counts, setCounts] = useState<Counts | null>(null);
  const [files, setFiles] = useState<Record<ImportKind, File | null>>({ bom: null, masters: null, inventory: null });
  const [busy, setBusy] = useState<ImportKind | null>(null);
  const [message, setMessage] = useState("Ready for your first data import.");
  async function refreshStatus() { const response = await fetch("/api/status"); const data = await response.json(); if (response.ok) setCounts(data); }
  useEffect(() => { refreshStatus(); }, []);
  async function upload(kind: ImportKind) {
    const file = files[kind]; if (!file) return; setBusy(kind); setMessage(`Importing ${file.name} into Supabase...`);
    const formData = new FormData(); formData.append("kind", kind); formData.append("file", file);
    const response = await fetch("/api/import", { method: "POST", body: formData }); const data = await response.json(); setBusy(null);
    if (!response.ok) { setMessage(data.error ?? "Import failed."); return; }
    setMessage(`${data.rows.toLocaleString()} rows saved to Supabase.`); setFiles((current) => ({ ...current, [kind]: null })); await refreshStatus();
  }
  return <main className="shell">
    <header className="topbar"><div className="brand"><span className="brand-mark"><Database size={18} /></span><span>Inventory Mapping</span></div><div className="connection"><span className="pulse" /> Supabase connected</div></header>
    <section className="hero"><div><p className="eyebrow">CONTROL CENTER / DATA SETUP</p><h1>Build every report from<br /><em>one source of truth.</em></h1><p className="lede">Import the reference workbooks once. From then on, your Vercel app reads BOM, Masters, and Inventory directly from Supabase.</p></div><div className="hero-stat"><Activity size={20} /><span>Database rows</span><strong>{counts ? Object.values(counts).reduce((sum, value) => sum + value, 0).toLocaleString() : "--"}</strong></div></section>
    <section className="section-heading"><div><p className="eyebrow">DATA SOURCES</p><h2>Import workbooks</h2></div><button className="icon-button" onClick={refreshStatus} title="Refresh Supabase status"><RefreshCw size={17} /></button></section>
    <section className="import-grid">{imports.map((item, index) => <article className={`import-card ${index === 2 ? "accent" : ""}`} key={item.kind}><div className="card-top"><span className="step">0{index + 1}</span><FileSpreadsheet size={21} /></div><h3>{item.title}</h3><p>{item.description}</p><div className="stored"><span>Stored rows</span><strong>{counts?.[item.table]?.toLocaleString() ?? "--"}</strong></div><label className="file-picker"><span>{files[item.kind]?.name ?? "Choose .xlsx or .xlsm"}</span><input type="file" accept=".xlsx,.xlsm" onChange={(event) => setFiles((current) => ({ ...current, [item.kind]: event.target.files?.[0] ?? null }))} /></label><button className="upload-button" disabled={!files[item.kind] || busy !== null} onClick={() => upload(item.kind)}><ArrowUpFromLine size={16} />{busy === item.kind ? "Importing..." : "Import to Supabase"}</button></article>)}</section>
    <div className="status-line"><span className={message.includes("failed") || message.includes("Could") ? "status-dot error" : "status-dot"} />{message}</div>
    <section className="next-step"><div><p className="eyebrow">NEXT STEP</p><h2>Generate from stored data</h2><p>Once the three source tables are populated, report generation will calculate from Supabase rows without reading local Excel files.</p></div><span className="locked">Available after imports</span></section>
  </main>;
}
