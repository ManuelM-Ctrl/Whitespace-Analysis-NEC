#!/usr/bin/env python3
"""
migrate_reference.py — one-shot migration of SAP_Industry_Product_Matrix_Long.xlsx

Reads the existing file (which has a single 'Solution Area' GTM column),
maps each product to SAH L1/L2/L3/L4, and writes a new file with the
columns that ingest.py now expects.

Run from the project root:
    python3 migrate_reference.py
"""

import pandas as pd
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pathlib import Path

SRC = Path("reference-data/SAP_Industry_Product_Matrix_Long.xlsx")
DST = SRC  # overwrite in-place

# ---------------------------------------------------------------------------
# SAH mapping: product name (lowercase substring) → (L1, L2, L3, L4)
# L4 is blank when the best match is at L3.
# ---------------------------------------------------------------------------
PRODUCT_SAH = {
    # S4 — Finance
    "sap s/4hana cloud for professional services":  ("S4", "Finance, Q2C and Enterprise Mgmt", "Enterprise Management", "S/4HANA EM Cloud - Public"),
    "sap s/4hana defense and security":             ("S4", "Industry-specific Applications", "Public Services", "Defense & Security"),
    "sap s/4hana insurance for reinsurance":        ("S4", "Industry-specific Applications", "Financial Services", "Core Insurance"),
    "sap s/4hana manufacturing":                    ("S4", "Digital Supply Chain", "D2O Manufacture", "Manufacture - S4HANA"),
    "sap s/4hana for retail":                       ("S4", "Industry-specific Applications", "Consumer Industries", "Retail"),
    "sap project system":                           ("S4", "Finance, Q2C and Enterprise Mgmt", "Enterprise Management", "S/4HANA EM Cloud - Public"),
    "sap real estate management":                   ("S4", "Finance, Q2C and Enterprise Mgmt", "Finance", "Real Estate Management"),
    "sap cpq":                                      ("S4", "Finance, Q2C and Enterprise Mgmt", "Quote to Cash", "CPQ"),
    "sap global trade services":                    ("S4", "Finance, Q2C and Enterprise Mgmt", "GRC and Global Tax", "International Trade Management"),
    "sap billing and revenue innovation":           ("S4", "Finance, Q2C and Enterprise Mgmt", "Quote to Cash", "Billing"),
    "sap variant configuration and pricing":        ("S4", "Finance, Q2C and Enterprise Mgmt", "Quote to Cash", "CPQ"),
    "sap portfolio and project management":         ("S4", "Finance, Q2C and Enterprise Mgmt", "Enterprise Management", "S/4HANA EM Cloud - Public"),
    "sap for banking":                              ("S4", "Industry-specific Applications", "Financial Services", "Core Banking"),
    "sap for media":                                ("S4", "Industry-specific Applications", "Services Industries", "Media"),
    # S4 — Digital Supply Chain
    "sap integrated business planning":             ("S4", "Digital Supply Chain", "D2O Plan", "Planning & Forecasting"),
    "sap transportation management":                ("S4", "Digital Supply Chain", "D2O Deliver", "Transportation Management"),
    "sap extended warehouse management":            ("S4", "Digital Supply Chain", "D2O Deliver", "Warehouse Management"),
    "sap digital manufacturing":                    ("S4", "Digital Supply Chain", "D2O Manufacture", "Manufacturing Execution"),
    "sap enterprise asset management":              ("S4", "Digital Supply Chain", "D2O Operate", "Intelligent Asset Management"),
    "sap logistics business network":               ("ISBN", "Business Network", "Logistics Business Network", "Logistics Business Network"),
    "sap engineering control center":               ("S4", "Digital Supply Chain", "D2O Design", "Design - S4HANA"),
    "sap enterprise product development":           ("S4", "Digital Supply Chain", "D2O Design", "Product"),
    "sap recipe development":                       ("S4", "Digital Supply Chain", "D2O Design", "Product"),
    "sap assortment planning for retail":           ("S4", "Digital Supply Chain", "D2O Plan", "Planning & Forecasting"),
    "sap customer activity repository":             ("S4", "Digital Supply Chain", "D2O Plan", "Planning & Forecasting"),
    "sap trade promotion management":               ("CX", "Sales and Services", "Cloud for Customer", "Cloud for Customer"),
    "sap retail execution":                         ("CX", "Sales and Services", "Cloud for Customer", "Cloud for Customer"),
    "sap omnichannel promotion pricing":            ("S4", "Digital Supply Chain", "D2O Plan", "Planning & Forecasting"),
    "sap field service management":                 ("CX", "Sales and Services", "Cloud for Customer", "Cloud for Customer"),
    # S4 — Sustainability / GRC
    "sap product compliance":                       ("S4", "Finance, Q2C and Enterprise Mgmt", "GRC and Global Tax", "Enterprise Risk and Compliance"),
    "sap product footprint management":             ("S4", "Finance, Q2C and Enterprise Mgmt", "GRC and Global Tax", "Enterprise Risk and Compliance"),
    "sap responsible design and production":        ("S4", "Finance, Q2C and Enterprise Mgmt", "GRC and Global Tax", "Enterprise Risk and Compliance"),
    "sap sustainability control tower":             ("S4", "Finance, Q2C and Enterprise Mgmt", "GRC and Global Tax", "Enterprise Risk and Compliance"),
    "sap environment, health, and safety":          ("S4", "Finance, Q2C and Enterprise Mgmt", "GRC and Global Tax", "Enterprise Risk and Compliance"),
    # BTP
    "sap analytics cloud":                          ("BTP", "Planning and Analytics", "Analytics", "Analytics Public"),
    "sap business technology platform":             ("BTP", "Foundation/Appl. Dev. & Integration", "AppDev and Automation", "AppDev and Automation Public"),
    # CX
    "sap sales cloud":                              ("CX", "Sales and Services", "Cloud for Customer", "Cloud for Customer"),
    "sap service cloud":                            ("CX", "Sales and Services", "Cloud for Customer", "Cloud for Customer"),
    "sap commerce cloud":                           ("CX", "Commerce", "Commerce", "Commerce CCV2"),
    "sap emarsys customer engagement":              ("CX", "Marketing", "Emarsys", "Emarsys"),
    # ISBN
    "sap concur":                                   ("ISBN", "Travel and Expense", "Concur", "Concur - Expense"),
    "sap fieldglass":                               ("ISBN", "External Workforce", "Fieldglass Products", "Fieldglass - Core"),
    # Utilities-specific (S4 industry)
    "billable items for utilities":                 ("S4", "Industry-specific Applications", "Energy and Natural Resources", "Utilities"),
    "billing for utilities":                        ("S4", "Industry-specific Applications", "Energy and Natural Resources", "Utilities"),
    "utilities billing integration":                ("S4", "Industry-specific Applications", "Energy and Natural Resources", "Utilities"),
    "utilities budget billing plan":                ("S4", "Industry-specific Applications", "Energy and Natural Resources", "Utilities"),
    # Public Sector (S4 industry)
    "multichannel foundation for public sector":    ("S4", "Industry-specific Applications", "Public Services", "Public Sector"),
    "public sector controlling":                    ("S4", "Industry-specific Applications", "Public Services", "Public Sector"),
    "public sector finance":                        ("S4", "Industry-specific Applications", "Public Services", "Public Sector"),
    "public sector procurement":                    ("S4", "Industry-specific Applications", "Public Services", "Public Sector"),
}


def lookup(product_name: str):
    key = product_name.strip().lower()
    # exact match first
    if key in PRODUCT_SAH:
        return PRODUCT_SAH[key]
    # substring match — longest matching key wins
    best = None
    best_len = 0
    for k, v in PRODUCT_SAH.items():
        if k in key and len(k) > best_len:
            best, best_len = v, len(k)
    return best or ("", "", "", "")


def main():
    df = pd.read_excel(SRC, sheet_name="Product-Industry Matrix", engine="openpyxl")

    l1, l2, l3, l4 = [], [], [], []
    for product in df["Product"]:
        a, b, c, d = lookup(str(product) if pd.notna(product) else "")
        l1.append(a); l2.append(b); l3.append(c); l4.append(d)

    # Build new dataframe with the columns ingest.py expects
    out = pd.DataFrame({
        "Product":          df["Product"],
        "Solution Area L1": l1,
        "Solution Area L2": l2,
        "Solution Area L3": l3,
        "Solution Area L4": l4,
        "Industry":         df["Industry"],
        "Tag":              df["Tag"],
        "Category":         df["Category"],
        "Priority":         df["Priority"],
        "KG URI":           df.get("KG URI", pd.Series([""] * len(df))),
        "External URL":     df.get("External URL", pd.Series([""] * len(df))),
    })

    # Report unmapped
    unmapped = out[out["Solution Area L1"] == ""]["Product"].dropna().unique()
    if len(unmapped):
        print(f"WARNING: {len(unmapped)} products could not be mapped to SAH:")
        for p in sorted(unmapped):
            print(f"  - {p}")

    # Write with styling
    HEADER_FILL = PatternFill("solid", fgColor="1F3864")
    HEADER_FONT = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    ALT_FILL    = PatternFill("solid", fgColor="EEF2F8")
    WARN_FILL   = PatternFill("solid", fgColor="FFF2CC")
    BODY_FONT   = Font(name="Calibri", size=10)
    THIN        = Side(style="thin", color="CCCCCC")
    BORDER      = Border(bottom=THIN)

    GLOSSARY = [
        ("CM", "Core",   "Must-have", "Foundational product required for core end-to-end processes in this industry"),
        ("CC", "Core",   "Common",    "Broadly applicable; frequently selected in mature deployments"),
        ("CO", "Core",   "Optional",  "Cross-industry product relevant only in specific scenarios"),
        ("AM", "Add-on", "Must-have", "Add-on required for core processes in this industry"),
        ("AC", "Add-on", "Common",    "Add-on broadly applicable in mature deployments"),
        ("AO", "Add-on", "Optional",  "Add-on relevant only in specific scenarios"),
    ]

    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # Sheet 1: Product-Industry Matrix
    ws = wb.create_sheet("Product-Industry Matrix")
    cols = list(out.columns)
    ws.append(cols)
    for c in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT; cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 28

    tag_order = {"CM": 0, "AM": 1, "CC": 2, "AC": 3, "CO": 4, "AO": 5}
    rows_sorted = out.sort_values(
        by=["Industry", "Tag", "Solution Area L1", "Product"],
        key=lambda s: s.map(lambda v: tag_order.get(v, 99)) if s.name == "Tag" else s.fillna(""),
    )

    for i, (_, row) in enumerate(rows_sorted.iterrows(), start=2):
        ws.append([str(v) if pd.notna(v) else "" for v in row])
        is_unmapped = str(row.get("Solution Area L1", "")).strip() == ""
        fill = WARN_FILL if is_unmapped else (ALT_FILL if i % 2 == 0 else None)
        for c in range(1, len(cols) + 1):
            cell = ws.cell(row=i, column=c)
            cell.font = BODY_FONT; cell.border = BORDER
            if fill:
                cell.fill = fill

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        width = max((len(str(c.value or "")) for c in col), default=0)
        ws.column_dimensions[letter].width = min(max(width + 2, 10), 60)

    # Sheet 2: Glossary
    ws2 = wb.create_sheet("Glossary")
    ws2.append(["Tag", "Category", "Priority", "Description"])
    for c in range(1, 5):
        cell = ws2.cell(row=1, column=c)
        cell.font = HEADER_FONT; cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 28
    for i, row in enumerate(GLOSSARY, start=2):
        ws2.append(list(row))
        for c in range(1, 5):
            cell = ws2.cell(row=i, column=c)
            cell.font = BODY_FONT; cell.border = BORDER
            if i % 2 == 0:
                cell.fill = ALT_FILL
    for col in ws2.columns:
        letter = get_column_letter(col[0].column)
        width = max((len(str(c.value or "")) for c in col), default=0)
        ws2.column_dimensions[letter].width = min(max(width + 2, 10), 80)

    wb.save(DST)
    print(f"Written: {DST}  ({len(out)} rows, {out['Industry'].nunique()} industries)")


if __name__ == "__main__":
    main()
