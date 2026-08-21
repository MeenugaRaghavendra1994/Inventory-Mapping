from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import parse_qs, urlparse

from common import json_response, read_rows, supabase_admin, write_rows

TABLES = {"bom": "bom_records", "masters": "master_records"}


def read_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    return json.loads(handler.rfile.read(length) or b"{}")


def rows_payload(rows):
    return [{"row_number": index, "data": row} for index, row in enumerate(rows)]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_GET(self):
        try:
            kind = parse_qs(urlparse(self.path).query).get("kind", [""])[0]
            if kind not in TABLES:
                raise ValueError("Source must be 'bom' or 'masters'.")
            rows = read_rows(TABLES[kind])
            json_response(self, {"kind": kind, "rows": rows})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)

    def do_POST(self):
        try:
            body = read_body(self)
            kind = body.get("kind")
            rows = body.get("rows")
            if kind not in TABLES or not isinstance(rows, list):
                raise ValueError("A source kind and rows array are required.")
            write_rows(TABLES[kind], rows)
            json_response(self, {"kind": kind, "rows": len(rows)})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)

    def do_PATCH(self):
        try:
            body = read_body(self)
            kind = body.get("kind")
            rows = body.get("rows")
            if kind not in TABLES or not isinstance(rows, list):
                raise ValueError("A source kind and rows array are required.")
            write_rows(TABLES[kind], rows)
            json_response(self, {"kind": kind, "rows": len(rows)})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)

    def do_DELETE(self):
        try:
            body = read_body(self)
            kind = body.get("kind")
            row_number = body.get("rowNumber")
            if kind not in TABLES or not isinstance(row_number, int):
                raise ValueError("A source kind and row number are required.")
            client = supabase_admin()
            result = client.table(TABLES[kind]).delete().eq("row_number", row_number).execute()
            if not result.data:
                raise ValueError("Source row was not found.")
            rows = read_rows(TABLES[kind])
            write_rows(TABLES[kind], rows)
            json_response(self, {"kind": kind, "rows": len(rows)})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)
