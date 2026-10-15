import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd
if tuple(int(x) for x in pd.__version__.split(".")[:2]) < (2, 1):
    sys.exit("pandas >= 2.1.0 required")

import validate
from validate import ValidationError, ValidationReport
from utils import strip_code, EUR_TO_USD, CODE_RE

# Short abbreviations for SAH L1 names (must match canonical L1 names in the SAH Excel file)
SAH_L1_ABBREV = {
    "BAIP - Data & AI":             "DAI",
    "BAIP - Technology Foundation": "BTP",
    "Cloud ERP Private":            "Cloud ERP",
    "Customer Experience":          "CX",
    "Finance and Spend Management": "FSM",
    "Human Capital Management":     "HCM",
    "Supply Chain Management":      "SCM",
    "Business Transformation Management": "BTM",
    "Other":                        "Other",
}

INDUSTRY_CROSSWALK = {
    "Aerospace and Defense":                    "Aerospace & defense",
    "Agribusiness":                             "Agribusiness",
    "Automotive":                               "Automotive",
    "Banking":                                  "Financial Services",
    "Chemicals":                                "Chemicals",
    "Consumer Products":                        "Consumer products",
    "Defense and Security":                     "Defense & security",
    "Engineering, Construction and Operation":  "Construction & real estate",
    "Engineering, Construction, and O":         "Construction & real estate",
    "Healthcare":                               "Life sciences & healthcare",
    "High Tech":                                "High tech",
    "Higher Education and Research":            "Education & research",
    "Industrial Manufacturing":                 "Industrial manufacturing",
    "Insurance":                                "Financial Services",
    "Life Sciences":                            "Life sciences & healthcare",
    "Media":                                    "Media, sports & entertainment",
    "Mill Products and Mining":                 "Mill products",
    "Oil, Gas and Energy":                      "Oil, gas & energy",
    "Oil, Gas, and Energy":                     "Oil, gas & energy",
    "Professional Services":                    "Professional services",
    "Retail":                                   "Retail",
    "Sports and Entertainment":                 "Media, sports & entertainment",
    "Telecommunications":                       "Telecommunications",
    "Travel and Transportation":                "Travel & transportation",
    "Utilities":                                "Utilities",
    "Wholesale Distribution":                   "Wholesale distribution",
}

# Maps stale SAH codes used in migrate_reference.py to canonical L1/L2 names from SAH-Hierarchy.md.
# Keys are (old_l1_prefix, old_l2_prefix); values are (canonical_l1, canonical_l2).
# Matching is done by checking whether the stored l1/l2 start with the key prefix.
LEGACY_SAH_NORM = {
    ("BTP", "Planning and Analytics"):       ("Business Technology Platform", "BTP Other"),
    ("BTP", "Foundation"):                   ("Business Technology Platform", "SAP Integration Suite"),
    ("BTP", "SAP Build"):                    ("Business Technology Platform", "SAP Build"),
    ("BTP", "CIAM"):                         ("Business Technology Platform", "CIAM (CDC)"),
    ("BTP", "Enterprise"):                   ("Business Technology Platform", "Enterprise Agreements"),
    ("BTP",):                                ("Business Technology Platform", "BTP Other"),
    ("CX", "Sales and Serv"):                ("Customer Experience", "Sales and Service"),
    ("CX", "Commerce"):                      ("Customer Experience", "Commerce"),
    ("CX", "Marketing"):                     ("Customer Experience", "Marketing"),
    ("CX", "Sales Performance"):             ("Customer Experience", "Sales Performance Management"),
    ("CX",):                                 ("Customer Experience", "Sales and Service"),
    ("S4", "Finance, Q2C"):                  ("Finance and Spend Management", "Accounting & Financial Close"),
    ("S4", "Digital Supply Chain"):          ("Supply Chain Management", "SCM Private"),
    ("S4", "Industry-specific"):             ("Cloud ERP Private", "Cloud ERP Private"),
    ("S4",):                                 ("Cloud ERP Private", "Cloud ERP Private"),
    ("ISBN", "Travel and Expense"):          ("Finance and Spend Management", "Travel and Expense"),
    ("ISBN", "External Workforce"):          ("Finance and Spend Management", "Fieldglass"),
    ("ISBN", "Business Network"):            ("Supply Chain Management", "Business Network"),
    ("ISBN",):                               ("Finance and Spend Management", "Finance Private"),
}

TAG_SORT_ORDER = {"CM": 0, "AM": 1, "CC": 2, "AC": 3, "CO": 4, "AO": 5}

RISE_CODES = {"LPR245", "LPR943", "LPR1001", "LPR1052"}

# Maps new TAO "Sales Priority" string values to the numeric-prefix format the dashboard expects.
SALES_PRIORITY_MAP = {
    "Very High": "1 Very High",
    "High":      "2 High",
    "Medium":    "3 Medium",
    "Low":       "4 Low",
    "Very Low":  "5 Very Low",
}



def parse_sah_xlsx(path):
    """Parse SAH hierarchy from an Excel file (Products sheet).

    Reads 'SolAr 2026' (L1) and 'Sub-Solution Area 2026' (L2) columns.
    Returns (sah_hierarchy, sah_l1_names) in the same format as parse_sah_md().
    """
    df = pd.read_excel(path, sheet_name="Products", engine="openpyxl", dtype=str)
    df = df[["SolAr 2026", "Sub-Solution Area 2026"]].dropna(subset=["SolAr 2026", "Sub-Solution Area 2026"])
    df = df.rename(columns={"SolAr 2026": "l1", "Sub-Solution Area 2026": "l2"})
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    df = df[df["l1"].astype(bool) & df["l2"].astype(bool)]
    hierarchy = {}
    l1_names = []
    for _, row in df.drop_duplicates().iterrows():
        l1, l2 = row["l1"], row["l2"]
        if l1 not in hierarchy:
            hierarchy[l1] = {"label": l1, "l2": {}}
            l1_names.append(l1)
        l2_map = hierarchy[l1]["l2"]
        if l2 not in l2_map:
            l2_map[l2] = {"label": l2, "l4": {}}
    return hierarchy, l1_names


def build_product_name_map(path):
    """Return {product_key: external_product_name} from the Products sheet.

    AM stores products as "Display Name (LPRxxx)"; the key is extracted from
    the parenthetical code and looked up here to get the external-facing name.
    """
    df = pd.read_excel(path, sheet_name="Products", engine="openpyxl", dtype=str,
                       usecols=["Product Key", "External Product Name"])
    result = {}
    for _, row in df.iterrows():
        key = row.get("Product Key")
        name = row.get("External Product Name")
        if isinstance(key, str) and key.strip() and isinstance(name, str) and name.strip():
            result[key.strip()] = name.strip()
    return result


def parse_code(label):
    if not isinstance(label, str):
        return (label, None)
    m = CODE_RE.match(label.strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else (label.strip(), None)


def load_am(path):
    df = pd.read_csv(path, encoding="utf-8-sig", header=1, dtype=str)
    df = df[df["Planning Entity ID"].notna()]
    df = df[df["Planning Entity ID"] != "(No Value)"]
    # AM pads IDs with leading zeros; strip them to match IAA/TAO/ADRM format
    df["Planning Entity ID"] = df["Planning Entity ID"].str.strip().str.lstrip("0")
    return df


def load_iaa(path):
    df = pd.read_csv(path, encoding="utf-8-sig", header=1, dtype=str)
    df.columns = [c.lstrip("﻿") for c in df.columns]
    df = df[df["Sales Group: Current"].notna()]
    # Exclude the SHELL sales office (not a real territory)
    if "Sales Office: Current" in df.columns:
        df = df[df["Sales Office: Current"].str.strip() != "SL-MW-MMN-SHELL"]
    df["Planning Entity ID"] = df["Planning Entity ID"].str.strip().str.lstrip("0")
    if "SAP Top Parent CRM ID" in df.columns:
        df["SAP Top Parent CRM ID"] = df["SAP Top Parent CRM ID"].str.strip().str.lstrip("0")
    # Deduplicate: keep first occurrence per account; IAA can contain duplicate rows
    # for the same Planning Entity ID when accounts span multiple territories.
    df = df.drop_duplicates(subset="Planning Entity ID", keep="first")
    return df


def load_tao(paths):
    if isinstance(paths, str):
        paths = [paths]
    frames = []
    for p in paths:
        # New TAO format uses a two-row header: row 0 holds measure column names
        # (CLOUD_EXIT_ACV_EUR, etc.), row 1 holds dimension column names (Account ID, etc.).
        # Combine them: take row-1 value where non-empty, else row-0 value.
        raw = pd.read_csv(p, header=None, nrows=2, encoding="utf-8-sig")
        cols = []
        for i in range(len(raw.columns)):
            v1 = str(raw.iloc[1, i]).strip()
            v0 = str(raw.iloc[0, i]).strip()
            cols.append(v1 if v1 and v1 != "nan" else v0)
        df = pd.read_csv(p, header=None, skiprows=2, names=cols, encoding="utf-8-sig")
        df["Planning Entity ID"] = df["Account ID"].astype(str).str.strip()
        if "Sub Solution Area" in df.columns:
            df = df[df["Sub Solution Area"].notna()].copy()
        df["Solution Area"] = df["Solution Area"].str.strip()
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_adrm(path):
    df = pd.read_csv(path, encoding="utf-8-sig", header=1, dtype=str)
    df.columns = [c.lstrip("﻿") for c in df.columns]
    # "Total @ FC" label lives in the skipped row 0; the data column arrives as "Unnamed: N".
    # Find it by label from the header row rather than assuming it's the last unnamed column.
    if "Total @ FC" not in df.columns:
        hdr = pd.read_csv(path, encoding="utf-8-sig", header=None, nrows=1).iloc[0]
        fc_indices = [i for i, v in enumerate(hdr) if str(v).strip() == "Total @ FC"]
        if fc_indices:
            col_name = df.columns[fc_indices[0]]
        else:
            unnamed_cols = [c for c in df.columns if c.startswith("Unnamed:")]
            assert unnamed_cols, "No unnamed columns found in ADRM file — check export format"
            col_name = unnamed_cols[-1]
        df = df.rename(columns={col_name: "Total @ FC"})
        assert df["Total @ FC"].notna().any(), f"ADRM pipeline total column '{col_name}' is empty — check column position"
    df["Planning Entity ID"] = df["Planning Entity ID"].str.strip().str.lstrip("0")
    df["Total @ FC"] = pd.to_numeric(df["Total @ FC"], errors="coerce").fillna(0)
    # Convert Euros → KUSD (divide by 1000 for K, then multiply by exchange rate)
    df["pipeline_kusd"] = df["Total @ FC"] / 1000.0 * EUR_TO_USD
    grouped = (
        df.groupby(["Planning Entity ID", "Solution Area L2"], as_index=False)["pipeline_kusd"]
        .sum()
    )
    return grouped


def load_spi(path):
    df = pd.read_csv(path, encoding="utf-8-sig", header=1, dtype=str)
    df.columns = [c.lstrip("﻿") for c in df.columns]
    # "Exp. Pipeline" label lives in the skipped row 0; the data column arrives as "Unnamed: N".
    # Find it by label from the header row rather than assuming it's the last unnamed column.
    if "Exp. Pipeline" not in df.columns:
        hdr = pd.read_csv(path, encoding="utf-8-sig", header=None, nrows=1).iloc[0]
        ep_indices = [i for i, v in enumerate(hdr) if str(v).strip() == "Exp. Pipeline"]
        if ep_indices:
            col_name = df.columns[ep_indices[0]]
        else:
            unnamed_cols = [c for c in df.columns if c.startswith("Unnamed:")]
            assert unnamed_cols, "No unnamed columns found in SPI file — check export format"
            col_name = unnamed_cols[-1]
        df = df.rename(columns={col_name: "Exp. Pipeline"})
        assert df["Exp. Pipeline"].notna().any(), f"SPI pipeline column '{col_name}' is empty — check column position"
    df = df[df["Acc Planning Entity ID"].str.strip() != "(No Value)"]
    df["Planning Entity ID"] = df["Acc Planning Entity ID"].str.strip().str.lstrip("0")
    df["Idea Solution Area L2"] = df["Idea Solution Area L2"].str.strip()
    df["spi_kusd"] = pd.to_numeric(df["Exp. Pipeline"], errors="coerce").fillna(0)
    return df.groupby(["Planning Entity ID", "Idea Solution Area L2"], as_index=False)["spi_kusd"].sum()


def build_spi_index(spi, sah_hierarchy):
    l2_to_l1 = build_l2_to_l1(sah_hierarchy)
    l1_labels = {node["label"] for node in sah_hierarchy.values()}
    index = {}
    for _, row in spi.iterrows():
        acct = str(row["Planning Entity ID"]).strip()
        sa_raw = strip_code(str(row.get("Idea Solution Area L2", "")).strip())
        l1_name = l2_to_l1.get(sa_raw)
        if not l1_name:
            l1_name = sa_raw if sa_raw in l1_labels else None
        if not l1_name:
            continue
        acct_dict = index.setdefault(acct, {})
        acct_dict[l1_name] = round(acct_dict.get(l1_name, 0.0) + float(row["spi_kusd"]), 3)
    return index


def _normalize_ref_sah(l1, l2):
    """Map stale SAH codes from migrate_reference.py to canonical L1/L2 names."""
    if not isinstance(l1, str):
        return l1, l2
    l1 = l1.strip()
    l2 = l2.strip() if isinstance(l2, str) else ""
    # Try progressively shorter key tuples: (l1, l2_prefix) then (l1,)
    for prefix_len in range(max(1, len(l2)), 0, -1):
        key = (l1, l2[:prefix_len])
        if key in LEGACY_SAH_NORM:
            return LEGACY_SAH_NORM[key]
    # Fallback: match on l1 alone
    key = (l1,)
    if key in LEGACY_SAH_NORM:
        return LEGACY_SAH_NORM[key]
    return l1, l2


def load_reference_raw(path):
    """Return the raw Reference Solutions DataFrame (used for I-5 validation)."""
    return pd.read_excel(path, sheet_name="Reference Solutions", engine="openpyxl")


def load_reference(path):
    df = pd.read_excel(path, sheet_name="Reference Solutions", engine="openpyxl")
    ref = {}
    for _, row in df.iterrows():
        industry = row.get("Industry")
        if not isinstance(industry, str):
            continue
        raw_l1 = row.get("Solution Area L1")
        raw_l2 = row.get("Solution Area L2")
        norm_l1, norm_l2 = _normalize_ref_sah(raw_l1, raw_l2)
        sah_l4 = row.get("Solution Area L4")
        ext_name = row.get("Product")
        entry = {
            "product":           ext_name if isinstance(ext_name, str) and ext_name.strip() else (sah_l4 if isinstance(sah_l4, str) and sah_l4.strip() else None),
            "sah_l1":            norm_l1,
            "sah_l2":            norm_l2,
            "sah_l4":            sah_l4,
            "tag":               row.get("Tag"),
            "category":          row.get("Category"),
            "priority":          row.get("Priority"),
            "kg_uri":            None,
            "external_url":      None,
        }
        ref.setdefault(industry, []).append(entry)
    for industry in ref:
        ref[industry].sort(key=lambda e: TAG_SORT_ORDER.get(e["tag"], 99))
        # Deduplicate by external product name, keeping first occurrence (highest-priority tag after sort)
        seen, deduped = set(), []
        for e in ref[industry]:
            key = e["product"]
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        ref[industry] = deduped
    return ref


def validate_am_against_sah(am, sah_l1_names, sah_hierarchy):
    """Warn if AM data contains L1/L2 names not present in the canonical SAH hierarchy."""
    canonical_l1 = set(sah_l1_names)
    canonical_l2 = {
        l2_node["label"]
        for l1_node in sah_hierarchy.values()
        for l2_node in l1_node.get("l2", {}).values()
    }
    unknown_l1, unknown_l2 = set(), set()
    for _, row in am.iterrows():
        l1 = strip_code(row.get("Solution Area Level 1", ""))
        l2 = strip_code(row.get("Solution Area Level 2", ""))
        if l1 and l1 not in canonical_l1:
            unknown_l1.add(l1)
        if l2 and l2 not in canonical_l2:
            unknown_l2.add(l2)
    for name in sorted(unknown_l1):
        print(f"  WARNING: AM L1 not in SAH-Hierarchy.md: {name!r}")
    for name in sorted(unknown_l2):
        print(f"  WARNING: AM L2 not in SAH-Hierarchy.md: {name!r}")


def build_coverage(am, sah_l1_names, product_name_map=None):
    coverage = {}  # {account_id: {l1_name: {live_project, any_status, products, l2}}}
    rise_accounts = set()

    for _, row in am.iterrows():
        acct = row["Planning Entity ID"]
        l1_name = strip_code(row.get("Solution Area Level 1", ""))
        l2_name = strip_code(row.get("Solution Area Level 2", ""))
        status = row.get("Max / Highest Adoption State", "")
        product = row.get("Logical Product", "")

        if not l1_name:
            continue

        acct_cov = coverage.setdefault(acct, {})
        cell = acct_cov.setdefault(l1_name, {"live_project": False, "any_status": False, "products": [], "l2": {}})

        status_lc = status.strip().lower() if isinstance(status, str) else ""
        if status_lc in ("live", "project"):
            cell["live_project"] = True
        if status_lc in ("live", "project", "shelfware"):
            cell["any_status"] = True
        if isinstance(product, str) and product.strip():
            # Resolve to external product name via the code in parens, e.g. "SAP ERP (LPR246)"
            display = product.strip()
            _, prod_code = parse_code(display)
            if prod_code and prod_code in RISE_CODES:
                rise_accounts.add(acct)
            if product_name_map:
                if prod_code and prod_code in product_name_map:
                    display = product_name_map[prod_code]
            if display not in cell["products"]:
                cell["products"].append(display)

        # Track per-L2 status and LPR count
        if l2_name:
            l2e = cell["l2"].setdefault(l2_name, {"live": False, "project": False, "shelfware": False, "lpr_cnt": 0})
            if status_lc == "live":
                l2e["live"] = True
            elif status_lc == "project":
                l2e["project"] = True
            elif status_lc == "shelfware":
                l2e["shelfware"] = True
            l2e["lpr_cnt"] += 1

            # Track per-L3 status
            l3_name = strip_code(row.get("Solution Area Level 3", ""))
            if l3_name:
                l3e = l2e.setdefault("l3", {}).setdefault(l3_name, {"live": False, "project": False, "shelfware": False})
                if status_lc == "live":
                    l3e["live"] = True
                elif status_lc == "project":
                    l3e["project"] = True
                elif status_lc == "shelfware":
                    l3e["shelfware"] = True

    # fill in zeros for L1s not present for this account
    for acct in coverage:
        for l1 in sah_l1_names:
            coverage[acct].setdefault(l1, {"live_project": False, "any_status": False, "products": [], "l2": {}})

    return coverage, rise_accounts


def build_l3_hierarchy(am):
    """Return {l1_name → {l2_name → [l3_names ordered by first appearance]}} from AM data."""
    hierarchy = {}
    seen = {}  # (l1, l2, l3) → True, for dedup while preserving order
    for _, row in am.iterrows():
        l1 = strip_code(row.get("Solution Area Level 1", ""))
        l2 = strip_code(row.get("Solution Area Level 2", ""))
        l3 = strip_code(row.get("Solution Area Level 3", ""))
        if not (l1 and l2 and l3):
            continue
        key = (l1, l2, l3)
        if key not in seen:
            seen[key] = True
            hierarchy.setdefault(l1, {}).setdefault(l2, []).append(l3)
    return hierarchy


def build_tao_index(tao):
    # account-level fields (first row per account)
    acct_fields = {}
    # per-account × L1 × L2 fields (raw L2 accumulator)
    tao_l2_raw = {}

    has_l2 = "Sub Solution Area" in tao.columns

    for _, row in tao.iterrows():
        acct = str(row["Planning Entity ID"]).strip()
        sa   = str(row.get("Solution Area", "")).strip()
        l2   = str(row.get("Sub Solution Area", "")).strip() if has_l2 else ""

        if acct not in acct_fields:
            acct_fields[acct] = {
                "industry":          row.get("Industry"),
                "archetype":         row.get("Archetype"),
                "revenue_band":      row.get("Revenue Band"),
                "iac":               row.get("IAC"),
                "segment":           row.get("Segment"),
                "rbc":               row.get("RBC"),
                "num_solutions":     row.get("NUM_SOLUTIONS"),
                "num_solutions_band":row.get("NUM_SOLUTIONS_BAND"),
            }

        gap_eur      = row.get("GAP_TO_ESTIMATED_WALLET")
        wallet_eur   = row.get("ESTIMATED_WALLET_EUR")
        acv_eur      = row.get("CLOUD_EXIT_ACV_EUR")
        acv_risk_eur = row.get("ACV_AT_RISK_EUR")
        cy_eur       = row.get("CY_PIPELINE")
        cy1_eur      = row.get("CY_1_PIPELINE")
        gap_kusd      = round(float(gap_eur)      * EUR_TO_USD, 2) if pd.notna(gap_eur)      else None
        wallet_kusd   = round(float(wallet_eur)   * EUR_TO_USD, 2) if pd.notna(wallet_eur)   else None
        acv_kusd      = round(float(acv_eur)      * EUR_TO_USD, 2) if pd.notna(acv_eur)      else None
        acv_risk_kusd = round(float(acv_risk_eur) * EUR_TO_USD, 2) if pd.notna(acv_risk_eur) else None
        cy_kusd       = round(float(cy_eur)       * EUR_TO_USD, 2) if pd.notna(cy_eur)       else None
        cy1_kusd      = round(float(cy1_eur)      * EUR_TO_USD, 2) if pd.notna(cy1_eur)      else None

        entry = {
            "gap_kusd":              gap_kusd,
            "estimated_wallet_kusd": wallet_kusd,
            "priority_score":        SALES_PRIORITY_MAP.get(str(row.get("Sales Priority") or "").strip(), row.get("Sales Priority")),
            "strategy":              row.get("Strategy"),
            "historical_pipeline":   None,
            "acv_kusd":              acv_kusd,
            "acv_at_risk_kusd":      acv_risk_kusd,
            "cy_pipeline_kusd":      cy_kusd,
            "cy1_pipeline_kusd":     cy1_kusd,
        }

        l1_map = tao_l2_raw.setdefault(acct, {}).setdefault(sa, {})
        if l2 in l1_map:
            existing = l1_map[l2]
            for fld in ('gap_kusd', 'estimated_wallet_kusd', 'acv_kusd', 'acv_at_risk_kusd', 'cy_pipeline_kusd', 'cy1_pipeline_kusd'):
                if entry[fld] is not None:
                    existing[fld] = (existing[fld] or 0) + entry[fld]
        else:
            l1_map[l2] = entry

    # Roll L2 up to L1: sum gap/wallet; take representative meta from highest-gap L2
    tao_l1 = {}
    tao_l2 = {}   # {acct: {l1: {l2: {gap_kusd, estimated_wallet_kusd}}}}
    for acct, l1_map in tao_l2_raw.items():
        for l1, l2_map in l1_map.items():
            total_gap      = sum(e["gap_kusd"]              for e in l2_map.values() if e["gap_kusd"]              is not None)
            total_wallet   = sum(e["estimated_wallet_kusd"] for e in l2_map.values() if e["estimated_wallet_kusd"] is not None)
            total_acv      = sum(e["acv_kusd"]              for e in l2_map.values() if e["acv_kusd"]              is not None)
            total_acv_risk = sum(e["acv_at_risk_kusd"]      for e in l2_map.values() if e["acv_at_risk_kusd"]      is not None)
            total_cy       = sum(e["cy_pipeline_kusd"]      for e in l2_map.values() if e["cy_pipeline_kusd"]      is not None)
            total_cy1      = sum(e["cy1_pipeline_kusd"]     for e in l2_map.values() if e["cy1_pipeline_kusd"]     is not None)
            # Representative row: highest-gap L2 (or first if all zero)
            rep = max(l2_map.values(), key=lambda e: e["gap_kusd"] or 0)
            tao_l1.setdefault(acct, {})[l1] = {
                "gap_kusd":              round(total_gap, 2),
                "estimated_wallet_kusd": round(total_wallet, 2),
                "priority_score":        rep["priority_score"],
                "strategy":              rep["strategy"],
                "historical_pipeline":   None,
                "acv_kusd":              round(total_acv, 2),
                "acv_at_risk_kusd":      round(total_acv_risk, 2),
                "cy_pipeline_kusd":      round(total_cy, 2),
                "cy1_pipeline_kusd":     round(total_cy1, 2),
            }
            tao_l2.setdefault(acct, {})[l1] = {
                l2: {"gap_kusd": e["gap_kusd"], "estimated_wallet_kusd": e["estimated_wallet_kusd"]}
                for l2, e in l2_map.items() if l2
            }

    return acct_fields, tao_l1, tao_l2


def build_l2_to_l1(sah_hierarchy):
    """Return {l2_name: l1_name} using stripped (no-code) labels from the SAH hierarchy."""
    mapping = {}
    for l1_code, l1_node in sah_hierarchy.items():
        l1_name = l1_node["label"]
        for l2_code, l2_node in l1_node.get("l2", {}).items():
            mapping[l2_node["label"]] = l1_name
    return mapping


def build_pipeline_index(adrm, sah_hierarchy):
    l2_to_l1 = build_l2_to_l1(sah_hierarchy)
    l1_labels = {node["label"] for node in sah_hierarchy.values()}
    pipeline = {}  # {account_id: {l1_name: kusd}}
    for _, row in adrm.iterrows():
        acct = str(row["Planning Entity ID"]).strip()
        sa_l2_raw = str(row.get("Solution Area L2", "")).strip()
        l2_name = strip_code(sa_l2_raw)
        l1_name = l2_to_l1.get(l2_name)
        if not l1_name:
            l1_name = l2_name if l2_name in l1_labels else None
        if not l1_name:
            continue
        acct_dict = pipeline.setdefault(acct, {})
        acct_dict[l1_name] = round(acct_dict.get(l1_name, 0.0) + float(row["pipeline_kusd"]), 3)
    return pipeline


def _geo_l3(country_raw):
    """Harmonize Country → GEO-Level 3 bucket for LAC files."""
    c = str(country_raw or "").strip().upper()
    if c == "MEXICO":
        return "MEXICO"
    if c in ("BRAZIL", "BRASIL"):
        return "BRAZIL"
    if c:
        return "MCLAC"
    return None


def _segment_from_iac(iac_raw, rbc_raw=None):
    """Derive Segment from IAC value per spec 2026-09-16 §2.1."""
    v = str(iac_raw or "").strip()
    if v in ("C-Digital", "C-Field"):
        return "Corporate"
    if v in ("E-High Touch", "E-SCP"):
        return "Enterprise"
    if v == "Partner-Driven":
        return "Partner Driven"
    return "Null"


def main():
    parser = argparse.ArgumentParser(description="Ingest source files and produce data.json.")
    parser.add_argument("--am",    required=True, help="Adoption Monitor CSV")
    parser.add_argument("--am-tp", default=None, help="Top-parent Adoption Monitor CSV (optional)")
    parser.add_argument("--iaa",   required=True, help="IAA CSV")
    parser.add_argument("--tao",   required=True, nargs="+", help="TAO CSV file(s)")
    parser.add_argument("--adrm",  required=True, help="ADRM CSV")
    parser.add_argument("--spi",   default=None, help="SPI planned pipeline CSV (optional)")
    parser.add_argument("--ref",  required=True, help="Reference Excel")
    parser.add_argument("--sah",  required=True, help="SAH hierarchy Excel (Copy of Solution Areas and Logical Products...xlsx)")
    parser.add_argument("--out",  required=True, help="Output JSON path")
    parser.add_argument("--snapshot-date", default=None, help="Source data snapshot date (YYYY-MM-DD); shown in dashboard header")
    args = parser.parse_args()

    print("Loading SAH hierarchy from Excel...")
    sah_hierarchy, sah_l1_names = parse_sah_xlsx(args.sah)
    print("Loading product name map...")
    product_name_map = build_product_name_map(args.sah)

    print("Loading AM...")
    am = load_am(args.am)
    print("Loading IAA...")
    iaa = load_iaa(args.iaa)
    is_lac = os.path.basename(args.iaa).startswith("LAC_MU")
    print("Loading TAO...")
    tao = load_tao(args.tao)
    # Keep a raw copy of the TAO DataFrame for B-7 currency spot-check (before any transformations)
    tao_raw = tao.copy()
    print("Loading ADRM...")
    adrm = load_adrm(args.adrm)
    if args.spi:
        print("Loading SPI...")
        spi = load_spi(args.spi)
    else:
        spi = None
    print("Loading Reference...")
    reference = load_reference(args.ref)
    ref_df_raw = load_reference_raw(args.ref)

    # ------------------------------------------------------------------
    # Layer 1: Input preflight (I-1 … I-8)
    # ------------------------------------------------------------------
    print("\nValidation — Layer 1: Input preflight")
    report = ValidationReport()
    # load_adrm already grouped; reconstruct raw ADRM for column checks
    adrm_raw = pd.read_csv(args.adrm, encoding="utf-8-sig", header=1, dtype=str)
    adrm_raw.columns = [c.lstrip("﻿") for c in adrm_raw.columns]
    if "Total @ FC" not in adrm_raw.columns:
        unnamed_cols = [c for c in adrm_raw.columns if c.startswith("Unnamed:")]
        if unnamed_cols:
            adrm_raw = adrm_raw.rename(columns={unnamed_cols[-1]: "Total @ FC"})
    try:
        validate.check_input_preflight(am, iaa, tao_raw, adrm_raw, ref_df_raw, report)
    except ValidationError as exc:
        print(f"\nIngest aborted due to hard validation failure: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Validating AM against SAH hierarchy...")
    validate_am_against_sah(am, sah_l1_names, sah_hierarchy)

    print("Building coverage index...")
    coverage, rise_accounts = build_coverage(am, sah_l1_names, product_name_map)

    print("Building L3 hierarchy...")
    sah_l3_per_l2_dict = build_l3_hierarchy(am)

    print("Building TAO index...")
    tao_acct_fields, tao_l1_index, tao_l2_index = build_tao_index(tao)

    print("Building pipeline index...")
    pipeline_index = build_pipeline_index(adrm, sah_hierarchy)

    print("Building SPI index...")
    spi_index = build_spi_index(spi, sah_hierarchy) if spi is not None else {}

    # Determine MU from IAA (first non-null value)
    mu = iaa["Market Unit"].dropna().iloc[0] if "Market Unit" in iaa.columns and len(iaa) else "Unknown"

    print("Assembling accounts...")
    sic_map = (
        am.drop_duplicates("Planning Entity ID")
        .set_index("Planning Entity ID")["Standard Industry Code (Key + Text)"]
        .to_dict()
    )
    accounts_data = []

    for _, iaa_row in iaa.iterrows():
        acct_id = str(iaa_row["Planning Entity ID"]).strip()
        acct_cov = coverage.get(acct_id, {l1: {"live_project": False, "any_status": False, "products": []} for l1 in sah_l1_names})

        # is_prospect: no live/project coverage in any L1
        has_any_coverage = any(acct_cov.get(l1, {}).get("live_project") for l1 in sah_l1_names)
        is_prospect = not has_any_coverage

        # TAO account-level fields (gap/wallet/pipeline/strategy kept from TAO)
        tao_fields = tao_acct_fields.get(acct_id, {})

        # IAA-sourced filter fields
        iaa_industry_raw = str(iaa_row.get("Industry") or "").strip()
        iaa_iac_raw      = str(iaa_row.get("IAC (Engagement Model): Current") or "").strip() or None
        industry_bucket  = INDUSTRY_CROSSWALK.get(iaa_industry_raw, None) if iaa_industry_raw else None

        # Applicable products
        applicable_products = reference.get(industry_bucket, []) if industry_bucket else []

        # TAO per-L1 and per-L2
        tao_per_l1 = tao_l1_index.get(acct_id, {})
        tao_per_l2 = tao_l2_index.get(acct_id, {})

        # Pipeline per-L1
        pipeline_per_l1 = pipeline_index.get(acct_id, {})
        spi_per_l1 = spi_index.get(acct_id, {})

        # Whitespace classification (pre-score placeholder)
        opportunity = {}
        for l1 in sah_l1_names:
            cell_cov = acct_cov.get(l1, {})
            if not is_prospect and not cell_cov.get("live_project"):
                opportunity[l1] = {"is_whitespace": True}

        # SIC from AM (first row for this account)
        sic_raw = sic_map.get(acct_id)
        sic = None if (sic_raw is None or pd.isna(sic_raw)) else (str(sic_raw).strip() or None)

        acct_obj = {
            "id":               acct_id,
            "name":             str(iaa_row.get("Planning Entity", "") or "").strip(),
            "mu":               str(iaa_row.get("Market Unit", "") or "").strip(),
            "sales_office":     str(iaa_row.get("Sales Office: Current", "") or "").strip(),
            "sales_group":      str(iaa_row.get("Sales Group: Current", "") or "").strip(),
            "industry":          iaa_industry_raw or None,
            "industry_bucket":   industry_bucket,
            "archetype":         str(iaa_row.get("PE Agg Archetype: Current") or "").strip() or None,
            "revenue_band":      str(iaa_row.get("Revenue Band") or "").strip() or None,
            "iac":               iaa_iac_raw,
            "geo_l3":            _geo_l3(iaa_row.get("Country")) if is_lac else None,
            "terr_employee":     str(iaa_row.get("Terr: Territory Employee") or "").strip() or None,
            "terr_manager":      str(iaa_row.get("Terr: Manager") or "").strip() or None,
            "segment":           _segment_from_iac(iaa_iac_raw, iaa_row.get("RBC: Current")),
            "rbc":               str(iaa_row.get("RBC: Current") or "").strip() or None,
            "num_solutions":     tao_fields.get("num_solutions"),
            "num_solutions_band":str(tao_fields.get("num_solutions_band") or "").strip() or None,
            "sic":              sic,
            "is_prospect":      is_prospect,
            "is_rise":          acct_id in rise_accounts,
            "is_top_parent":    str(iaa_row.get("SAP Top Parent CRM ID") or "").strip() == acct_id,
            "top_parent_id":    str(iaa_row.get("SAP Top Parent CRM ID") or "").strip(),
            "coverage":         {l1: acct_cov.get(l1, {"live_project": False, "any_status": False, "products": []}) for l1 in sah_l1_names},
            "tao":              {l1: tao_per_l1.get(l1) for l1 in sah_l1_names},
            "tao_l2":           {l1: tao_per_l2.get(l1, {}) for l1 in sah_l1_names},
            "pipeline_kusd":    {l1: pipeline_per_l1.get(l1, 0.0) for l1 in sah_l1_names},
            "planned_pipeline_kusd": {l1: spi_per_l1.get(l1, 0.0) for l1 in sah_l1_names},
            "applicable_products": applicable_products,
            "opportunity":      opportunity,
        }
        accounts_data.append(acct_obj)

    # ------------------------------------------------------------------
    # Layer 2: Join & coverage integrity (J-1 … J-7)
    # ------------------------------------------------------------------
    print("\nValidation — Layer 2: Join integrity")
    am_ids = set(am["Planning Entity ID"].dropna().astype(str).str.strip())
    iaa_ids = set(iaa["Planning Entity ID"].dropna().astype(str).str.strip())
    non_prospect_ids = {a["id"] for a in accounts_data if not a["is_prospect"]}
    tao_ids = set(tao_raw["Planning Entity ID"].dropna().astype(str).str.strip())
    am_l1_names = {
        strip_code(v) for v in am["Solution Area Level 1"].dropna()
        if isinstance(v, str) and strip_code(v)
    } if "Solution Area Level 1" in am.columns else set()
    canonical_l1_names = set(sah_l1_names)
    tao_industries = set()
    if "Industry" in tao_raw.columns:
        tao_industries = {
            str(v).strip() for v in tao_raw["Industry"].dropna() if str(v).strip()
        }
    known_crosswalk_keys = set(INDUSTRY_CROSSWALK.keys())

    try:
        validate.check_join_integrity(
            am_ids, iaa_ids, non_prospect_ids, tao_ids,
            am_l1_names, canonical_l1_names,
            tao_industries, known_crosswalk_keys,
            report,
            tao_raw=tao_raw,
        )
    except ValidationError as exc:
        print(f"\nIngest aborted due to hard validation failure: {exc}", file=sys.stderr)
        sys.exit(1)

    validate.check_no_coverage_duplicates(am, report)

    # J-4: ADRM pipeline coverage (informational)
    adrm_ids = set(adrm["Planning Entity ID"].dropna().astype(str).str.strip())
    adrm_rate = len(non_prospect_ids & adrm_ids) / len(non_prospect_ids) if non_prospect_ids else 0.0
    print(f"  [INFO] J-4: {adrm_rate:.1%} of non-prospects have ADRM pipeline data")

    # ------------------------------------------------------------------
    # Layer 3: Business logic correctness (B-1 … B-8)
    # ------------------------------------------------------------------
    print("\nValidation — Layer 3: Business logic")
    try:
        validate.check_business_logic(accounts_data, sah_l1_names, tao_raw, report)
    except ValidationError as exc:
        print(f"\nIngest aborted due to hard validation failure: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.am_tp:
        print("Loading AM (Top Parent)...")
        am_tp = load_am(args.am_tp)
        tp_full_cov, _ = build_coverage(am_tp, sah_l1_names, product_name_map)
        tp_coverage = {}
        for tp_id, l1_map in tp_full_cov.items():
            tp_coverage[tp_id] = {}
            for l1, cell in l1_map.items():
                l2_bools = {l2: True for l2, e in cell.get("l2", {}).items()
                            if e.get("live") or e.get("project") or e.get("shelfware")}
                if l2_bools:
                    tp_coverage[tp_id][l1] = l2_bools
        # Build {tp_id: display_name} — strip trailing "(0000xxxxx)" suffix if present
        if "Planning Entity" in am_tp.columns:
            tp_name_map = {}
            for _, row in am_tp[["Planning Entity ID", "Planning Entity"]].drop_duplicates("Planning Entity ID").iterrows():
                tp_id = str(row["Planning Entity ID"]).strip()
                raw = str(row.get("Planning Entity", "") or "").strip()
                name = re.sub(r"\s*\(\d+\)\s*$", "", raw).strip()
                if tp_id and name:
                    tp_name_map[tp_id] = name
        else:
            tp_name_map = {}
    else:
        tp_coverage = {}
        tp_name_map = {}

    output = {
        "meta": {
            "mu":            mu,
            "generated_at":  datetime.now(timezone.utc).isoformat(),
            "snapshot_date": args.snapshot_date,
            "currency":      "KUSD",
            "eur_to_usd":    EUR_TO_USD,
        },
        "sah_l1":       sah_l1_names,
        "sah_l1_short": [SAH_L1_ABBREV.get(l, l) for l in sah_l1_names],
        "sah_hierarchy": sah_hierarchy,
        "sah_l3_per_l2": sah_l3_per_l2_dict,
        "accounts":     accounts_data,
        "tp_coverage":  tp_coverage,
        "tp_name_map":  tp_name_map,
    }

    # ------------------------------------------------------------------
    # Layer 4: Output structure integrity (O-1 … O-3)
    # ------------------------------------------------------------------
    print("\nValidation — Layer 4: Output structure")
    try:
        validate.check_data_json_structure(output, report)
    except ValidationError as exc:
        print(f"\nIngest aborted due to hard validation failure: {exc}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    n_accounts = len(accounts_data)
    n_prospects = sum(1 for a in accounts_data if a["is_prospect"])
    n_ws_cells = sum(
        1 for a in accounts_data for l1 in sah_l1_names
        if a["opportunity"].get(l1, {}).get("is_whitespace")
    )
    print(f"\n{report.summary()}")
    print(f"Done. {n_accounts} accounts ({n_prospects} prospects), {n_ws_cells} whitespace cells.")
    print(f"Output written to {args.out}")
    if report.warn_count > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
