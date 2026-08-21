from http.server import BaseHTTPRequestHandler

from common import json_response, parse_multipart, workbook_rows, write_rows

TABLES = {"bom": "bom_records", "masters": "master_records", "inventory": "inventory_records"}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_POST(self):
        try:
            kind, file_bytes = parse_multipart(self)
            if kind not in TABLES:
                raise ValueError("Unknown import type.")
            if not file_bytes:
                raise ValueError("An Excel file is required.")
            rows = workbook_rows(file_bytes, kind)
            if not rows:
                raise ValueError("The selected sheet contains no rows.")
            write_rows(TABLES[kind], rows)
            json_response(self, {"kind": kind, "rows": len(rows)})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)
