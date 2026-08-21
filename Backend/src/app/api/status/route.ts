import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

const tables = ["bom_records", "master_records", "inventory_records"] as const;

export async function GET() {
  try {
    const url = process.env.SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY;
    if (!url || !key) throw new Error("Supabase environment variables are missing.");
    const supabase = createClient(url, key, { auth: { persistSession: false } });
    const counts = await Promise.all(
      tables.map(async (table) => {
        const { count, error } = await supabase
          .from(table)
          .select("row_number", { count: "exact", head: true });
        if (error) throw new Error(error.message);
        return [table, count ?? 0] as const;
      }),
    );
    return NextResponse.json(Object.fromEntries(counts));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not read Supabase status.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
