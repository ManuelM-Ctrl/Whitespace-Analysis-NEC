# Spec Changes 2026-09-16 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix duplicate accounts in the Account Details table; re-point 6 dashboard filters from TAO to IAA Account Master as their data source (with Segment computed from IAC); and verify the WS×Pipeline column already handles pipe=0 correctly.

**Architecture:** All changes are in `ingest.py` only. `build.py` and `dashboard-template.html` do not need modification because the compact account object field names (`ind`, `arch`, `rev`, `iac`, `seg`, `rbc`) stay unchanged — only their data source moves from TAO to IAA.

**Tech Stack:** Python 3 + pandas.

**Spec:** [docs/2026-09-16 Spec changes.md](../2026-09-16%20Spec%20changes.md)

## Global Constraints

- Only `ingest.py` is touched in this plan. Do not modify `build.py` or `dashboard-template.html`.
- No automated test suite — running `python3 run_pipeline.py --input-dir input/<date>/` is the integration test.
- All monetary values in KUSD throughout the payload.
- `esc()` must wrap every data-derived string written to `innerHTML` (unchanged).
- IAA column names to use exactly as specified (see Task 2 steps).
- Do not break the `industry_bucket` derivation — it still uses `INDUSTRY_CROSSWALK` applied to the new IAA-sourced `industry` value.

---

### Task 1: Fix duplicate accounts (Spec §1.2)

**Root cause:** `load_iaa()` does not deduplicate on `Planning Entity ID`. If the IAA file has multiple rows for the same account (e.g. due to re-exports or merged territories), the `for _, iaa_row in iaa.iterrows()` loop at line 638 creates a separate account object for each row, producing duplicates in the output.

**Files:**
- Modify: `ingest.py:153-165` (`load_iaa()`)

**Interfaces:**
- Produces: `iaa` DataFrame — exactly one row per unique `Planning Entity ID`

- [ ] **Step 1: Add deduplication to `load_iaa()`**

  In `load_iaa()`, after `df["Planning Entity ID"] = df["Planning Entity ID"].str.strip().str.lstrip("0")` (currently line 162) and before the `return df` (line 165), add:

  ```python
      # Deduplicate: keep first occurrence per account; IAA can contain duplicate rows
      # for the same Planning Entity ID when accounts span multiple territories.
      df = df.drop_duplicates(subset="Planning Entity ID", keep="first")
  ```

- [ ] **Step 2: Run pipeline and verify no duplicates**

  Run: `python3 run_pipeline.py --input-dir input/2026-09-01/`

  Then verify with Python:
  ```python
  import json
  d = json.load(open("output/2026-09-01/data.json", encoding="utf-8"))
  ids = [a["id"] for a in d["accounts"]]
  dupes = [id for id in set(ids) if ids.count(id) > 1]
  print("Duplicate IDs:", dupes[:5] if dupes else "None — OK")
  ```

  Expected: no duplicate IDs.

- [ ] **Step 3: Commit**

  ```bash
  git add ingest.py
  git commit -m "fix: deduplicate IAA accounts by Planning Entity ID in load_iaa"
  ```

---

### Task 2: Re-point 6 filter fields from TAO to IAA (Spec §2 + §2.1)

**Context:** Currently `industry`, `archetype`, `revenue_band`, `iac`, `segment`, `rbc` are read from `tao_fields = tao_acct_fields.get(acct_id, {})` at lines 647–690. After this task they are read from `iaa_row` directly. The compact account object field names (`ind`, `arch`, `rev`, `iac`, `seg`, `rbc`) do not change so `build.py` and the dashboard are unaffected.

**Files:**
- Modify: `ingest.py:646-690` (account object construction in `main()`)

**Interfaces:**
- Consumes: `iaa_row` — pandas Series for the current IAA row; must have columns `Industry`, `Revenue Band`, `RBC: Current`, `PE Agg Archetype: Current`, `IAC (Engagement Model): Current`
- Produces: account object fields `industry`, `archetype`, `revenue_band`, `iac`, `segment`, `rbc` — now IAA-sourced

- [ ] **Step 1: Add `_segment_from_iac()` helper function**

  Add this function near the other short helpers (around line 510, after `_geo_l3`):

  ```python
  def _segment_from_iac(iac_raw):
      """Derive Segment from IAC value per spec 2026-09-16 §2.1."""
      v = str(iac_raw or "").strip()
      if v in ("C-Digital", "C-Field"):
          return "Corporate"
      if v in ("E-High Touch", "E-SCP"):
          return "Enterprise"
      if v == "Partner Driven":
          return "Partner Driven"
      return "Null"
  ```

- [ ] **Step 2: Replace TAO sources with IAA sources in account object construction**

  In `main()`, the block currently reads (lines ~646–690):
  ```python
      # TAO account-level fields
      tao_fields = tao_acct_fields.get(acct_id, {})
      industry_raw = tao_fields.get("industry") or ""
      industry_bucket = INDUSTRY_CROSSWALK.get(str(industry_raw).strip(), None)
      ...
      "industry":          str(industry_raw).strip() if industry_raw else None,
      "industry_bucket":   industry_bucket,
      "archetype":         str(tao_fields.get("archetype") or "").strip() or None,
      "revenue_band":      str(tao_fields.get("revenue_band") or "").strip() or None,
      "iac":               str(tao_fields.get("iac") or "").strip() or None,
      ...
      "segment":           str(tao_fields.get("segment") or "").strip() or None,
      "rbc":               str(tao_fields.get("rbc") or "").strip() or None,
  ```

  Replace the `industry_raw` and `industry_bucket` derivation block:
  ```python
      # TAO account-level fields (TAO: priority_score, strategy, gap, wallet, pipeline kept from TAO)
      tao_fields = tao_acct_fields.get(acct_id, {})

      # IAA-sourced fields (Industry, Archetype, Revenue Band, IAC, RBC, Segment)
      iaa_industry_raw = str(iaa_row.get("Industry") or "").strip()
      industry_raw     = iaa_industry_raw  # used below for industry_bucket
      industry_bucket  = INDUSTRY_CROSSWALK.get(iaa_industry_raw, None) if iaa_industry_raw else None
      iaa_iac_raw      = str(iaa_row.get("IAC (Engagement Model): Current") or "").strip() or None
  ```

  Then in the account object dict, replace the 6 TAO-sourced lines:
  ```python
      "industry":          iaa_industry_raw or None,
      "industry_bucket":   industry_bucket,
      "archetype":         str(iaa_row.get("PE Agg Archetype: Current") or "").strip() or None,
      "revenue_band":      str(iaa_row.get("Revenue Band") or "").strip() or None,
      "iac":               iaa_iac_raw,
      ...
      "segment":           _segment_from_iac(iaa_iac_raw),
      "rbc":               str(iaa_row.get("RBC: Current") or "").strip() or None,
  ```

  Keep `tao_fields` in scope — TAO is still used for `tao_per_l1`, `tao_per_l2`, `num_solutions`, `num_solutions_band`, and `priority_score`/`strategy`.

  Full context of the replacement for clarity:

  **Before** (lines ~646–690 as they stand):
  ```python
      # TAO account-level fields
      tao_fields = tao_acct_fields.get(acct_id, {})
      industry_raw = tao_fields.get("industry") or ""
      industry_bucket = INDUSTRY_CROSSWALK.get(str(industry_raw).strip(), None)
  ```
  and in the dict:
  ```python
      "industry":          str(industry_raw).strip() if industry_raw else None,
      "industry_bucket":   industry_bucket,
      "archetype":         str(tao_fields.get("archetype") or "").strip() or None,
      "revenue_band":      str(tao_fields.get("revenue_band") or "").strip() or None,
      "iac":               str(tao_fields.get("iac") or "").strip() or None,
      ...
      "segment":           str(tao_fields.get("segment") or "").strip() or None,
      "rbc":               str(tao_fields.get("rbc") or "").strip() or None,
  ```

  **After**:
  ```python
      # TAO account-level fields (gap/wallet/pipeline/strategy kept from TAO)
      tao_fields = tao_acct_fields.get(acct_id, {})

      # IAA-sourced filter fields
      iaa_industry_raw = str(iaa_row.get("Industry") or "").strip()
      iaa_iac_raw      = str(iaa_row.get("IAC (Engagement Model): Current") or "").strip() or None
      industry_bucket  = INDUSTRY_CROSSWALK.get(iaa_industry_raw, None) if iaa_industry_raw else None
  ```
  and in the dict:
  ```python
      "industry":          iaa_industry_raw or None,
      "industry_bucket":   industry_bucket,
      "archetype":         str(iaa_row.get("PE Agg Archetype: Current") or "").strip() or None,
      "revenue_band":      str(iaa_row.get("Revenue Band") or "").strip() or None,
      "iac":               iaa_iac_raw,
      ...
      "segment":           _segment_from_iac(iaa_iac_raw),
      "rbc":               str(iaa_row.get("RBC: Current") or "").strip() or None,
  ```

- [ ] **Step 3: Run pipeline and verify fields are populated**

  Run: `python3 run_pipeline.py --input-dir input/2026-09-01/`

  Then verify with Python:
  ```python
  import json
  d = json.load(open("output/2026-09-01/data.json", encoding="utf-8"))
  # Sample the first 5 non-prospect accounts
  non_prospects = [a for a in d["accounts"] if not a["is_prospect"]][:5]
  for a in non_prospects:
      print(f"{a['id']}: ind={a.get('ind')}, arch={a.get('arch')}, rev={a.get('rev')}, iac={a.get('iac')}, seg={a.get('seg')}, rbc={a.get('rbc')}")
  ```

  Wait — the compact object uses shortened field names (`ind`, `arch`, etc.) — check `data.json` (not the compact HTML) using the full field names:
  ```python
  for a in non_prospects:
      print(f"{a['id']}: industry={a.get('industry')}, archetype={a.get('archetype')}, rev={a.get('revenue_band')}, iac={a.get('iac')}, seg={a.get('segment')}, rbc={a.get('rbc')}")
  ```

  Expected: non-null values for accounts whose IAA rows have the new columns populated. If all values are `None`, the IAA column names may not match exactly — check with `print([c for c in iaa.columns if 'IAC' in c or 'RBC' in c or 'Revenue' in c or 'Archetype' in c or 'Industry' in c])` in a one-liner.

- [ ] **Step 4: Verify Segment mapping**

  ```python
  import json
  d = json.load(open("output/2026-09-01/data.json", encoding="utf-8"))
  # Check accounts with IAC values and their segment derivation
  for a in d["accounts"]:
      iac = a.get("iac")
      seg = a.get("segment")
      if iac:
          print(f"IAC={iac!r} → Segment={seg!r}")
          break
  # Also verify "Null" for empty IAC
  for a in d["accounts"]:
      if not a.get("iac"):
          print(f"empty IAC → Segment={a.get('segment')!r} (expect 'Null')")
          break
  ```

  Expected: IAC values map to Corporate/Enterprise/Partner Driven/Null per spec §2.1.

- [ ] **Step 5: Commit**

  ```bash
  git add ingest.py
  git commit -m "feat: re-point Industry/Archetype/RevBand/IAC/Segment/RBC filters from TAO to IAA; compute Segment from IAC"
  ```

---

### Task 3: Verify §1.1 is already handled + run full pipeline

**Context:** Section 1.1 asks that when `pipeline == 0` the Pipe column shows "Whitespace" label instead of `–`. This was implemented in the previous development session (commit `f3b7428`): the Pipe cell uses `pipeVal > 0 ? fmtUSD : 'Whitespace'` for whitespace accounts. Null/undefined pipe values are coerced to 0 via `(a.pipe && a.pipe[i]) || 0`. This task confirms the behavior is correct and runs the full pipeline.

**Files:** None to change (verification only).

- [ ] **Step 1: Confirm Pipe column implementation in dashboard-template.html**

  Search for the pipe cell rendering code:
  ```bash
  grep -n "pipeCell\|pipeVal\|Pipe" dashboard-template.html | head -20
  ```

  Expected: lines showing `pipeVal > 0 ? ... fmtUSD ... : ws-badge ws-badge--whitespace` pattern.

  If this pattern is NOT found (e.g. implementation was overwritten), it must be re-implemented per the code in `docs/superpowers/specs/2026-08-25-l3-drill-ws-pipeline-design.md` Section 3.

- [ ] **Step 2: Run full pipeline and open in browser**

  ```bash
  python3 run_pipeline.py --input-dir input/2026-09-01/
  ```

  Open `output/2026-09-01/whitespace-analyzer.html` in a browser. Check list:
  - [ ] Account Details normal mode: every L1 has two columns (`FSM` + `FSM Pipe`)
  - [ ] A whitespace account with no pipeline shows "Whitespace" in the Pipe column
  - [ ] A whitespace account with pipeline > 0 shows a KUSD value in the Pipe column
  - [ ] A covered account shows `–` in the Pipe column
  - [ ] Industry filter: dropdown shows values from IAA (not TAO)
  - [ ] Segment filter: dropdown shows Corporate/Enterprise/Partner Driven/Null (not raw TAO segments)
  - [ ] RBC, Archetype, Revenue Band, IAC filters: show IAA-sourced values
  - [ ] Filtering works correctly — selecting an Industry/Segment/etc. filters the account table
  - [ ] No JavaScript errors in browser console

- [ ] **Step 3: Commit (if any fixes were needed in step 1)**

  Only commit if step 1 found missing code and a fix was applied.

  ```bash
  git add dashboard-template.html
  git commit -m "fix: ensure Pipe column shows Whitespace badge when pipeline == 0"
  ```
