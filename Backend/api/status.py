from http.server import BaseHTTPRequestHandler

from common import json_response, read_rows


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_GET(self):
        try:
            counts = {
                "bom_records": len(read_rows("bom_records")),
                "master_records": len(read_rows("master_records")),
                "inventory_records": len(read_rows("inventory_records")),
            }
            json_response(self, counts)
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)
