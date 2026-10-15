"""
build_industry_reference.py

Builds reference-data/SAP_Industry_Solution_Reference.xlsx from:
  - reference-data/Copy of Solution Areas and Logical Products 2026.xlsx (Products tab = hierarchy)
  - reference-data/scrping_results_from_sap_dot_com.xlsx (already-scraped industries)
  - NEW_SCRAPED_DATA dict below (additional industries scraped for this run)

Output sheets:
  1. Reference Solutions  — Industry | L1 | L2 | L3 | L4 | Tag | Category | Priority
  2. Glossary             — classification scheme + provenance
  3. Unmatched            — items that could not be resolved to the hierarchy
"""

import ast
import re
import json
from datetime import date
from collections import defaultdict

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# 1. LOAD THE HIERARCHY
# ---------------------------------------------------------------------------

HIERARCHY_FILE = "reference-data/Copy of Solution Areas and Logical Products 2026.xlsx"


def load_hierarchy(path):
    """
    Returns:
      lookup: dict  norm_ext_name -> list of entry dicts
      entries: list of all entry dicts
    """
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["Products"]
    rows = list(ws.iter_rows(values_only=True))
    # [0] Product Key, [1] Product Name, [2] SolAr Key, [3] SolAr 2026 (L1),
    # [4] SSA Key, [5] Sub-Solution Area 2026 (L2), [6] SA L3 Key, [7] Solution Area L3 2026 (L3),
    # [8] SA L4 Key, [9] Solution Area L4 2026 (L4), [10] Deployment, [11] Active,
    # [12] Product Type, [13] External Product Name
    lookup = defaultdict(list)
    entries = []
    for r in rows[1:]:
        if len(r) < 14:
            continue
        key, pname, _, l1, _, l2, _, l3, _, l4, dep, active, ptype, ext_name = r
        if ext_name:
            entry = {
                "product_key": key,
                "product_name": pname,
                "l1": l1 or "",
                "l2": l2 or "",
                "l3": l3 or "",
                "l4": l4 or "",
                "product_type": ptype or "",
                "ext_name": ext_name,
            }
            lookup[ext_name.strip().lower()].append(entry)
            entries.append(entry)
    return lookup, entries


# ---------------------------------------------------------------------------
# 2. NAME ALIASES — map industry-page names to canonical External Product Names
# ---------------------------------------------------------------------------

# Key: normalized (lower, stripped) industry-page name
# Value: list of canonical External Product Names to look up in hierarchy
# Use lists because some marketing names map to multiple products.
NAME_ALIASES = {
    # Generic SAP platform references
    "sap grow": ["SAP S/4HANA Cloud Public Edition"],
    "grow with sap": ["SAP S/4HANA Cloud Public Edition"],
    "sap cloud erp": ["SAP S/4HANA Cloud Public Edition"],
    "sap cloud erp for finance": ["SAP S/4HANA Cloud Public Edition"],
    "sap cloud erp finance": ["SAP S/4HANA Cloud Public Edition"],
    "sap cloud erp private edition for portfolio and project management": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private for product lifecycle": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private for manufacturing": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private manufacturing solutions": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private for service": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private for assets": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private for finance": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private edition": ["SAP S/4HANA Cloud Private Edition"],
    "sap business suite": ["SAP S/4HANA Cloud Private Edition"],
    "sap business suite for retail": ["SAP S/4HANA Cloud Private Edition"],

    # Transportation
    "sap transportation management": ["SAP S/4HANA Supply Chain for transportation management"],
    "transportation management": ["SAP S/4HANA Supply Chain for transportation management"],

    # IBP
    "sap integrated business planning for supply chain": ["SAP Integrated Business Planning for Supply Chain"],

    # BTP / AI / Joule
    "joule": ["Joule"],
    "sap business ai": ["SAP Business AI"],
    "sap business ai for finance": ["SAP Business AI"],
    "sap business ai for manufacturing": ["SAP Business AI"],
    "sap business ai for service": ["SAP Business AI"],
    "sap business ai for customer experience": ["SAP Business AI"],
    "sap business ai for procurement": ["SAP Business AI"],
    "sap ai for maintenance": ["SAP Business AI"],
    "sap analytics cloud in business data cloud": ["SAP Analytics Cloud for business intelligence"],
    # Warehouse management
    "warehouse operation management": ["SAP S/4HANA Cloud Private Edition, extended warehouse management"],
    "sap warehouse management": ["SAP S/4HANA Cloud Private Edition, extended warehouse management"],

    # Finance / S4
    "sap s/4hana for procurement": ["SAP Ariba Sourcing"],
    "sap cloud erp for procurement": ["SAP Ariba Sourcing"],
    "sap s/4hana cloud for procurement": ["SAP Ariba Sourcing"],
    "central procurement": ["SAP Ariba Sourcing"],
    "self-billing processing": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "real-time financial analysis": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "autonomous finance": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "autonomous spend": ["SAP Ariba Sourcing"],

    # HCM / HR
    "core hr and payroll software": ["SAP SuccessFactors Employee Central"],
    "human capital management": ["SAP SuccessFactors Employee Central"],
    "workforce management": ["SAP Fieldglass Contingent Workforce Management"],
    "travel and expense management solutions": ["Concur Travel"],
    "travel, expense, and invoice management": ["Concur Travel"],
    "sap successfactors solutions for core hr, time, and payroll": ["SAP SuccessFactors Employee Central"],
    "sap successfactors document management": ["SAP SuccessFactors Employee Central"],

    # Supply chain descriptive names
    "supply and distribution network planning": ["SAP Integrated Business Planning"],
    "global track and trace": ["SAP Business Network Global Track and Trace"],
    "material traceability": ["SAP Business Network Material Traceability"],
    "manufacturing networks": ["SAP Digital Manufacturing"],
    "manufacturing": ["SAP Digital Manufacturing"],
    "asset management resource planning": ["SAP Asset Performance Management"],
    "responsible design and production": ["SAP Responsible Design and Production"],
    "sap business network for supply chain": ["SAP Business Network Supply Chain Collaboration"],
    "sap business network for logistics": ["SAP Business Network Freight Collaboration"],

    # CX / Sales
    "trade and revenue growth management": ["SAP Revenue Growth Management"],
    "omnichannel order management": ["SAP Order Management foundation"],
    "insights and automation for sales, service, and marketing": ["SAP Sales Cloud"],
    "ai-driven discovery and exceptional experiences": ["SAP Commerce Cloud"],
    "sales automation": ["SAP Sales Cloud"],

    # Procurement descriptive names
    "supplier collaboration": ["SAP Business Network Supply Chain Collaboration"],
    "procurement contract management": ["SAP Ariba Contracts"],
    "procurement analytics": ["SAP Analytics Cloud for business intelligence"],
    "sap ariba": ["SAP Ariba Sourcing"],
    "sap strategic sourcing": ["SAP Ariba Sourcing"],
    "sap ariba central procurement": ["SAP Ariba Sourcing"],

    # Product dev / innovation
    "product formulation and recipe management": ["SAP S/4HANA Cloud Public Edition"],
    "product development and configuration": ["SAP S/4HANA Cloud Public Edition"],
    "portfolio and project management": ["SAP Project and Resource Management"],
    "product compliance": ["SAP S/4HANA for product compliance"],

    # Manufacturing / AI agentic references
    "autonomous commodity management": ["SAP Commodity Management"],
    "autonomous revenue growth management": ["SAP Revenue Growth Management"],
    "autonomous unified commerce": ["SAP Commerce Cloud"],
    "autonomous regulated manufacturing": ["SAP Digital Manufacturing"],
    "autonomous adaptive production": ["SAP Digital Manufacturing"],
    "autonomous supply chain management": ["SAP Integrated Business Planning for Supply Chain"],
    "sap grc and cybersecurity": ["SAP GRC Access Control"],

    # Misc
    "sap paybacks and chargebacks by vistex": ["SAP Incentive Administration by Vistex and SAP Paybacks and Chargebacks by Vistex"],
    "sap s/4hana manufacturing for planning and scheduling": ["SAP S/4HANA Manufacturing for planning and scheduling"],

    # S/4HANA Public Cloud ERP variants
    "sap s/4hana cloud public edition": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "sap cloud erp for sales": ["SAP S/4HANA Cloud Public Edition"],
    "sap cloud erp for supply chain": ["SAP S/4HANA Cloud Public Edition"],
    "sap cloud erp for supply chain (inbound)": ["SAP S/4HANA Cloud Public Edition"],
    "sap cloud erp for asset management": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private (hydrocarbon supply)": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp private (secondary distribution)": ["SAP S/4HANA Cloud Private Edition"],

    # S/4HANA EHS
    "sap s/4hana for ehs environment management": ["SAP S/4HANA Cloud Public Edition, EHS environment management"],
    "sap s/4hana cloud public edition, ehs environment management": ["SAP S/4HANA Cloud Public Edition, EHS environment management"],
    "sap s/4hana for ehs workplace safety": ["SAP S/4HANA Cloud Public Edition, EHS environment management"],
    "sap s/4hana for ehs workplace safety (end-to-end)": ["SAP S/4HANA Cloud Public Edition, EHS environment management"],

    # Industry-specific S/4HANA
    "sap s/4hana retail for merchandise management": ["SAP Merchandising for Retail and Wholesale Distribution"],
    "sap s/4hana for fashion and vertical business": ["SAP S/4HANA Cloud Public Edition, retail, fashion, and vertical business"],
    "sap s/4hana for field equipment and material logistics planning and execution": ["SAP S/4HANA Supply Chain for extended service parts planning"],

    # Asset / EAM
    "enterprise asset management": ["SAP Asset Performance Management"],
    "sap intelligent asset management": ["SAP Asset Performance Management"],

    # Billing / Revenue / E-mobility / Distribution
    "sap engagement cloud": ["SAP Service Cloud"],
    "sap e-mobility": ["SAP E-Mobility"],
    "distributed energy resources (der)": ["SAP Distributed Energy Resources"],
    "sap distributed energy resources": ["SAP Distributed Energy Resources"],
    "retail fuel network operations": ["SAP S/4HANA Cloud Private Edition"],
    "hydrocarbon accounting and management": ["SAP Upstream Hydrocarbon Accounting and Management for Oil and Gas"],
    "joint venture accounting": ["SAP Portfolio and Project Management"],
    "sap joint venture accounting": ["SAP Portfolio and Project Management"],

    # Portfolio / Project
    "sap enterprise portfolio and project management": ["SAP Portfolio and Project Management"],
    "portfolio and project management": ["SAP Portfolio and Project Management"],

    # Mining / O&G / Chemicals specific
    "sap commodity management": ["SAP Commodity Management"],
    "sap advanced commodity risk analytics": ["SAP Commodity Risk Management"],
    "sap commodity risk management": ["SAP Commodity Risk Management"],
    "autonomous asset management": ["SAP Asset Performance Management"],
    "autonomous project delivery": ["SAP Project and Resource Management"],
    "sap sales and operations planning": ["SAP Integrated Business Planning"],
    "sap upstream hydrocarbon accounting and management for oil and gas": ["SAP Upstream Hydrocarbon Accounting and Management for Oil and Gas"],

    # Finance catchalls
    "finance": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "financial management solutions": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "compliance and tax management": ["SAP governance, risk, and compliance solutions"],
    "sustainability reporting and management": ["SAP Sustainability Control Tower"],
    "carbon accounting software": ["SAP Sustainability Control Tower"],
    "sap cash application": ["SAP Advanced Financial Closing"],

    # HR catchalls
    "workforce and contingent workforce management": ["SAP Fieldglass Contingent Workforce Management"],
    "sap enable now": ["SAP SuccessFactors Employee Central"],
    "sap business ai for human resources": ["SAP AI Services"],
    "sap business ai for hr": ["SAP AI Services"],
    "sap business ai": ["SAP AI Services"],
    "sap business ai for finance": ["SAP AI Services"],
    "sap business ai for manufacturing": ["SAP AI Services"],
    "sap business ai for service": ["SAP AI Services"],
    "sap business ai for customer experience": ["SAP AI Services"],
    "sap business ai for procurement": ["SAP AI Services"],
    "sap ai for maintenance": ["SAP AI Services"],
    "sap successfactors": ["SAP SuccessFactors Employee Central"],
    "travel and expense management": ["Concur Travel"],

    # Modern procurement / sourcing descriptive
    "modern procurement": ["SAP Ariba Central Procurement"],
    "sourcing and contract management": ["SAP Ariba Contracts"],
    "sap ariba contracts": ["SAP Ariba Contracts"],
    "sap ariba contract intelligence by icertis": ["SAP Ariba Contracts"],
    "icertis contract intelligence (ici) for sap ariba": ["SAP Ariba Contracts"],
    # Sustainability
    "sap sustainability data exchange": ["SAP Sustainability Data Exchange"],
    "sap sustainability footprint management": ["SAP Sustainability Footprint Management"],

    # More S/4HANA cloud ERP variants
    "sap cloud erp for manufacturing": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp asset management": ["SAP S/4HANA Cloud Private Edition"],
    "sap cloud erp for services": ["SAP S/4HANA Cloud Private Edition"],
    "sap core hr and payroll": ["SAP SuccessFactors Employee Central"],
    "sap cloud erp for finance (compliance)": ["SAP S/4HANA Cloud Private Edition"],
    "sap distributed energy resources": ["SAP Billing and Revenue Innovation Management"],
    "sap s/4hana cloud": ["SAP S/4HANA Cloud Private Edition"],
    "sap s/4hana cloud, public edition": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "sap s/4hana public cloud edition": ["SAP S/4HANA Cloud Public Edition, group reporting"],

    # New industry products
    "sap sport one": ["SAP Analytics Cloud for business intelligence"],
    "sap event ticketing": ["SAP Event Ticketing, cloud edition"],
    "sap customer checkout": ["SAP Customer Checkout, cloud edition"],
    "sap emarsys": ["SAP Emarsys"],
    "sap signavio process transformation suite": ["SAP Signavio Process Intelligence"],
    "sap signavio process insights": ["SAP Signavio Process Intelligence"],
    "sap business technology platform": ["SAP AI Core"],
    "sap enterprise asset management": ["SAP Asset Performance Management"],
    "sap customer relationship management": ["SAP CRM Sales"],
    "sap crm": ["SAP CRM Sales"],
    "sap ariba solutions": ["SAP Ariba Sourcing"],
    "sap ariba sourcing and procurement for public sector in sap s/4hana": ["SAP S/4HANA Sourcing and Procurement for Public Sector"],
    "sap treasury and risk management": ["SAP Treasury and Risk Management, private cloud edition"],
    "budget and grant management": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "core hr and payroll": ["SAP SuccessFactors Employee Central"],
    "talent management": ["SAP SuccessFactors Talent Management"],
    "workforce analytics": ["SAP SuccessFactors Employee Central"],
    "sap successfactors talent solutions": ["SAP SuccessFactors Talent Management"],
    "sap successfactors hcm": ["SAP SuccessFactors Employee Central"],
    "sap sales performance management": ["SAP SuccessFactors Incentive Management"],
    "sales performance management": ["SAP SuccessFactors Incentive Management"],
    "hr management": ["SAP SuccessFactors Employee Central"],
    "grc and cybersecurity solutions": ["SAP governance, risk, and compliance solutions"],
    "sap accounting and financial close": ["SAP Advanced Financial Closing"],
    "procurement management": ["SAP Ariba Sourcing"],
    "procurement": ["SAP Ariba Sourcing"],
    "supplier management": ["SAP Business Network Supply Chain Collaboration"],
    "spend management optimization": ["SAP Ariba Sourcing"],
    "ai with sap business data cloud": ["SAP Business Data Cloud"],
    "generative ai": ["SAP AI Services"],
    "sap cloud erp procurement": ["SAP Ariba Sourcing"],
    "sap s/4hana cloud for receivables management": ["SAP S/4HANA Cloud Public Edition, receivables management"],
    "integrated customer experience": ["SAP Service Cloud"],
    "ai-driven finance transformation": ["SAP S/4HANA Cloud Public Edition, group reporting"],
    "compliance and security": ["SAP governance, risk, and compliance solutions"],
    "product lifecycle management": ["SAP S/4HANA Cloud Private Edition, product lifecycle management"],
    "sap business network": ["SAP Business Network Supply Chain Collaboration"],
    "sap sovereign cloud": ["SAP S/4HANA Cloud Private Edition"],
    "sap integrated business planning for demand": ["SAP Integrated Business Planning"],
    "sap cloud erp private asset management": ["SAP S/4HANA Cloud Private Edition"],
    "global track and trace": ["SAP Business Network Global Track and Trace"],
    "sap service and asset manager mobile app": ["SAP Service and Asset Manager"],
    "sap analytics cloud": ["SAP Analytics Cloud for business intelligence"],
    "cloud for banking": ["SAP Transactional Banking"],
    "sap profitability and performance management": ["SAP Profitability and Performance Management"],
    "sap datasphere": ["SAP Datasphere"],

    # Misc industry-specific
    "ecovadis": ["EcoVadis Business Sustainability Ratings for Ariba"],
    "ecovadis business sustainability assessments, esg ratings and carbon scorecards": ["EcoVadis Business Sustainability Ratings for SAP Business Network"],
    "ecovadis business sustainability assessments, esg ratings, and carbon scorecards": ["EcoVadis Business Sustainability Ratings for SAP Business Network"],

    "sap extended warehouse management": ["SAP S/4HANA Cloud Private Edition, extended warehouse management"],
    "mirakl marketplace management": ["Mirakl Marketplace Platform"],
    "ecovadis business sustainability ratings for sap ariba": ["EcoVadis Business Sustainability Ratings for Ariba"],
    "sap customer activity repository applications bundle": ["SAP Customer Activity Repository"],
    "sap order and delivery scheduling": ["SAP Order and Delivery Scheduling"],
    "sap predictive replenishment": ["SAP Predictive Replenishment"],
    "sap recommerce": ["SAP Commerce Cloud"],
    "sap business network commerce automation": ["SAP Business Network Supply Chain Collaboration"],
    "sap s/4hana cloud, public edition": ["SAP S/4HANA Cloud Public Edition"],
    "sap service and asset manager": ["SAP Service and Asset Manager"],
    "sap billing and revenue innovation management": ["SAP Billing and Revenue Innovation Management"],
    "sap incentive administration by vistex": ["SAP Incentive Administration by Vistex and SAP Paybacks and Chargebacks by Vistex"],
    "sap incentive management": ["SAP SuccessFactors Incentive Management"],
    "sap grc access control": ["SAP Access Control"],
    "sap governance, risk, and compliance solutions": ["SAP governance, risk, and compliance solutions"],
    "sap grc and cybersecurity": ["SAP governance, risk, and compliance solutions"],
    "sap content stream by skillsoft": ["SAP Content Stream by Skillsoft"],
    "sap workforce forecasting and scheduling by workforce software": ["SAP Workforce Forecasting and Scheduling by WorkForce Software"],
    "sap absence and leave management by workforce software": ["SAP Workforce Forecasting and Scheduling by WorkForce Software"],
    "sap time and attendance management by workforce software": ["SAP Time and Attendance Management by WorkForce Software"],
    "sap intercompany governance by blackline": ["SAP Account Substantiation and Automation by BlackLine"],
    "sap account substantiation and automation by blackline": ["SAP Account Substantiation and Automation by BlackLine"],
    "sap ariba contract intelligence by icertis": ["SAP Ariba Contracts"],
    "sap yard logistics": ["SAP Yard Logistics"],
    "sap global trade services": ["SAP Global Trade Services"],
    "sap customer data platform": ["SAP Customer Data Platform"],
    "sap fieldglass contingent workforce management": ["SAP Fieldglass Contingent Workforce Management"],
    "sap fieldglass assignment management": ["SAP Fieldglass Assignment Management"],
    "sap successfactors hxm suite": ["SAP SuccessFactors Employee Central"],
    "sap successfactors employee central": ["SAP SuccessFactors Employee Central"],
    "sap successfactors workforce analytics": ["SAP SuccessFactors Employee Central"],
    "sap concur travel": ["Concur Travel"],
    "sap entitlement management": ["SAP Entitlement Management"],
    "sap subscription billing": ["SAP Subscription Billing"],
}


def normalize(s):
    return s.strip().lower() if s else ""


def find_hierarchy_entries(sol_name, lookup):
    """
    Given an industry-page solution name, find matching hierarchy entries.
    Returns list of entry dicts (may be empty).
    """
    norm = normalize(sol_name)

    # 1. Direct lookup
    if norm in lookup:
        return lookup[norm]

    # 2. Alias lookup
    if norm in NAME_ALIASES:
        results = []
        for canonical in NAME_ALIASES[norm]:
            if normalize(canonical) in lookup:
                results.extend(lookup[normalize(canonical)])
        if results:
            return results

    # 3. Fuzzy: strip leading "SAP " and try again
    stripped = re.sub(r"^sap\s+", "", norm)
    if stripped != norm and stripped in lookup:
        return lookup[stripped]

    # 4. Partial prefix match (e.g. "SAP Ariba" -> first entry with that prefix)
    prefix_matches = [v for k, v in lookup.items() if k.startswith(norm) or norm.startswith(k[:20])]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    return []


# ---------------------------------------------------------------------------
# 3. CLASSIFICATION LOGIC
# ---------------------------------------------------------------------------

# Pre-defined overrides for cross-industry foundational products.
# Format: (l1, l2) -> (category, priority)
# These override the per-industry heuristic.
CORE_OVERRIDES = {
    # ERP backbone
    ("Cloud ERP Private", "Cloud ERP Private"): ("Core", "Must-have"),
    ("Finance and Spend Management", "Accounting & Financial Close"): ("Core", "Must-have"),
    ("Finance and Spend Management", "Financial Planning & Analysis"): ("Core", "Must-have"),
    ("Finance and Spend Management", "Quote to Cash"): ("Core", "Must-have"),
    ("Finance and Spend Management", "Finance Private"): ("Core", "Must-have"),
    ("Human Capital Management", "Core HR and Payroll public"): ("Core", "Must-have"),
    ("Human Capital Management", "Learning and Talent"): ("Core", "Optional"),
    ("Human Capital Management", "Workforce Management"): ("Core", "Optional"),
    ("Finance and Spend Management", "Travel and Expense"): ("Core", "Common"),
    ("Finance and Spend Management", "Procurement"): ("Core", "Common"),
    ("Finance and Spend Management", "Fieldglass"): ("Core", "Optional"),
    ("Supply Chain Management", "Plan"): ("Core", "Common"),
    ("Supply Chain Management", "Business Network"): ("Core", "Common"),
    ("Data & AI", "BDC Capacity Units"): ("Core", "Common"),
    ("Data & AI", "BDC Public"): ("Core", "Common"),
    ("Data & AI", "BDC Private"): ("Core", "Common"),
    ("Data & AI", "Artificial Intelligence"): ("Core", "Common"),
    ("Business Technology Platform", "SAP Integration Suite"): ("Core", "Common"),
    ("Business Technology Platform", "SAP Build"): ("Core", "Optional"),
}

# Industry-specific add-ons by L2 — used when L1 = SCM or CX and not in core overrides
ADDON_MUST_HAVE_L2 = {
    "Operate & Service", "Make & Deliver", "SCM Private",
    "Commerce", "Sales and Service", "Marketing", "Sales Performance Management",
}

ADDON_COMMON_L2 = {
    "Responsible Design and Production", "Environment Health and Safety",
    "Life Sciences Regulatory", "BTP Other", "Enterprise Agreements",
}


def classify(entry, industry_page_category):
    """
    Returns (tag, category, priority) for a hierarchy entry.
    """
    l1 = entry.get("l1", "")
    l2 = entry.get("l2", "")
    ptype = entry.get("product_type", "")

    # Check CORE_OVERRIDES first
    key = (l1, l2)
    if key in CORE_OVERRIDES:
        cat, pri = CORE_OVERRIDES[key]
        return _tag(cat, pri), cat, pri

    # 3rd-party products: always Add-on
    if ptype == "3rd Party Product":
        # Partner-specific SAP-branded products (BlackLine, WorkForce, etc.) commonly adopted
        ext = entry.get("ext_name", "").lower()
        if any(x in ext for x in ["blackline", "workforce software", "icertis", "opentext", "docusign"]):
            return "AC", "Add-on", "Common"
        return "AO", "Add-on", "Optional"

    # Cloud ERP Private and related: always Core Must-have
    if l1 == "Cloud ERP Private":
        return "CM", "Core", "Must-have"

    # Finance backbone
    if l1 == "Finance and Spend Management":
        if l2 in ("Accounting & Financial Close", "Financial Planning & Analysis", "Quote to Cash", "Finance Private"):
            return "CM", "Core", "Must-have"
        if l2 in ("Procurement",):
            return "CC", "Core", "Common"
        if l2 == "Travel and Expense":
            return "CC", "Core", "Common"
        return "CO", "Core", "Optional"

    # HCM
    if l1 == "Human Capital Management":
        if l2 in ("Core HR and Payroll public", "Core HR and Payroll private"):
            return "CM", "Core", "Must-have"
        return "CC", "Core", "Common"

    # Supply Chain
    if l1 == "Supply Chain Management":
        if l2 == "Plan":
            return "CC", "Core", "Common"
        if l2 in ("Make & Deliver", "Operate & Service"):
            return "AC", "Add-on", "Common"
        if l2 == "Business Network":
            return "CC", "Core", "Common"
        if l2 == "SCM Private":
            return "AC", "Add-on", "Common"
        return "AC", "Add-on", "Common"

    # Customer Experience
    if l1 == "Customer Experience":
        if l2 == "Commerce":
            return "AC", "Add-on", "Common"
        if l2 in ("Sales and Service", "Marketing"):
            return "AC", "Add-on", "Common"
        if l2 == "Sales Performance Management":
            return "AO", "Add-on", "Optional"
        return "AO", "Add-on", "Optional"

    # Data & AI
    if l1 == "Data & AI":
        if l2 in ("BDC Capacity Units", "BDC Public", "Artificial Intelligence"):
            return "CC", "Core", "Common"
        return "CO", "Core", "Optional"

    # BTP
    if l1 == "Business Technology Platform":
        return "CO", "Core", "Optional"

    # Business Transformation Management (LeanIX, Signavio)
    if l1 == "Business Transformation Management":
        return "CO", "Core", "Optional"

    # Fallback
    return "AC", "Add-on", "Common"


def _tag(category, priority):
    return {"Core": {"Must-have": "CM", "Common": "CC", "Optional": "CO"},
            "Add-on": {"Must-have": "AM", "Common": "AC", "Optional": "AO"}}[category][priority]


# ---------------------------------------------------------------------------
# 4. LOAD ALREADY-SCRAPED DATA
# ---------------------------------------------------------------------------

SCRAPING_FILE = "reference-data/scrping_results_from_sap_dot_com.xlsx"


def load_scraped_data(path):
    """Returns list of {industry, url, solutions: [{solution_name, category_heading, is_partner}]}"""
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    results = []
    for r in rows[1:]:
        url, industry, solutions_str, name = r
        try:
            solutions = ast.literal_eval(solutions_str) if solutions_str else []
        except Exception:
            solutions = []
        results.append({"industry": industry, "url": url, "solutions": solutions})
    return results


# ---------------------------------------------------------------------------
# 5. NEW SCRAPED DATA — populated from agent outputs
# ---------------------------------------------------------------------------

# This dict holds the scraped solutions for industries not yet in the scraping file.
# Key: industry name  Value: {url, solutions list}
NEW_SCRAPED_DATA = {}


def add_new_scraped(industry_data_list):
    """Add a list of {industry, url, solutions} dicts to NEW_SCRAPED_DATA."""
    for item in industry_data_list:
        NEW_SCRAPED_DATA[item["industry"]] = {
            "url": item["url"],
            "solutions": item["solutions"],
        }


# ---------------------------------------------------------------------------
# 6. PROCESS: MATCH + CLASSIFY + DEDUPLICATE
# ---------------------------------------------------------------------------

def process_industries(all_industries, lookup):
    """
    all_industries: list of {industry, url, solutions}
    Returns: (reference_rows, unmatched_rows)
    """
    reference_rows = []  # (industry, l1, l2, l3, l4, tag, cat, pri)
    unmatched_rows = []  # (industry, raw_name, on_page_cat, url, reason)
    seen = set()

    for ind_data in all_industries:
        industry = ind_data["industry"]
        url = ind_data["url"]
        solutions = ind_data["solutions"]

        for sol in solutions:
            sol_name = sol.get("solution_name", "").strip()
            cat_heading = sol.get("category_heading", "")
            is_partner = sol.get("is_partner", False)

            if not sol_name:
                continue

            # Skip pure navigation/header entries
            if cat_heading.lower() in ("header", "faq"):
                continue

            entries = find_hierarchy_entries(sol_name, lookup)

            if not entries:
                unmatched_rows.append((
                    industry,
                    sol_name,
                    cat_heading,
                    url,
                    "No match found in Products hierarchy"
                ))
                continue

            for entry in entries:
                l1 = entry["l1"] or ""
                l2 = entry["l2"] or ""
                l3 = entry["l3"] or ""
                l4 = entry["l4"] or ""

                # Deduplicate on (industry, l1, l2, l3, l4)
                dedup_key = (industry, l1, l2, l3, l4)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                tag, category, priority = classify(entry, cat_heading)
                ext_name = entry.get("ext_name", "")
                reference_rows.append((industry, l1, l2, l3, l4, ext_name, tag, category, priority))

    # Sort
    reference_rows.sort(key=lambda r: (r[0], r[1], r[2], r[3], r[4], r[5]))
    return reference_rows, unmatched_rows


# ---------------------------------------------------------------------------
# 7. WRITE EXCEL OUTPUT
# ---------------------------------------------------------------------------

COMPILE_DATE = date.today().isoformat()
OUTPUT_FILE = "reference-data/SAP_Industry_Solution_Reference.xlsx"

HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
BODY_FONT = Font(name="Calibri", size=10)
ALT_FILL = PatternFill(start_color="EBF3FB", end_color="EBF3FB", fill_type="solid")

TAG_COLORS = {
    "CM": "1F7A1F",  # dark green
    "CC": "3CB371",  # medium green
    "CO": "90EE90",  # light green
    "AM": "8B0000",  # dark red
    "AC": "CD5C5C",  # indian red
    "AO": "FFB6C1",  # light pink
}


def write_reference_sheet(wb, reference_rows):
    ws = wb.create_sheet("Reference Solutions")
    headers = ["Industry", "Solution Area L1", "Solution Area L2",
               "Solution Area L3", "Solution Area L4", "Solution Name", "Tag", "Category", "Priority"]
    ws.append(headers)

    # Style header
    for col, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[1].height = 28

    for i, row in enumerate(reference_rows, 2):
        ws.append(list(row))
        fill = ALT_FILL if i % 2 == 0 else None
        for col in range(1, 10):
            cell = ws.cell(row=i, column=col)
            cell.font = BODY_FONT
            if col == 7:  # Tag column — color by tag
                tag = row[6]
                color = TAG_COLORS.get(tag, "000000")
                cell.font = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
                cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
                cell.alignment = Alignment(horizontal="center")
            elif fill:
                cell.fill = fill

    # Column widths
    col_widths = [30, 32, 36, 40, 40, 40, 8, 12, 14]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def write_glossary_sheet(wb, all_industries, reference_rows, unmatched_rows):
    ws = wb.create_sheet("Glossary")

    def hdr(text, row_offset=0):
        return (text, True, "1F4E79", "FFFFFF")

    def body(text):
        return (text, False, None, None)

    content = [
        ("SAP Industry Solution Reference — Classification Glossary", True, "1F4E79", "FFFFFF"),
        ("", False, None, None),
        ("CLASSIFICATION SCHEME", True, "2E75B6", "FFFFFF"),
        ("", False, None, None),
        ("Tag | Category | Priority | Meaning", True, "D6E4F0", "000000"),
        ("CM  | Core     | Must-have | Foundational product required for core end-to-end processes across industries (e.g. ERP, core finance).", False, None, None),
        ("CC  | Core     | Common    | Broadly applicable cross-industry; frequently selected in mature deployments.", False, None, None),
        ("CO  | Core     | Optional  | Cross-industry product relevant only in specific scenarios.", False, None, None),
        ("AM  | Add-on   | Must-have | Industry-specific; required for regulatory or key industry processes.", False, None, None),
        ("AC  | Add-on   | Common    | Industry-specific; commonly adopted but not strictly day-one.", False, None, None),
        ("AO  | Add-on   | Optional  | Industry-specific; advanced or niche scenarios.", False, None, None),
        ("", False, None, None),
        ("SOLUTION AREA HIERARCHY", True, "2E75B6", "FFFFFF"),
        ("", False, None, None),
        ("All solution area names (L1–L4) come verbatim from the 'Products' tab of:", False, None, None),
        (f"  {HIERARCHY_FILE}", False, None, None),
        ("", False, None, None),
        ("L1 (SolAr 2026)          — Top-level portfolio (e.g. 'Finance and Spend Management', 'Supply Chain Management')", False, None, None),
        ("L2 (Sub-Solution Area)   — Major product family within L1 (e.g. 'Procurement', 'Plan')", False, None, None),
        ("L3 (Solution Area L3)    — Product line / grouping within L2", False, None, None),
        ("L4 (Solution Area L4)    — Specific SKU / deployment variant", False, None, None),
        ("", False, None, None),
        ("CORE vs. ADD-ON LOGIC", True, "2E75B6", "FFFFFF"),
        ("", False, None, None),
        ("Category = 'Core'    for cross-industry/foundational products (ERP, Finance, HCM, BTP, Data & AI).", False, None, None),
        ("Category = 'Add-on'  for industry-specific or scenario-specific products.", False, None, None),
        ("3rd-party products are always classified as Add-on.", False, None, None),
        ("When uncertain between two priorities, the more conservative (lower) priority was chosen.", False, None, None),
        ("", False, None, None),
        ("SUMMARY STATISTICS", True, "2E75B6", "FFFFFF"),
        ("", False, None, None),
        (f"Industries covered:  {len(set(r[0] for r in reference_rows))}", False, None, None),
        (f"Total reference rows: {len(reference_rows)}", False, None, None),
        (f"Unmatched items:     {len(unmatched_rows)}", False, None, None),
        (f"Compiled:            {COMPILE_DATE}", False, None, None),
        ("", False, None, None),
        ("SOURCE INDUSTRY PAGES", True, "2E75B6", "FFFFFF"),
        ("", False, None, None),
    ]

    for ind_data in sorted(all_industries, key=lambda x: x["industry"]):
        content.append((f"  {ind_data['industry']:40s}  {ind_data['url']}", False, None, None))

    for i, (text, is_header, bg, fg) in enumerate(content, 1):
        cell = ws.cell(row=i, column=1, value=text)
        cell.font = Font(name="Calibri", bold=is_header, size=10 if not is_header else 11,
                         color=fg if fg else "000000")
        if bg:
            cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
        cell.alignment = Alignment(wrap_text=True)

    ws.column_dimensions["A"].width = 130


def write_unmatched_sheet(wb, unmatched_rows):
    ws = wb.create_sheet("Unmatched")
    headers = ["Industry", "Raw Solution Name", "On-page Category", "Source URL", "Reason"]
    ws.append(headers)

    for col, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
        cell.font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
        cell.alignment = Alignment(horizontal="center")

    for row in unmatched_rows:
        ws.append(list(row))

    col_widths = [28, 50, 38, 60, 40]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def build_excel(reference_rows, unmatched_rows, all_industries):
    wb = openpyxl.Workbook()
    # Remove default sheet
    default = wb.active
    wb.remove(default)

    write_reference_sheet(wb, reference_rows)
    write_glossary_sheet(wb, all_industries, reference_rows, unmatched_rows)
    write_unmatched_sheet(wb, unmatched_rows)

    wb.save(OUTPUT_FILE)
    print(f"Saved: {OUTPUT_FILE}")
    print(f"  Reference rows: {len(reference_rows)}")
    print(f"  Unmatched:      {len(unmatched_rows)}")
    print(f"  Industries:     {len(set(r[0] for r in reference_rows))}")


# ---------------------------------------------------------------------------
# 8. MAIN
# ---------------------------------------------------------------------------

def main():
    import sys
    import os

    print("Loading hierarchy...")
    lookup, _ = load_hierarchy(HIERARCHY_FILE)
    print(f"  {len(lookup)} unique external product names in hierarchy")

    print("Loading already-scraped data...")
    if os.path.exists(SCRAPING_FILE):
        scraped = load_scraped_data(SCRAPING_FILE)
        print(f"  {len(scraped)} industries from scraping file")
    else:
        scraped = []
        print(f"  Scraping file not found, skipping: {SCRAPING_FILE}")

    # Check if a JSON file with new scraped data was passed as argument
    if len(sys.argv) > 1:
        new_data_path = sys.argv[1]
        if os.path.exists(new_data_path):
            print(f"Loading new scraped data from {new_data_path}...")
            with open(new_data_path) as f:
                new_data = json.load(f)
            add_new_scraped(new_data)
            print(f"  Added {len(NEW_SCRAPED_DATA)} new industries")

    # Merge all industries
    existing_names = {d["industry"] for d in scraped}
    all_industries = list(scraped)
    for industry, data in NEW_SCRAPED_DATA.items():
        if industry not in existing_names:
            all_industries.append({
                "industry": industry,
                "url": data["url"],
                "solutions": data["solutions"],
            })

    print(f"Total industries to process: {len(all_industries)}")
    for d in sorted(all_industries, key=lambda x: x["industry"]):
        print(f"  - {d['industry']} ({len(d['solutions'])} solutions)")

    print("\nMatching and classifying...")
    reference_rows, unmatched_rows = process_industries(all_industries, lookup)

    print(f"  Matched rows:   {len(reference_rows)}")
    print(f"  Unmatched rows: {len(unmatched_rows)}")

    if unmatched_rows:
        print("\nUnmatched items (first 20):")
        for u in unmatched_rows[:20]:
            print(f"  [{u[0]}] {u[1]!r}")

    print("\nBuilding Excel...")
    build_excel(reference_rows, unmatched_rows, all_industries)
    print("Done.")


if __name__ == "__main__":
    main()
