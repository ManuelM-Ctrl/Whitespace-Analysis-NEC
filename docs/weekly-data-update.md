# Weekly Data Update Instructions

## Overview

Each week, refresh the five source data files below, then run the pipeline to regenerate the dashboard.

---

## Files to Replace

### 1. Adoption Monitor (AM)
**Filename pattern:** `MW_MU_AM_<YYYY-MM-DD>.csv`
**Location:** `input/<YYYY-MM-DD>/`
**Format:** CSV, 1 skipped header row
**Settings:** Default
**Filters:** SBB Market Unit Desc = US Midwest
**Report:** [AM Report Shortcut](https://sap-sac.eu10.sapanalytics.cloud/sap/fpa/ui/app.html#/dataanalyzer&/dz/shortcuts/33D8A434BE414DA29843B2DD2E372F97)

| Column | Notes |
|--------|-------|
| `Planning Entity ID` | Account key; leading zeros are stripped at load |
| `Standard Industry Code (Key + Text)` | Used to populate the SIC field per account |
| `Max Adoption State` | Values: `Live`, `Project`, or `Shelfware` |
| `Solution Area Level 1` | Format: `Name (CODE)` — code is stripped automatically |
| `Solution Area Level 2` | Format: `Name (CODE)` — code is stripped automatically |
| `Solution Area Level 3` | Included in hierarchy |
| `Solution Area Level 4` | Included in hierarchy |
| `Logical Product` | Format: `Product Name (LPR###)` — used for product name resolution |

---

### 2. AM Top Parent (AM-TP) — optional
**Filename pattern:** `MW_MU_AM_TP_<YYYY-MM-DD>.csv`
**Location:** `input/<YYYY-MM-DD>/`
**Format:** Same columns as AM, scoped to top-parent CRM accounts
**Settings:** Default
**Filters:** `Planning Entity ID` in top parent list
**Report:** [AM-TP Report Shortcut](https://sap-sac.eu10.sapanalytics.cloud/sap/fpa/ui/app.html#/dataanalyzer&/dz/shortcuts/B7AA8A9FEC5C45BCA259FDB6BF96828F)

Used to populate `tp_l2s` and `tp_name` on each account. Pipeline runs without it; omit `--am-tp` if unavailable.

---

### 3. IAA Account Master
**Filename pattern:** `MW_MU_IAA_<YYYY-MM-DD>.csv`
**Location:** `input/<YYYY-MM-DD>/`
**Format:** CSV, 1 skipped header row
**Filters:** Market Unit = Midwest
**Report:** [IAA Report Shortcut](https://sap-sac.eu10.sapanalytics.cloud/sap/fpa/ui/app.html#/dataanalyzer&/dz/shortcuts/551870CC59274293B1825035256B6F6F)

| Column | Notes |
|--------|-------|
| `Planning Entity ID` | Master account key; leading zeros stripped |
| `Planning Entity` | Account display name |
| `Market Unit` | e.g., `US Midwest` |
| `Industry` | Raw industry string; present in file but not used directly — industry comes from the TAO `INDUSTRY` column |
| `Sales Office: Current` | Used for filtering; exclude `SL-MW-MMN-SHELL` |
| `Sales Group: Current` | Used for filtering; exclude rows containing `-PD-`, starting with `PD`, or containing `PartnerLed` |
| `SAP Top Parent CRM ID` | Used to link accounts to their top parent |

---

### 4. TAO Outside-In Metrics (3 files)
**Filename pattern:** `US_MIDWEST_TAO_<DD_MM_YYYY>_v<N>_1.csv`, `_2.csv`, `_3.csv`
**Location:** `input/<YYYY-MM-DD>/`
**Format:** CSV, split across three files (all loaded together)
**Report:** [TAO Report Shortcut](https://sap-business.eu10.sapanalytics.cloud/sap/fpa/ui/app.html#/dataanalyzer&/dz/shortcuts/4F16CC2EA14B417494B22B0BCB3EF268)

| Column | Notes |
|--------|-------|
| `ACCOUNT_ID` | Account key; renamed to `Planning Entity ID` at load; leading zeros are **not** stripped |
| `Solution Area` | Bare L1 name, no parenthetical code |
| `Sub-Solution Area` | Bare L2 name, no parenthetical code; rows where this is null are dropped |
| `INDUSTRY` | Used for industry crosswalk; see `INDUSTRY_CROSSWALK` in `ingest.py` |
| `ARCHETYPE` | Account archetype |
| `REVENUE_BANDS` | Account revenue band |
| `Gap to Estimated Wallet (KEuro)` | In **KEuro**; converted to KUSD at load using `EUR_TO_USD = 1.16` |
| `Estimated Wallet (KEuro)` | In **KEuro**; converted to KUSD at load |
| `Priority Score` | Used for sorting/display |
| `Strategy` | Narrative field |
| `Historical pipeline` | In KEuro; converted to KUSD |
| `SAP Cloud Exit ACV (KEuro)` | In KEuro; converted to KUSD |
| `CY pipeline (KEuro)` | In KEuro; converted to KUSD |
| `CY+1 pipeline (KEuro)` | In KEuro; converted to KUSD |

---

### 5. ADRM Pipeline
**Filename pattern:** `MW_MU_ADRM_<YYYY-MM-DD>.csv`
**Location:** `input/<YYYY-MM-DD>/`
**Format:** CSV, 1 skipped header row
**Settings:** Currency = USD, Hierarchy Version - Sales Current, Select Quarter = CQ, CQ+1, CQ+2, CQ+3
**Filters:** Zero Flag = N, Source = CLOUD, Region L1 Desc = Americas
**Report:** [ADRM Report Shortcut](https://sap-sac.eu10.sapanalytics.cloud/sap/fpa/ui/app.html#/dataanalyzer&/dz/shortcuts/3F9DB5FB2174435CAE73FC89F10E22E9)

| Column | Notes |
|--------|-------|
| `Planning Entity ID` | Account key; leading zeros stripped |
| `Solution Area L2` | **Contains the actual SAH L1 name** (column labeling is off by one in the source) |
| `Solution Area L3` | **Contains the actual SAH L2 name** |
| `Total @ FC` | Forecast pipeline in **Euros**; divided by 1,000 and converted to KUSD at load |

---

### 6. SPI Planned Pipeline — optional
**Filename pattern:** `MW_MU_SPI_<YYYY-MM-DD>.csv`
**Location:** `input/<YYYY-MM-DD>/`
**Format:** CSV, 1 skipped header row, UTF-8 BOM
**Settings:** Region Level 2: US Midwest, IP_CURRENCY = USD
**Report:** [SPI Report Shortcut](https://sap-sac.eu10.sapanalytics.cloud/sap/fpa/ui/app.html#/dataanalyzer&/dz/shortcuts/3F40060A56CE4D629443005DD486D52C)

| Column | Notes |
|--------|-------|
| `Acc Planning Entity ID` | Account key; leading zeros stripped |
| `Idea Solution Area L2` | SAH L2 name; rolled up to L1 via SAH hierarchy |
| `Exp. Pipeline` | Planned pipeline in **KUSD** |

---

## Reference Files (update only when content changes)

| File | Location | When to update |
|------|----------|----------------|
| `SAP_Industry_Solution_Reference.xlsx` | `reference-data/` | When industry solution applicability changes |
| `Copy of Solution Areas and Logical Products 2026 - update.xlsx` | `reference-data/` | When the SAH product hierarchy changes |

---

## Running the Update

### Step 1 — Export Top Parent IDs for AM-TP download

After downloading the IAA file (and before downloading AM-TP), run:

```bash
python3 tools/export_top_parent_ids.py --iaa input/<YYYY-MM-DD>/MW_MU_IAA_<YYYY-MM-DD>.csv
```

This writes `top_parent_ids.csv` alongside the IAA file in the same dated folder — a single-column list of SAP Top Parent CRM IDs (zero-padded to 10 digits) for accounts that roll up to a different top parent. Use this list to scope the AM-TP download from the Adoption Monitor before proceeding.

---

### Step 2 — Run the pipeline

Point the pipeline at the dated input folder:

```bash
python3 run_pipeline.py --input-dir input/2026-07-13/
```

The folder name is used automatically as the `--snapshot-date` (shown in the dashboard header). All source files are discovered by filename pattern — no need to spell out individual paths.

All outputs are written to `output/<YYYY-MM-DD>/`:

| File | Description |
|------|-------------|
| `whitespace-analyzer.html` | The dashboard — open in any browser |
| `data.json` | Intermediate ingest output |
| `clusters.json` | Intermediate cluster output |
| `version.json` | Build metadata |

<details>
<summary>Long-form invocation (explicit file paths)</summary>

```bash
python3 run_pipeline.py \
  --am    example-data/MW_MU_AM_<YYYY-MM-DD>.csv \
  --am-tp example-data/MW_MU_AM_TP_<YYYY-MM-DD>.csv \
  --iaa   example-data/MW_MU_IAA_<YYYY-MM-DD>.csv \
  --tao   example-data/US_MIDWEST_TAO_<DD_MM_YYYY>_v2_1.csv \
          example-data/US_MIDWEST_TAO_<DD_MM_YYYY>_v2_2.csv \
          example-data/US_MIDWEST_TAO_<DD_MM_YYYY>_v2_3.csv \
  --adrm  example-data/MW_MU_ADRM_<YYYY-MM-DD>.csv \
  --spi   example-data/MW_MU_SPI_<YYYY-MM-DD>.csv
```

</details>

---

## Validation

The pipeline runs validation automatically. Watch for:

- **Exit code 0** — clean run, no issues
- **Exit code 2** — soft warnings (output still generated; review the printed validation report before sharing)
- **Exit code 1** — hard failure (output not generated; fix the reported error before proceeding)

Common warning causes: AM↔IAA join rate below threshold, TAO coverage below 50% of non-prospects, or missing expected columns.
