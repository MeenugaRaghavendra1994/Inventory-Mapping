import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

type Row = Record<string, unknown>;
type StoredRow = { row_number: number; data: Row };

function numeric(value: unknown) {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const parsed = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function text(value: unknown) {
  return String(value ?? "").trim();
}

function admin() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY;
  if (!url || !key) throw new Error("Supabase environment variables are missing.");
  return createClient(url, key, { auth: { persistSession: false } });
}

async function allRows(table: string): Promise<Row[]> {
  const supabase = admin();
  const rows: StoredRow[] = [];
  for (let start = 0; ; start += 1000) {
    const { data, error } = await supabase.from(table).select("row_number, data").order("row_number").range(start, start + 999);
    if (error) throw new Error(error.message);
    rows.push(...((data ?? []) as StoredRow[]));
    if (!data || data.length < 1000) break;
  }
  return rows.map((row) => row.data);
}

function required(rows: Row[], columns: string[], name: string) {
  const missing = columns.filter((column) => !(column in (rows[0] ?? {})));
  if (missing.length) throw new Error(`${name} is missing columns: ${missing.join(", ")}`);
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { reportDate?: string };
    const reportDate = body.reportDate;
    if (!reportDate || !/^\d{4}-\d{2}-\d{2}$/.test(reportDate)) throw new Error("A valid report date is required.");

    const [bom, masters, inventory] = await Promise.all([
      allRows("bom_records"), allRows("master_records"), allRows("inventory_records"),
    ]);
    if (!bom.length || !masters.length || !inventory.length) throw new Error("Import BOM, Masters, and Inventory before generating a report.");
    required(bom, ["Material Code", "Component Code", "Component Description", "Component Quantity"], "BOM");
    required(masters, ["Material", "Year", "Eduvate/Private", "Moving Type", "Sub Category", "New Grade", "Volume", "SSPL CP", "K12 CP"], "Masters");
    required(inventory, ["Material", "Material Description", "Plant", "Unrestricted Stock", "Blocked Stock", "Storage Location"], "Inventory");

    const bomMap = new Map<string, Row>();
    for (const row of bom) bomMap.set(text(row["Material Code"]), row);
    const masterMap = new Map<string, Row>();
    for (const row of masters) if (!masterMap.has(text(row.Material))) masterMap.set(text(row.Material), row);

    const grouped = new Map<string, Row>();
    const failed: Row[] = [];
    for (const row of inventory) {
      const material = text(row.Material);
      const stock = numeric(row["Unrestricted Stock"]) + numeric(row["Blocked Stock"]);
      if (!material.startsWith("91")) {
        const item = { Material: material, "Material Description": text(row["Material Description"]), Plant: text(row.Plant), "Storage Location": text(row["Storage Location"]), quantity: stock };
        const key = `${item.Material}|${item["Material Description"]}|${item.Plant}|${item["Storage Location"]}`;
        const existing = grouped.get(key);
        if (existing) existing.quantity = numeric(existing.quantity) + item.quantity;
        else grouped.set(key, item);
        continue;
      }
      const mapping = bomMap.get(material);
      if (!mapping || !text(mapping["Component Code"])) {
        failed.push({ Material: material, Plant: text(row.Plant), "Storage Location": text(row["Storage Location"]), "Unrestricted Stock": stock, Reason: "Not found in BOM" });
        continue;
      }
      const item = { Material: text(mapping["Component Code"]), "Material Description": text(mapping["Component Description"]), Plant: text(row.Plant), "Storage Location": text(row["Storage Location"]), quantity: numeric(mapping["Component Quantity"]) * stock };
      const key = `${item.Material}|${item["Material Description"]}|${item.Plant}|${item["Storage Location"]}`;
      const existing = grouped.get(key);
      if (existing) existing.quantity = numeric(existing.quantity) + item.quantity;
      else grouped.set(key, item);
    }

    const finalInventory = Array.from(grouped.values()).map((item) => {
      const master = masterMap.get(text(item.Material)) ?? {};
      const quantity = numeric(item.quantity);
      return {
        Material: item.Material, "Material Description": item["Material Description"], Plant: item.Plant, "Storage Location": item["Storage Location"],
        "Plant Summation Quantity": quantity, Year: master.Year ?? null, "Eduvate/Private": master["Eduvate/Private"] ?? null, "Moving Type": master["Moving Type"] ?? null,
        "Sub Category": master["Sub Category"] ?? null, "New Grade": master["New Grade"] ?? null, Volume: master.Volume ?? null, "SSPL CP": numeric(master["SSPL CP"]), "K12 CP": numeric(master["K12 CP"]),
        "SSPL Value": quantity * numeric(master["SSPL CP"]), "K12 Value": quantity * numeric(master["K12 CP"]),
      };
    });

    const supabase = admin();
    const { error: deleteError } = await supabase.from("final_inventory_records").delete().eq("report_date", reportDate);
    if (deleteError) throw new Error(deleteError.message);
    for (let start = 0; start < finalInventory.length; start += 500) {
      const payload = finalInventory.slice(start, start + 500).map((data, offset) => ({ report_date: reportDate, row_number: start + offset, data }));
      const { error } = await supabase.from("final_inventory_records").insert(payload);
      if (error) throw new Error(error.message);
    }
    return NextResponse.json({ reportDate, rows: finalInventory.length, failed: failed.length, ssplValue: finalInventory.reduce((sum, row) => sum + numeric(row["SSPL Value"]), 0), k12Value: finalInventory.reduce((sum, row) => sum + numeric(row["K12 Value"]), 0) });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Report generation failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
