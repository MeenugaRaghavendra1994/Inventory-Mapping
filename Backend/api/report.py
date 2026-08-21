from http.server import BaseHTTPRequestHandler
import json

import pandas as pd

from common import json_response, read_rows, supabase_admin

BOM_REQUIRED = ["Material Code", "Component Code", "Component Description", "Component Quantity"]
MASTERS_REQUIRED = ["Material", "Year", "Eduvate/Private", "Moving Type", "Sub Category", "New Grade", "Volume", "SSPL CP", "K12 CP"]
INVENTORY_REQUIRED = ["Material", "Material Description", "Plant", "Unrestricted Stock", "Blocked Stock", "Storage Location"]


def number(value: object) -> float:
    return pd.to_numeric(str(value).replace(",", ""), errors="coerce") or 0


def validate(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")


def calculate(bom: pd.DataFrame, masters: pd.DataFrame, inventory: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate(bom, BOM_REQUIRED, "BOM")
    validate(masters, MASTERS_REQUIRED, "Masters")
    validate(inventory, INVENTORY_REQUIRED, "Inventory")

    bom = bom.copy()
    masters = masters.copy()
    inventory = inventory.copy()
    bom["Material Code"] = pd.to_numeric(bom["Material Code"], errors="coerce").astype("Int64")
    bom["Component Code"] = pd.to_numeric(bom["Component Code"], errors="coerce").astype("Int64")
    bom["Component Quantity"] = pd.to_numeric(bom["Component Quantity"], errors="coerce").fillna(0)
    masters["Material"] = pd.to_numeric(masters["Material"], errors="coerce").astype("Int64")
    masters = masters.drop_duplicates(subset=["Material"]).copy()
    for column in ("SSPL CP", "K12 CP"):
        masters[column] = pd.to_numeric(masters[column], errors="coerce").fillna(0)
    inventory["Material"] = pd.to_numeric(inventory["Material"], errors="coerce").astype("Int64")
    inventory["Plant"] = pd.to_numeric(inventory["Plant"], errors="coerce").astype("Int64")
    for column in ("Unrestricted Stock", "Blocked Stock"):
        inventory[column] = pd.to_numeric(inventory[column], errors="coerce").fillna(0)
    inventory["Unrestricted Stock"] += inventory["Blocked Stock"]

    is_kit = inventory["Material"].astype("string").str.startswith("91", na=False)
    normal = inventory.loc[~is_kit, ["Material", "Material Description", "Plant", "Storage Location", "Unrestricted Stock"]].rename(columns={"Unrestricted Stock": "Final Quantity"})
    kits = inventory.loc[is_kit, ["Material", "Plant", "Storage Location", "Unrestricted Stock"]]
    converted = kits.merge(bom[["Material Code", "Component Code", "Component Description", "Component Quantity"]], left_on="Material", right_on="Material Code", how="left", sort=False)
    converted["Final Quantity"] = converted["Component Quantity"].fillna(0) * converted["Unrestricted Stock"].fillna(0)
    failed = converted.loc[converted["Component Code"].isna(), ["Material", "Plant", "Storage Location", "Unrestricted Stock"]].drop_duplicates().copy()
    failed["Reason"] = "Not found in BOM"
    converted = converted.loc[converted["Component Code"].notna()].copy()
    converted_final = converted[["Component Code", "Component Description", "Plant", "Storage Location", "Final Quantity"]].rename(columns={"Component Code": "Material", "Component Description": "Material Description"})
    combined = pd.concat([normal[["Material", "Material Description", "Plant", "Storage Location", "Final Quantity"]], converted_final], ignore_index=True)
    final = combined.groupby(["Material", "Material Description", "Plant", "Storage Location"], as_index=False, sort=False)["Final Quantity"].sum().rename(columns={"Final Quantity": "Plant Summation Quantity"})
    master_columns = ["Material", "Year", "Eduvate/Private", "Moving Type", "Sub Category", "New Grade", "Volume", "SSPL CP", "K12 CP"]
    final = final.merge(masters[master_columns], on="Material", how="left", sort=False)
    final["SSPL Value"] = (final["Plant Summation Quantity"] * final["SSPL CP"]).fillna(0)
    final["K12 Value"] = (final["Plant Summation Quantity"] * final["K12 CP"]).fillna(0)
    return final, failed


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            report_date = body.get("reportDate", "")
            parsed_date = pd.to_datetime(report_date, errors="coerce")
            if not isinstance(report_date, str) or len(report_date) != 10 or pd.isna(parsed_date):
                raise ValueError("A valid report date is required.")
            bom = pd.DataFrame(read_rows("bom_records"))
            masters = pd.DataFrame(read_rows("master_records"))
            inventory = pd.DataFrame(read_rows("inventory_records"))
            if bom.empty or masters.empty or inventory.empty:
                raise ValueError("Import BOM, Masters, and Inventory before generating a report.")
            final, failed = calculate(bom, masters, inventory)
            records = json.loads(final.to_json(orient="records", date_format="iso"))
            json_response(self, {"reportDate": report_date, "rows": len(records), "preview": records, "failedRows": json.loads(failed.to_json(orient="records")), "failed": len(failed), "ssplValue": float(final["SSPL Value"].sum()), "k12Value": float(final["K12 Value"].sum())})
        except Exception as error:
            json_response(self, {"error": str(error)}, 500)
