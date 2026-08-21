from http.server import BaseHTTPRequestHandler
import json

from common import json_response, supabase_admin


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            report_date = body.get("reportDate")
            rows = body.get("rows")
            if not isinstance(report_date, str) or len(report_date) != 10:
                raise ValueError("A valid inventory date is required.")
            if not isinstance(rows, list) or not rows:
                raise ValueError("Run the calculation and approve a non-empty preview first.")

            client = supabase_admin()
            client.table("final_inventory_records").delete().eq("report_date", report_date).execute()
            for start in range(0, len(rows), 500):
                payload = [
                    {"report_date": report_date, "row_number": start + offset, "data": row}
                    for offset, row in enumerate(rows[start:start + 500])
                ]
                client.table("final_inventory_records").insert(payload).execute()
            json_response(self, {"reportDate": report_date, "rows": len(rows)})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)
