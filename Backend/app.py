import json
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

API_DIR = Path(__file__).parent / "api"
sys.path.insert(0, str(API_DIR))

from common import read_rows, supabase_admin, workbook_rows, write_rows  # noqa: E402
from report import calculate  # noqa: E402

app = FastAPI(title="Inventory Mapping Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TABLES = {"bom": "bom_records", "masters": "master_records", "inventory": "inventory_records"}


def error_response(error: Exception) -> JSONResponse:
    return JSONResponse({"error": str(error)}, status_code=500)


@app.get("/api/status")
def status():
    try:
        return {
            "bom_records": len(read_rows("bom_records")),
            "master_records": len(read_rows("master_records")),
            "inventory_records": len(read_rows("inventory_records")),
        }
    except Exception as error:
        return error_response(error)


@app.get("/api/sources")
def get_sources(kind: str):
    try:
        if kind not in ("bom", "masters"):
            raise ValueError("Source must be 'bom' or 'masters'.")
        return {"kind": kind, "rows": read_rows(TABLES[kind])}
    except Exception as error:
        return error_response(error)


@app.patch("/api/sources")
def update_sources(payload: dict):
    try:
        kind = payload.get("kind")
        rows = payload.get("rows")
        if kind not in ("bom", "masters") or not isinstance(rows, list):
            raise ValueError("A source kind and rows array are required.")
        write_rows(TABLES[kind], rows)
        return {"kind": kind, "rows": len(rows)}
    except Exception as error:
        return error_response(error)


@app.post("/api/import")
def import_workbook(request: Request, kind: str = Form(...), file: UploadFile = File(...)):
    try:
        if kind not in TABLES:
            raise ValueError("Unknown import type.")
        rows = workbook_rows(file.file.read(), kind)
        if not rows:
            raise ValueError("The selected sheet contains no rows.")
        mode = request.headers.get("x-import-mode", "replace")
        if mode == "append" and kind in ("bom", "masters"):
            rows = read_rows(TABLES[kind]) + rows
        write_rows(TABLES[kind], rows)
        return {"kind": kind, "rows": len(rows)}
    except Exception as error:
        return error_response(error)


@app.post("/api/report")
def preview_report(payload: dict):
    try:
        report_date = payload.get("reportDate", "")
        parsed = pd.to_datetime(report_date, errors="coerce")
        if not isinstance(report_date, str) or len(report_date) != 10 or pd.isna(parsed):
            raise ValueError("A valid report date is required.")
        bom = pd.DataFrame(read_rows("bom_records"))
        masters = pd.DataFrame(read_rows("master_records"))
        inventory = pd.DataFrame(read_rows("inventory_records"))
        if bom.empty or masters.empty or inventory.empty:
            raise ValueError("Import BOM, Masters, and Inventory before generating a report.")
        final, failed = calculate(bom, masters, inventory)
        return {
            "reportDate": report_date,
            "rows": len(final),
            "preview": json.loads(final.to_json(orient="records", date_format="iso")),
            "failedRows": json.loads(failed.to_json(orient="records")),
            "failed": len(failed),
            "ssplValue": float(final["SSPL Value"].sum()),
            "k12Value": float(final["K12 Value"].sum()),
        }
    except Exception as error:
        return error_response(error)


@app.post("/api/save")
def save_report(payload: dict):
    try:
        report_date = payload.get("reportDate")
        rows = payload.get("rows")
        if not isinstance(report_date, str) or len(report_date) != 10 or not isinstance(rows, list) or not rows:
            raise ValueError("A valid inventory date and non-empty preview are required.")
        client = supabase_admin()
        client.table("final_inventory_records").delete().eq("report_date", report_date).execute()
        for start in range(0, len(rows), 500):
            payload_rows = [{"report_date": report_date, "row_number": start + offset, "data": row} for offset, row in enumerate(rows[start:start + 500])]
            client.table("final_inventory_records").insert(payload_rows).execute()
        return {"reportDate": report_date, "rows": len(rows)}
    except Exception as error:
        return error_response(error)


@app.get("/api/dashboard")
def dashboard():
    try:
        client = supabase_admin()
        rows = []
        for start in range(0, 10_000_000, 1000):
            result = client.table("final_inventory_records").select("report_date, row_number, data").order("report_date").order("row_number").range(start, start + 999).execute()
            page = result.data or []
            rows.extend({"report_date": row["report_date"], **row["data"]} for row in page)
            if len(page) < 1000:
                break
        frame = pd.DataFrame(rows)
        if frame.empty:
            return {"rows": [], "monthly": []}
        frame["month"] = pd.to_datetime(frame["report_date"]).dt.strftime("%Y-%m")
        monthly = frame.groupby("month", as_index=False)[["SSPL Value", "K12 Value"]].sum().sort_values("month")
        return {"rows": rows, "monthly": json.loads(monthly.to_json(orient="records"))}
    except Exception as error:
        return error_response(error)
