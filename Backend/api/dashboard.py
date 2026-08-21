from http.server import BaseHTTPRequestHandler
import json

import pandas as pd

from common import json_response, supabase_admin


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_GET(self):
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
                json_response(self, {"rows": [], "monthly": []})
                return
            frame["month"] = pd.to_datetime(frame["report_date"]).dt.strftime("%Y-%m")
            monthly = frame.groupby("month", as_index=False)[["SSPL Value", "K12 Value"]].sum().sort_values("month")
            json_response(self, {"rows": rows, "monthly": json.loads(monthly.to_json(orient="records"))})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)
