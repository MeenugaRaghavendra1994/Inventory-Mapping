import json
import os
from email import policy
from email.parser import BytesParser
from io import BytesIO
from typing import Any

import pandas as pd
from supabase import Client, create_client


def supabase_admin() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
    return create_client(url, key)


def cors_origin() -> str:
    return os.environ.get("FRONTEND_URL", "*")


def json_response(handler: Any, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Access-Control-Allow-Origin", cors_origin())
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def parse_multipart(handler: Any) -> tuple[str, bytes]:
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(length)
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + raw_body
    )
    kind = ""
    file_bytes = b""
    for part in message.iter_parts():
        disposition = part.get_content_disposition()
        name = part.get_param("name", header="content-disposition")
        if disposition == "form-data" and name == "kind":
            kind = part.get_content()
        elif disposition == "form-data" and name == "file":
            file_bytes = part.get_payload(decode=True) or b""
    return kind, file_bytes


def read_rows(table: str) -> list[dict[str, Any]]:
    client = supabase_admin()
    rows: list[dict[str, Any]] = []
    for start in range(0, 10_000_000, 1000):
        result = (
            client.table(table)
            .select("row_number, data")
            .order("row_number")
            .range(start, start + 999)
            .execute()
        )
        page = result.data or []
        rows.extend(row["data"] for row in page)
        if len(page) < 1000:
            return rows
    raise RuntimeError(f"Too many rows in Supabase table '{table}'.")


def write_rows(table: str, rows: list[dict[str, Any]]) -> None:
    client = supabase_admin()
    client.table(table).delete().neq("row_number", -1).execute()
    for start in range(0, len(rows), 500):
        payload = [
            {"row_number": start + offset, "data": row}
            for offset, row in enumerate(rows[start:start + 500])
        ]
        client.table(table).insert(payload).execute()


def workbook_rows(file_bytes: bytes, kind: str) -> list[dict[str, Any]]:
    preferred_sheet = {"bom": "Sheet1", "masters": "Masters", "inventory": "SAPUI5 Export"}[kind]
    workbook = pd.ExcelFile(BytesIO(file_bytes))
    sheet = preferred_sheet if preferred_sheet in workbook.sheet_names else workbook.sheet_names[0]
    frame = pd.read_excel(workbook, sheet_name=sheet)
    return json.loads(frame.to_json(orient="records", date_format="iso"))
