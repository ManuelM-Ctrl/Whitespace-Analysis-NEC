# Account Details: L3 Drill + WS × Pipeline Columns

## Overview

Two enhancements to the Account Details table:
1. **L3 drill** — a second drill level (L1 → L2 → L3) extending the existing treemap drill pattern.
2. **WS × Pipeline columns** — a parallel pipeline column alongside each existing whitespace column.

---

## Section 1 — Data pipeline (ingest.py + build.py)

### ingest.py

**`build_coverage_index()`** — extend to capture L3 from `Solution Area Level 3`:
- Strip code from L3 value same as L1/L2.
- Store L3 status inside the L2 entry: `l2: {l2_name → {status, l3: {l3_name → status}}}`.
- `status` encoding: 3=Live, 2=Project, 1=Shelfware, 0=None (same as L2).

**New helper `build_l3_hierarchy(am_df)`** — returns:
```python
{l1_name → {l2_name → [l3_names_ordered]}}
```
Used by build.py to emit index arrays.

Store both structures in `data.json` under keys `l3_coverage` (merged into existing coverage dict) and `sah_l3_per_l2`.

### build.py

**`compact_account()`** — add `l3s` array:
```
l3s[i][j][k] — int 3/2/1/0 per L3 k under L2 j under L1 i
```
Indexed parallel to `l2s[i][j]`.

**DATA payload** — add `sah_l3_per_l2`:
```
sah_l3_per_l2[i][j] → [l3_name, ...]   (parallel index with l2s)
```

---

## Section 2 — Dashboard: L3 drill (dashboard-template.html)

### State
```js
treemapDrillL2: null   // L2 index when drilled into L3, or null
```

### Runtime global
```js
const L3_PER_L2 = DATA.sah_l3_per_l2 || [];
```

### renderTopAccountsTable logic

Three modes (in order of priority):

| Condition | Columns shown | Click on column header |
|---|---|---|
| `treemapDrillL2 !== null` | L3 names for that L2 | — |
| `treemapDrillL1 !== null` | L2 names for that L1 | Set `treemapDrillL2` |
| Both null (normal) | L1 abbreviations | Set `treemapDrillL1` (existing) |

### Back button
- When `treemapDrillL2 !== null`: show "← Back to L2" button → clears `treemapDrillL2`
- When `treemapDrillL1 !== null` (and no L2 drill): existing "← All Solution Areas" button

### Cell rendering (L3 mode)
Same badge logic as L2 mode: Covered / Project / Shelfware / Whitespace / — based on `a.l3s[drillL1][drillL2][k]` status.

### CSV export
`downloadAccountDetailsCSV()` — add third branch for `treemapDrillL2 !== null`, using L3 names as column headers and `a.l3s` for cell values.

---

## Section 3 — Dashboard: WS × Pipeline columns (dashboard-template.html)

### Normal mode (no drill)

For each L1 `i`, render **two adjacent columns** instead of one:

| Column | Header | Cell logic |
|---|---|---|
| Existing | `L1_SHORT[i]` | Covered / Shelfware / Whitespace / — (unchanged) |
| New | `L1_SHORT[i] + " Pipe"` | See below |

**Pipeline cell logic** (normal mode only):
- Not whitespace → `"—"`
- Whitespace AND `a.pipe[i] == 0` → badge "Whitespace"
- Whitespace AND `a.pipe[i] > 0` → formatted KUSD value

### Drill modes (L2 and L3)
Pipeline column is **not shown** in drill modes — ADRM pipeline data only exists at L1 granularity.

### CSV export
Add the pipeline column values alongside whitespace values in normal-mode export.

---

## Files touched

| File | Changes |
|---|---|
| `ingest.py` | Extend `build_coverage_index()` for L3; add `build_l3_hierarchy()`; emit `sah_l3_per_l2` in `data.json` |
| `build.py` | Add `l3s[i][j][k]` to `compact_account()`; add `sah_l3_per_l2` to DATA payload |
| `dashboard-template.html` | Add `treemapDrillL2` state; update `renderTopAccountsTable` for 3-level drill + pipeline columns; update `downloadAccountDetailsCSV` |
