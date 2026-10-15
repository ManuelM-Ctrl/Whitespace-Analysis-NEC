# Whitespace and Cross-Sell Opportunity Analyzer

Identifies SAP accounts that have zero coverage in one or more Solution Areas ("whitespace"), ranks those gaps by outside-in wallet opportunity, and produces a self-contained interactive HTML dashboard for the sales team.

**Quick reference:** [Weekly Update Job Aid](docs/Whitespace_Analyzer_Job_Aid.pptx) — 1-page step-by-step guide (PowerPoint)

## Requirements

Python 3 with `pandas` and `openpyxl`:

```bash
pip install pandas openpyxl
```

## Weekly Update

Each week you'll download fresh source files, drop them into a dated folder, and run one command.

### 1. Download source files

Create a folder named `input/<YYYY-MM-DD>/` (use the date you pulled the data) and place these files in it:

| File | Source system | Notes |
|------|---------------|-------|
| `MW_MU_AM_<YYYY-MM-DD>.csv` | Adoption Monitor | Filters: SBB Market Unit Desc = US Midwest |
| `MW_MU_IAA_<YYYY-MM-DD>.csv` | IAA | Filters: Market Unit = Midwest |
| `MW_MU_ADRM_<YYYY-MM-DD>.csv` | ADRM | Filters: Zero Flag = N, Source = CLOUD, Region L1 Desc = Americas |
| `US_MIDWEST_TAO_<DD_MM_YYYY>_v2_1.csv` + `_2.csv` + `_3.csv` | TAO | 3 export files; all go in the same folder |
| `MW_MU_SPI_<YYYY-MM-DD>.csv` | SPI | Optional; pipeline runs without it |

See [docs/weekly-data-update.md](docs/weekly-data-update.md) for exact export settings and column details for each file.

### 2. Generate the Top Parent ID list (for AM-TP)

Before downloading the AM Top Parent file, generate the ID list the Adoption Monitor needs:

```bash
python3 tools/export_top_parent_ids.py --iaa input/<YYYY-MM-DD>/MW_MU_IAA_<YYYY-MM-DD>.csv
```

This writes `top_parent_ids.csv` into the same dated folder. Use it to scope your AM-TP export, then place the resulting `MW_MU_AM_TP_<YYYY-MM-DD>.csv` in the folder alongside the other files.

### 3. Run the pipeline

```bash
python3 run_pipeline.py --input-dir input/2026-08-10/
```

Replace the date with your folder name. The pipeline auto-discovers all files, uses the folder name as the snapshot date shown in the dashboard header, and writes all outputs to a matching dated folder:

```
output/2026-08-10/whitespace-analyzer.html   ← open this in any browser
output/2026-08-10/data.json
output/2026-08-10/clusters.json
output/2026-08-10/version.json
```

### Validation

The pipeline prints a validation report after each run:

| Exit code | Meaning |
|-----------|---------|
| `0` | Clean run — safe to share |
| `2` | Soft warnings — output was generated; review the report before sharing |
| `1` | Hard failure — output was **not** generated; fix the reported error and re-run |

Common causes of exit code `2`: AM↔IAA account match rate below threshold, TAO coverage below 50% of non-prospects, or missing expected columns.

## Reference Files

These live in `reference-data/` and only need updating when the underlying data changes (not weekly):

| File | Update when… |
|------|-------------|
| `SAP_Industry_Solution_Reference.xlsx` | Industry solution applicability changes |
| `Copy of Solution Areas and Logical Products 2026 - update.xlsx` | SAH product hierarchy changes |
