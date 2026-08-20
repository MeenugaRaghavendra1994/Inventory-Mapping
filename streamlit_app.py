from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st


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
    "Year",
    "Eduvate/Private",
    "Moving Type",
    "Sub Category",
    "New Grade",
    "Volume",
    "SSPL CP",
    "K12 CP",
}


def load_sources():
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

bom_tab, masters_tab = st.tabs(["BOM Report SAP", "Masters"])
with bom_tab:
    st.info("Edit existing rows or use Add rows at the bottom. Delete rows with the checkbox in the row menu.")
    edited_bom = st.data_editor(
        st.session_state.bom,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="bom_editor",
    )
    st.session_state.bom = edited_bom
    st.caption(f"{len(edited_bom):,} BOM rows")

with masters_tab:
    st.info("Edit existing rows or use Add rows at the bottom. Delete rows with the checkbox in the row menu.")
    edited_masters = st.data_editor(
        st.session_state.masters,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="masters_editor",
    )
    st.session_state.masters = edited_masters
    st.caption(f"{len(edited_masters):,} master rows")

button_col, status_col = st.columns([1, 3])
with button_col:
    if st.button("Save source Excel files", type="secondary"):
        try:
            save_sources(st.session_state.bom, st.session_state.masters)
            st.success("BOM and Masters saved.")
        except Exception as error:
            st.error(f"Could not save source files: {error}")

with status_col:
    st.write("Changes are kept in the current session until you save them or generate an output file.")

st.divider()
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
            use_container_width=True,
        )
