import { NextResponse } from "next/server";
import * as XLSX from "xlsx";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

const tableByKind = {
  bom: "bom_records",
  masters: "master_records",
  inventory: "inventory_records",
} as const;

type ImportKind = keyof typeof tableByKind;

type JsonRow = Record<string, unknown>;

function supabaseAdmin() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY;
  if (!url || !key) {
    throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.");
  }
  return createClient(url, key, { auth: { persistSession: false } });
}

async function parseWorkbook(file: File, kind: ImportKind): Promise<JsonRow[]> {
  const workbook = XLSX.read(new Uint8Array(await file.arrayBuffer()), {
    type: "array",
    cellDates: true,
  });
  const preferredSheet = kind === "inventory" ? "SAPUI5 Export" : kind === "masters" ? "Masters" : "Sheet1";
  const sheetName = workbook.SheetNames.includes(preferredSheet)
    ? preferredSheet
    : workbook.SheetNames[0];
  if (!sheetName) throw new Error("The workbook has no sheets.");

  return XLSX.utils.sheet_to_json<JsonRow>(workbook.Sheets[sheetName], {
    defval: null,
    raw: false,
  });
}

async function replaceRows(kind: ImportKind, rows: JsonRow[]) {
  const supabase = supabaseAdmin();
  const table = tableByKind[kind];
  const { error: deleteError } = await supabase.from(table).delete().neq("row_number", -1);
  if (deleteError) throw new Error(deleteError.message);

  const payload = rows.map((data, row_number) => ({ row_number, data }));
  for (let start = 0; start < payload.length; start += 500) {
    const { error } = await supabase.from(table).insert(payload.slice(start, start + 500));
    if (error) throw new Error(error.message);
  }
}

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const kind = formData.get("kind");
    const file = formData.get("file");
    if (typeof kind !== "string" || !(kind in tableByKind)) {
      return NextResponse.json({ error: "Unknown import type." }, { status: 400 });
    }
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "An Excel file is required." }, { status: 400 });
    }

    const rows = await parseWorkbook(file, kind as ImportKind);
    if (!rows.length) {
      return NextResponse.json({ error: "The selected sheet contains no rows." }, { status: 400 });
    }
    await replaceRows(kind as ImportKind, rows);
    return NextResponse.json({ kind, rows: rows.length });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Import failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
