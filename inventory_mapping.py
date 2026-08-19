import pandas as pd
from pathlib import Path
import time

# ============================================================
# FILE PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
BOM_FILE = BASE_DIR / "BOM Report SAP.xlsx"
INVENTORY_FILE = BASE_DIR / "Inventory.xlsx"
MASTERS_FILE = BASE_DIR / "Masters.xlsx"
OUTPUT_FILE = BASE_DIR / "Final Inventory.xlsx"


# ============================================================
# START TIMER
# ============================================================

start_time = time.time()


# ============================================================
# READ FILES
# ============================================================

print("Reading files...")

if not BOM_FILE.exists():
    raise FileNotFoundError(
        f"BOM file not found: {BOM_FILE}\n"
        "Place 'BOM Report SAP.xlsx' in the same folder as inventory_mapping.py."
    )

if not INVENTORY_FILE.exists():
    raise FileNotFoundError(
        f"Inventory file not found: {INVENTORY_FILE}\n"
        "Place 'Inventory.xlsx' in the same folder as inventory_mapping.py."
    )

if not MASTERS_FILE.exists():
    raise FileNotFoundError(
        f"Masters file not found: {MASTERS_FILE}\n"
        "Place 'Masters.xlsx' in the same folder as inventory_mapping.py."
    )

bom = pd.read_excel(
    BOM_FILE,
    sheet_name="Sheet1",
    usecols=[
        "Material Code",
        "Component Code",
        "Component Description",
        "Component Quantity"
    ]
)

inventory = pd.read_excel(
    INVENTORY_FILE,
    sheet_name="SAPUI5 Export",
    usecols=[
        "Material",
        "Material Description",
        "Plant",
        "Unrestricted Stock",
        "Blocked Stock",
        "Storage Location"
    ]
)

masters_excel = pd.ExcelFile(MASTERS_FILE)
masters_sheet = "Masters"
if masters_sheet not in masters_excel.sheet_names:
    masters_sheet = masters_excel.sheet_names[0]
    print(
        f"Warning: 'Masters' sheet not found in Masters.xlsx. "
        f"Using first sheet '{masters_sheet}' instead."
    )
masters = pd.read_excel(MASTERS_FILE, sheet_name=masters_sheet)
masters_required = {
    "Material",
    "Year",
    "Eduvate/Private",
    "Moving Type",
    "Sub Category",
    "New Grade",
    "Volume",
    "SSPL CP",
    "K12 CP"
}
if not masters_required.issubset(masters.columns):
    missing = masters_required - set(masters.columns)
    raise ValueError(
        f"Masters file missing columns: {missing} "
        f"in sheet '{masters_sheet}' of Masters.xlsx."
    )

masters["Material"] = pd.to_numeric(
    masters["Material"], errors="coerce"
).astype("Int64")
masters = masters.drop_duplicates(subset=["Material"]).copy()


# ============================================================
# VALIDATE REQUIRED COLUMNS
# ============================================================

bom_required = {
    "Material Code",
    "Component Code",
    "Component Description",
    "Component Quantity"
}

inventory_required = {
    "Material",
    "Material Description",
    "Plant",
    "Unrestricted Stock"
}

if not bom_required.issubset(bom.columns):
    missing = bom_required - set(bom.columns)
    raise ValueError(f"BOM file missing columns: {missing}")

if not inventory_required.issubset(inventory.columns):
    missing = inventory_required - set(inventory.columns)
    raise ValueError(f"Inventory file missing columns: {missing}")


# ============================================================
# NORMALIZE DATA TYPES
# ============================================================

print("Preparing data...")

bom["Material Code"] = pd.to_numeric(
    bom["Material Code"], errors="coerce"
).astype("Int64")

bom["Component Code"] = pd.to_numeric(
    bom["Component Code"], errors="coerce"
).astype("Int64")

bom["Component Quantity"] = pd.to_numeric(
    bom["Component Quantity"], errors="coerce"
).fillna(0)

inventory["Material"] = pd.to_numeric(
    inventory["Material"], errors="coerce"
).astype("Int64")

inventory["Plant"] = pd.to_numeric(
    inventory["Plant"], errors="coerce"
).astype("Int64")

inventory["Unrestricted Stock"] = pd.to_numeric(
    inventory["Unrestricted Stock"], errors="coerce"
).fillna(0)

inventory["Blocked Stock"] = pd.to_numeric(
    inventory["Blocked Stock"], errors="coerce"
).fillna(0)

# Combine Unrestricted Stock and Blocked Stock
inventory["Unrestricted Stock"] = inventory["Unrestricted Stock"] + inventory["Blocked Stock"]


# ============================================================
# IDENTIFY 91 SERIES MATERIALS
# ============================================================

is_91 = inventory["Material"].astype("string").str.startswith("91")

normal_inventory = inventory.loc[
    ~is_91,
    [
        "Material",
        "Material Description",
        "Plant",
        "Storage Location",
        "Unrestricted Stock"
    ]
].copy()

kit_inventory = inventory.loc[
    is_91,
    [
        "Material",
        "Plant",
        "Storage Location",
        "Unrestricted Stock"
    ]
].copy()


print(f"Normal inventory rows : {len(normal_inventory):,}")
print(f"91-series inventory   : {len(kit_inventory):,}")
print(f"BOM rows              : {len(bom):,}")


# ============================================================
# STEP 1
# NORMAL MATERIALS
#
# These materials remain as they are.
# ============================================================

normal_inventory = normal_inventory.rename(
    columns={
        "Unrestricted Stock": "Final Quantity"
    }
)


# ============================================================
# STEP 2
# CONVERT 91 SERIES USING BOM
#
# 91 Material
#       ↓
# Search BOM Material Code
#       ↓
# Get Component Code
# Get Component Description
# Get Component Quantity
#       ↓
# Search Component Code in Inventory
#       ↓
# Unrestricted Stock
#       ↓
# Component Quantity × Unrestricted Stock
# ============================================================

print("Converting 91-series materials using BOM...")

converted = kit_inventory.merge(
    bom,
    left_on="Material",
    right_on="Material Code",
    how="left",
    sort=False
)


# ============================================================
# CALCULATE FINAL COMPONENT QUANTITY
# ============================================================

converted["Final Quantity"] = (
    converted["Component Quantity"].fillna(0)
    * converted["Unrestricted Stock"].fillna(0)
)


# ============================================================
# CAPTURE FAILED BOM MAPPINGS
# ============================================================

bom_failed = converted.loc[
    converted["Component Code"].isna()
].copy()

bom_failed = bom_failed[
    [
        "Material",
        "Plant",
        "Storage Location",
        "Unrestricted Stock"
    ]
].drop_duplicates().copy()

bom_failed["Reason"] = "Not found in BOM"


# ============================================================
# REMOVE UNMAPPED BOM RECORDS
# ============================================================

converted = converted.loc[
    converted["Component Code"].notna()
].copy()


# ============================================================
# CREATE FINAL COMPONENT INVENTORY
# ============================================================

converted_final = converted[
    [
        "Component Code",
        "Component Description",
        "Plant",
        "Storage Location",
        "Final Quantity"
    ]
].copy()

converted_final = converted_final.rename(
    columns={
        "Component Code": "Material",
        "Component Description": "Material Description"
    }
)


# ============================================================
# COMBINE NORMAL + CONVERTED INVENTORY
#
# If the same component already exists in Inventory,
# its original stock and converted 91-series stock
# will be added together.
# ============================================================

print("Creating final inventory...")

combined = pd.concat(
    [
        normal_inventory[
            [
                "Material",
                "Material Description",
                "Plant",
                "Storage Location",
                "Final Quantity"
            ]
        ],
        converted_final[
            [
                "Material",
                "Material Description",
                "Plant",
                "Storage Location",
                "Final Quantity"
            ]
        ]
    ],
    ignore_index=True
)


# ============================================================
# FINAL SUM
#
# Group by:
# Material
# Material Description
# Plant
# Storage Location
# ============================================================

final_inventory = (
    combined
    .groupby(
        [
            "Material",
            "Material Description",
            "Plant",
            "Storage Location"
        ],
        as_index=False,
        sort=False
    )["Final Quantity"]
    .sum()
)


# ============================================================
# RENAME FINAL COLUMN
# ============================================================

final_inventory = final_inventory.rename(
    columns={
        "Final Quantity": "Plant Summation Quantity"
    }
)

final_inventory = final_inventory.merge(
    masters[
        [
            "Material",
            "Year",
            "Eduvate/Private",
            "Moving Type",
            "Sub Category",
            "New Grade",
            "Volume",
            "SSPL CP",
            "K12 CP"
        ]
    ],
    on="Material",
    how="left",
    sort=False
)


# ============================================================
# CALCULATE SSPL VALUE AND K12 VALUE
# ============================================================

final_inventory["SSPL Value"] = (
    final_inventory["Plant Summation Quantity"] * final_inventory["SSPL CP"]
).infer_objects(copy=False).fillna(0)

final_inventory["K12 Value"] = (
    final_inventory["Plant Summation Quantity"] * final_inventory["K12 CP"]
).infer_objects(copy=False).fillna(0)


# ============================================================
# WORKING FILE / VALIDATION SHEET
# ============================================================

normal_validation = normal_inventory.copy()
normal_validation["Record Type"] = "Normal"
normal_validation["Source Material"] = normal_validation["Material"]
normal_validation["Source Description"] = normal_validation["Material Description"]
normal_validation["Component Code"] = pd.Series(
    [pd.NA] * len(normal_validation), dtype="Int64"
)
normal_validation["Component Description"] = pd.Series(
    [pd.NA] * len(normal_validation), dtype="string"
)
normal_validation["Component Quantity"] = pd.Series(
    [pd.NA] * len(normal_validation), dtype="Int64"
)
normal_validation["Source Unrestricted Stock"] = normal_validation["Final Quantity"]
normal_validation = normal_validation[
    [
        "Record Type",
        "Source Material",
        "Source Description",
        "Component Code",
        "Component Description",
        "Component Quantity",
        "Plant",
        "Source Unrestricted Stock",
        "Final Quantity"
    ]
]

converted_validation = converted.copy()
converted_validation["Record Type"] = "Converted"
converted_validation["Source Material"] = converted_validation["Material"]
converted_validation["Source Description"] = pd.Series(
    [pd.NA] * len(converted_validation), dtype="string"
)
converted_validation["Source Unrestricted Stock"] = converted_validation["Unrestricted Stock"]
converted_validation = converted_validation[
    [
        "Record Type",
        "Source Material",
        "Source Description",
        "Component Code",
        "Component Description",
        "Component Quantity",
        "Plant",
        "Source Unrestricted Stock",
        "Final Quantity"
    ]
]

working_file = pd.concat(
    [
        normal_validation.reindex(
            columns=[
                "Record Type",
                "Source Material",
                "Source Description",
                "Component Code",
                "Component Description",
                "Component Quantity",
                "Plant",
                "Source Unrestricted Stock",
                "Final Quantity"
            ]
        ),
        converted_validation.reindex(
            columns=[
                "Record Type",
                "Source Material",
                "Source Description",
                "Component Code",
                "Component Description",
                "Component Quantity",
                "Plant",
                "Source Unrestricted Stock",
                "Final Quantity"
            ]
        )
    ],
    ignore_index=True,
    sort=False
)

# Explicitly set dtypes for all-NA columns
working_file["Component Code"] = working_file["Component Code"].astype("Int64")
working_file["Component Description"] = working_file["Component Description"].astype("string")
working_file["Component Quantity"] = working_file["Component Quantity"].astype("Int64")

working_file = working_file.merge(
    masters[
        [
            "Material",
            "Year",
            "Eduvate/Private",
            "Moving Type",
            "Sub Category",
            "New Grade",
            "Volume",
            "SSPL CP",
            "K12 CP"
        ]
    ],
    left_on="Source Material",
    right_on="Material",
    how="left",
    sort=False
)

working_file = working_file.drop(columns=["Material"])


# ============================================================
# FINAL VALIDATION
# ============================================================

# Make sure no 91-series material remains
final_91 = final_inventory[
    final_inventory["Material"]
    .astype("string")
    .str.startswith("91", na=False)
]

if len(final_91) > 0:
    raise ValueError(
        "ERROR: 91-series materials are still present in Final Inventory."
    )


# ============================================================
# EXPORT
# ============================================================

print("Writing Final Inventory.xlsx with validation sheet...")

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    final_inventory.to_excel(
        writer,
        sheet_name="Final Inventory",
        index=False
    )

    working_file.to_excel(
        writer,
        sheet_name="Working File",
        index=False
    )

    if len(bom_failed) > 0:
        bom_failed.to_excel(
            writer,
            sheet_name="BOM Failed",
            index=False
        )


# ============================================================
# SUMMARY
# ============================================================

elapsed = time.time() - start_time

print()
print("=" * 60)
print("PROCESS COMPLETED")
print("=" * 60)

print(f"Final rows             : {len(final_inventory):,}")
print(f"91-series removed      : {len(kit_inventory):,}")
print(f"Final 91-series rows   : {len(final_91):,}")
print(f"BOM Failed rows        : {len(bom_failed):,}")
print(f"Output file             : {OUTPUT_FILE}")
print(f"Processing time         : {elapsed:.2f} seconds")
print("=" * 60)