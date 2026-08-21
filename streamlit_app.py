from io import BytesIO
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client


BASE_DIR = Path(__file__).resolve().parent
BOM_FILE = BASE_DIR / "BOM Report SAP.xlsx"
INVENTORY_FILE = BASE_DIR / "Inventory.xlsx"
MASTERS_FILE = BASE_DIR / "Masters.xlsx"

BOM_REQUIRED = {
    "Material Code",
    "Component Code",
    "Component Description",
    "Component Quantity",
}
MASTERS_REQUIRED = {
    "Material",
    "Eduvate/Private",
    "Moving Type",
    "Sub Category",
    "New Grade",
    "Volume",
    "SSPL CP",
    "K12 CP",
}


def load_sources():
    client = get_supabase_client()
    if client is not None:
        return (
            load_dataframe_from_supabase(client, "bom_records"),
            load_dataframe_from_supabase(client, "master_records"),
        )

    return load_sources_from_excel()


def load_sources_from_excel():
    bom = pd.read_excel(BOM_FILE, sheet_name="Sheet1")
    masters_book = pd.ExcelFile(MASTERS_FILE)
    sheet = "Masters" if "Masters" in masters_book.sheet_names else masters_book.sheet_names[0]
    masters = pd.read_excel(MASTERS_FILE, sheet_name=sheet)
    return bom, masters


def load_inventory(uploaded_file):
    inventory_book = pd.ExcelFile(uploaded_file)
    sheet = (
        "SAPUI5 Export"
        if "SAPUI5 Export" in inventory_book.sheet_names
        else inventory_book.sheet_names[0]
    )
    return pd.read_excel(uploaded_file, sheet_name=sheet)

def clean_material(series):
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def filter_options(frame, column):
    return sorted(frame[column].dropna().unique().tolist(), key=str)


def apply_filtered_edits(original, edited):
    existing_index = edited.index.intersection(original.index)
    if len(existing_index):
        original.loc[existing_index, edited.columns] = edited.loc[existing_index]

    new_rows = edited.loc[~edited.index.isin(original.index)]
    if not new_rows.empty:
        original = pd.concat([original, new_rows], ignore_index=True)
    return original


def format_rupees(value):
    return f"₹{value:,.0f}"


def stretch_width_kwargs():
    version = tuple(int(part) for part in st.__version__.split(".")[:2])
    if version >= (1, 50):
        return {"width": "stretch"}
    return {"use_container_width": True}


def run_mapping(bom, inventory, masters):
    missing = BOM_REQUIRED - set(bom.columns)
    if missing:
        raise ValueError(f"BOM is missing columns: {sorted(missing)}")
    missing = MASTERS_REQUIRED - set(masters.columns)
    if missing:
        raise ValueError(f"Masters is missing columns: {sorted(missing)}")

    inventory_required = {
        "Material",
        "Material Description",
        "Plant",
        "Unrestricted Stock",
        "Blocked Stock",
        "Storage Location",
    }
    missing = inventory_required - set(inventory.columns)
    if missing:
        raise ValueError(f"Inventory is missing columns: {sorted(missing)}")

    bom = bom.copy()
    inventory = inventory.copy()
    masters = masters.copy()

    for column in ("Material Code", "Component Code"):
        bom[column] = clean_material(bom[column])
    bom["Component Quantity"] = pd.to_numeric(
        bom["Component Quantity"], errors="coerce"
    ).fillna(0)

    inventory["Material"] = clean_material(inventory["Material"])
    inventory["Plant"] = clean_material(inventory["Plant"])
    for column in ("Unrestricted Stock", "Blocked Stock"):
        inventory[column] = pd.to_numeric(inventory[column], errors="coerce").fillna(0)
    inventory["Unrestricted Stock"] += inventory["Blocked Stock"]

    masters["Material"] = clean_material(masters["Material"])
    masters = masters.drop_duplicates(subset=["Material"]).copy()
    for column in ("SSPL CP", "K12 CP"):
        masters[column] = pd.to_numeric(masters[column], errors="coerce").fillna(0)

    is_91 = inventory["Material"].astype("string").str.startswith("91", na=False)
    normal = inventory.loc[~is_91, [
        "Material", "Material Description", "Plant", "Storage Location",
        "Unrestricted Stock",
    ]].rename(columns={"Unrestricted Stock": "Final Quantity"})
    kits = inventory.loc[is_91, [
        "Material", "Plant", "Storage Location", "Unrestricted Stock",
    ]]

    converted = kits.merge(
        bom[["Material Code", "Component Code", "Component Description", "Component Quantity"]],
        left_on="Material", right_on="Material Code", how="left", sort=False,
    )
    converted["Final Quantity"] = (
        converted["Component Quantity"].fillna(0)
        * converted["Unrestricted Stock"].fillna(0)
    )
    bom_failed = converted.loc[converted["Component Code"].isna(), [
        "Material", "Plant", "Storage Location", "Unrestricted Stock",
    ]].drop_duplicates().copy()
    bom_failed["Reason"] = "Not found in BOM"

    converted = converted.loc[converted["Component Code"].notna()].copy()
    converted_final = converted[[
        "Component Code", "Component Description", "Plant", "Storage Location",
        "Final Quantity",
    ]].rename(columns={
        "Component Code": "Material",
        "Component Description": "Material Description",
    })

    combined = pd.concat([
        normal[["Material", "Material Description", "Plant", "Storage Location", "Final Quantity"]],
        converted_final[["Material", "Material Description", "Plant", "Storage Location", "Final Quantity"]],
    ], ignore_index=True)
    final_inventory = combined.groupby([
        "Material", "Material Description", "Plant", "Storage Location",
    ], as_index=False, sort=False)["Final Quantity"].sum()
    final_inventory = final_inventory.rename(columns={"Final Quantity": "Plant Summation Quantity"})

    master_columns = [
        "Material", "Year", "Eduvate/Private", "Moving Type", "Sub Category",
        "New Grade", "Volume", "SSPL CP", "K12 CP",
    ]
    final_inventory = final_inventory.merge(
        masters[master_columns], on="Material", how="left", sort=False,
    )
    final_inventory["SSPL Value"] = (
        final_inventory["Plant Summation Quantity"] * final_inventory["SSPL CP"]
    ).fillna(0)
    final_inventory["K12 Value"] = (
        final_inventory["Plant Summation Quantity"] * final_inventory["K12 CP"]
    ).fillna(0)

    normal_validation = normal.copy()
    normal_validation["Record Type"] = "Normal"
    normal_validation["Source Material"] = normal_validation["Material"]
    normal_validation["Source Description"] = normal_validation["Material Description"]
    normal_validation["Component Code"] = pd.Series(pd.NA, index=normal.index, dtype="Int64")
    normal_validation["Component Description"] = pd.Series(pd.NA, index=normal.index, dtype="string")
    normal_validation["Component Quantity"] = pd.Series(pd.NA, index=normal.index, dtype="Float64")
    normal_validation["Source Unrestricted Stock"] = normal_validation["Final Quantity"]

    converted_validation = converted.copy()
    converted_validation["Record Type"] = "Converted"
    converted_validation["Source Material"] = converted_validation["Material"]
    converted_validation["Source Description"] = pd.Series(pd.NA, index=converted.index, dtype="string")
    converted_validation["Source Unrestricted Stock"] = converted_validation["Unrestricted Stock"]

    validation_columns = [
        "Record Type", "Source Material", "Source Description", "Component Code",
        "Component Description", "Component Quantity", "Plant",
        "Source Unrestricted Stock", "Final Quantity",
    ]
    working_file = pd.concat([
        normal_validation[validation_columns],
        converted_validation[validation_columns],
    ], ignore_index=True, sort=False)
    working_file = working_file.merge(
        masters[master_columns], left_on="Source Material", right_on="Material",
        how="left", sort=False,
    ).drop(columns=["Material"])

    final_91 = final_inventory[
        final_inventory["Material"].astype("string").str.startswith("91", na=False)
    ]
    if not final_91.empty:
        raise ValueError("91-series materials are still present in the result.")

    return {
        "Final Inventory": final_inventory,
        "Working File": working_file,
        "BOM Failed": bom_failed,
    }


def workbook_bytes(sheets):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            if name != "BOM Failed" or not frame.empty:
                frame.to_excel(writer, sheet_name=name, index=False)
    return output.getvalue()


def save_sources(bom, masters):
    bom.to_excel(BOM_FILE, sheet_name="Sheet1", index=False)
    masters.to_excel(MASTERS_FILE, sheet_name="Masters", index=False)


def get_supabase_client():
    try:
        config = st.secrets["supabase"]
        url = config.get("url") or config.get("SUPABASE_URL")
        key = (
            config.get("service_role_key")
            or config.get("key")
            or config.get("SUPABASE_SERVICE_ROLE_KEY")
        )
    except (KeyError, FileNotFoundError):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not url or not key:
        return None
    return create_client(url.strip(), key.strip())


def dataframe_records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def save_dataframe_to_supabase(client, table_name, frame):
    client.table(table_name).delete().neq("row_number", -1).execute()
    records = [
        {"row_number": row_number, "data": record}
        for row_number, record in enumerate(dataframe_records(frame))
    ]
    for start in range(0, len(records), 500):
        client.table(table_name).insert(records[start:start + 500]).execute()


def save_sources_to_supabase(bom, masters):
    client = get_supabase_client()
    if client is None:
        raise ValueError(
            "Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY "
            "to Streamlit secrets or environment variables. Use the current "
            "service_role key for this Supabase project."
        )
    save_dataframe_to_supabase(client, "bom_records", bom)
    save_dataframe_to_supabase(client, "master_records", masters)


def save_final_inventory_to_supabase(report_date, final_inventory):
    client = get_supabase_client()
    if client is None:
        raise ValueError(
            "Supabase is not configured. Add the current service_role key "
            "to Streamlit secrets."
        )

    report_date_value = report_date.isoformat()
    client.table("final_inventory_records").delete().eq(
        "report_date", report_date_value
    ).execute()
    records = [
        {
            "report_date": report_date_value,
            "row_number": row_number,
            "data": record,
        }
        for row_number, record in enumerate(dataframe_records(final_inventory))
    ]
    for start in range(0, len(records), 500):
        client.table("final_inventory_records").insert(
            records[start:start + 500]
        ).execute()


def load_historical_inventory_from_supabase():
    client = get_supabase_client()
    if client is None:
        return pd.DataFrame()

    rows = load_supabase_rows(
        client,
        "final_inventory_records",
        "report_date, row_number, data",
        order_columns=["report_date", "row_number"],
    )
    if not rows:
        return pd.DataFrame()

    historical = pd.DataFrame([
        {"report_date": row["report_date"], **row["data"]}
        for row in rows
    ])
    historical["report_date"] = pd.to_datetime(historical["report_date"])
    return historical


def load_dataframe_from_supabase(client, table_name):
    rows = load_supabase_rows(
        client,
        table_name,
        "row_number, data",
        order_columns=["row_number"],
    )
    if not rows:
        raise ValueError(
            f"Supabase table '{table_name}' is empty. Save the source data first."
        )
    return pd.DataFrame([row["data"] for row in rows])


def load_supabase_rows(client, table_name, columns, order_columns):
    rows = []
    page_size = 1000
    start = 0
    while True:
        query = client.table(table_name).select(columns)
        for column in order_columns:
            query = query.order(column)
        page = query.range(start, start + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size

st.set_page_config(page_title="Inventory Mapping", page_icon=":bar_chart", layout="wide")
st.title("Inventory Mapping")
st.caption("Edit source mappings, save them to Excel, and generate the final inventory.")

inventory_file = st.file_uploader(
    "Upload the current Inventory Excel file",
    type=["xlsx", "xlsm"],
    help="The SAPUI5 Export sheet is used when available; otherwise the first sheet is used.",
)
if inventory_file is not None:
    st.caption(f"Selected inventory file: {inventory_file.name}")

if "bom" not in st.session_state or "masters" not in st.session_state:
    try:
        loaded_bom, loaded_masters = load_sources()
        st.session_state.bom = loaded_bom
        st.session_state.masters = loaded_masters
    except Exception as error:
        st.error(f"Could not load source files: {error}")
        st.stop()

bom_tab, masters_tab, dashboard_tab, bom_failed_tab = st.tabs([
    "BOM Report SAP",
    "Masters",
    "Dashboard",
    "BOM Failed Cases",
])
with bom_tab:
    st.info("Edit existing rows or use Add rows at the bottom. Delete rows with the checkbox in the row menu.")
    edited_bom = st.data_editor(
        st.session_state.bom,
        num_rows="dynamic",
        **stretch_width_kwargs(),
        hide_index=True,
        key="bom_editor",
    )
    st.session_state.bom = edited_bom
    st.caption(f"{len(edited_bom):,} BOM rows")

with masters_tab:
    st.info("Edit existing rows or use Add rows at the bottom. Delete rows with the checkbox in the row menu.")
    filter_columns = [
        "Year",
        "Eduvate/Private",
        "Moving Type",
        "Sub Category",
        "New Grade",
        "Volume",
    ]
    filter_values = {}
    filter_cols = st.columns(3)
    for position, column in enumerate(filter_columns):
        with filter_cols[position % 3]:
            filter_values[column] = st.multiselect(
                column,
                options=filter_options(st.session_state.masters, column),
                key=f"masters_filter_{column}",
            )

    filtered_masters = st.session_state.masters
    for column, selected_values in filter_values.items():
        if selected_values:
            filtered_masters = filtered_masters[
                filtered_masters[column].isin(selected_values)
            ]

    edited_masters = st.data_editor(
        filtered_masters,
        num_rows="dynamic",
        **stretch_width_kwargs(),
        hide_index=True,
        key="masters_editor",
    )
    st.session_state.masters = apply_filtered_edits(
        st.session_state.masters, edited_masters
    )
    st.caption(
        f"Showing {len(filtered_masters):,} of {len(st.session_state.masters):,} master rows"
    )

button_col, supabase_col, status_col = st.columns([1, 1, 2])
with button_col:
    if st.button("Save source Excel files", type="secondary"):
        try:
            save_sources(st.session_state.bom, st.session_state.masters)
            st.success("BOM and Masters saved.")
        except Exception as error:
            st.error(f"Could not save source files: {error}")

with supabase_col:
    if st.button("Save to Supabase", type="secondary"):
        try:
            save_sources_to_supabase(
                st.session_state.bom,
                st.session_state.masters,
            )
            st.success("BOM and Masters saved to Supabase.")
        except Exception as error:
            st.error(f"Could not save to Supabase: {error}")

    if st.button("Restore Excel sources to Supabase", type="secondary"):
        try:
            excel_bom, excel_masters = load_sources_from_excel()
            save_sources_to_supabase(excel_bom, excel_masters)
            st.session_state.bom = excel_bom
            st.session_state.masters = excel_masters
            st.success("BOM and Masters restored to Supabase from the bundled Excel files.")
            st.rerun()
        except Exception as error:
            st.error(f"Could not restore Excel sources to Supabase: {error}")

with status_col:
    st.write("Changes are kept in the current session until you save them or generate an output file.")

st.divider()
report_date = st.date_input(
    "Report date",
    value=pd.Timestamp.today().date(),
    help="Saving the same date again replaces that date's previous snapshot.",
)
if st.button("Generate Final Inventory", type="primary"):
    try:
        if inventory_file is None:
            st.warning("Upload an Inventory Excel file before generating the report.")
            st.stop()
        with st.spinner("Preparing final inventory..."):
            inventory = load_inventory(inventory_file)
            result = run_mapping(st.session_state.bom, inventory, st.session_state.masters)
            output = workbook_bytes(result)
        st.session_state.result = result
        st.session_state.output = output
        st.success(
            f"Generated {len(result['Final Inventory']):,} final rows. "
            f"BOM failures: {len(result['BOM Failed']):,}."
        )
    except Exception as error:
        st.error(f"Could not generate inventory: {error}")

if "output" in st.session_state:
    st.download_button(
        "Download Final Inventory.xlsx",
        data=st.session_state.output,
        file_name="Final Inventory.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    with st.expander("Preview generated Final Inventory"):
        st.dataframe(
            st.session_state.result["Final Inventory"],
            hide_index=True,
            **stretch_width_kwargs(),
        )

    if st.button("Save Final Inventory to Supabase", type="secondary"):
        try:
            save_final_inventory_to_supabase(
                report_date,
                st.session_state.result["Final Inventory"],
            )
            st.success(
                f"Final Inventory saved to Supabase for {report_date.isoformat()}."
            )
        except Exception as error:
            st.error(f"Could not save Final Inventory to Supabase: {error}")

with dashboard_tab:
    st.subheader("Month-on-Month Value Dashboard")
    historical_data = load_historical_inventory_from_supabase()
    if historical_data.empty:
        st.info("Save at least one dated Final Inventory to Supabase to view charts.")
    else:
        sspl_tab, k12_tab = st.tabs(["SSPL Value", "K12 Value"])
        chart_filters = st.columns(2)
        with chart_filters[0]:
            selected_years = st.multiselect(
                "Filter by Year",
                options=filter_options(historical_data, "Year"),
                key="historical_year_filter",
            )
        with chart_filters[1]:
            selected_categories = st.multiselect(
                "Filter by Eduvate/Private",
                options=filter_options(historical_data, "Eduvate/Private"),
                key="historical_category_filter",
            )

        filtered_history = historical_data
        if selected_years:
            filtered_history = filtered_history[
                filtered_history["Year"].isin(selected_years)
            ]
        if selected_categories:
            filtered_history = filtered_history[
                filtered_history["Eduvate/Private"].isin(selected_categories)
            ]

        chart_data = filtered_history.copy()
        chart_data["Report Month"] = (
            chart_data["report_date"].dt.to_period("M").astype("string")
        )
        monthly_values = chart_data.groupby("Report Month")[[
            "SSPL Value", "K12 Value"
        ]].sum().sort_index()

        with sspl_tab:
            st.bar_chart(monthly_values["SSPL Value"], y_label="SSPL Value (₹)")
            st.dataframe(
                monthly_values[["SSPL Value"]].style.format(format_rupees),
                **stretch_width_kwargs(),
            )
        with k12_tab:
            st.bar_chart(monthly_values["K12 Value"], y_label="K12 Value (₹)")
            st.dataframe(
                monthly_values[["K12 Value"]].style.format(format_rupees),
                **stretch_width_kwargs(),
            )

with bom_failed_tab:
    st.subheader("BOM Failed Cases")
    if "result" not in st.session_state:
        st.info("Generate the Final Inventory to view BOM failed cases.")
    else:
        bom_failed = st.session_state.result["BOM Failed"]
        st.metric("Failed BOM Cases", f"{len(bom_failed):,}")
        if bom_failed.empty:
            st.success("No BOM failed cases found.")
        else:
            st.dataframe(bom_failed, hide_index=True, **stretch_width_kwargs())
            st.download_button(
                "Download BOM Failed Cases.csv",
                data=bom_failed.to_csv(index=False).encode("utf-8"),
                file_name="BOM Failed Cases.csv",
                mime="text/csv",
            )
