# L3 Drill + WS×Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second drill level to the Account Details table (L1→L2→L3) and add a parallel WS×Pipeline column alongside each existing whitespace column in normal mode.

**Architecture:** L3 coverage is captured in `ingest.py` by extending the existing L2 entry dict with a nested `"l3"` dict; a helper function builds the hierarchy index `{l1→{l2→[l3s]}}` stored in `data.json`. `build.py` converts it to a 2D indexed array emitted in the DATA payload and adds `l3s[i][j][k]` to the compact account object. The dashboard adds a `treemapDrillL2` state variable, extends `renderTopAccountsTable()` to handle three modes (normal / L2-drill / L3-drill), and adds pipeline columns in normal mode.

**Tech Stack:** Python 3 + pandas (pipeline), Vue 3 + Chart.js 4 (dashboard).

**Spec:** [docs/superpowers/specs/2026-08-25-l3-drill-ws-pipeline-design.md](../specs/2026-08-25-l3-drill-ws-pipeline-design.md)

## Global Constraints

- No test suite — run the pipeline (`python3 run_pipeline.py`) and visually verify the dashboard as integration test.
- `EUR_TO_USD = 1.16` lives in `validate.py`; never redefine it.
- All monetary values in KUSD throughout the payload.
- Never redefine `L1`, `L1_SHORT`, `L2_PER_L1` globals in `dashboard-template.html`; extend them.
- `esc()` must wrap every data-derived string written to `innerHTML`.
- The `sah_l2_per_l1` indexed array (already in DATA) is the ground truth for L2 ordering; `sah_l3_per_l2` must be parallel to it.

---

### Task 1: ingest.py — capture L3 in coverage + build L3 hierarchy

**Files:**
- Modify: `ingest.py:374-388` (inside `build_coverage()`)
- Modify: `ingest.py:390` (after `build_coverage` definition, add new function)
- Modify: `ingest.py:584-586` (main() — call new function after build_coverage)
- Modify: `ingest.py:757-762` (main() output dict — add `sah_l3_per_l2` key)

**Interfaces:**
- Produces: `coverage[acct][l1]["l2"][l2_name]["l3"]` — `{l3_name: {"live": bool, "project": bool, "shelfware": bool}}`
- Produces: `build_l3_hierarchy(am)` → `{l1_name: {l2_name: [l3_name, ...]}}` (order of first appearance in AM)
- Produces: `data.json["sah_l3_per_l2"]` — the dict above, serialised as JSON

- [ ] **Step 1: Extend `build_coverage()` to track L3 inside L2 entries**

  In `ingest.py`, inside the `if l2_name:` block (currently lines 374–383), after `l2e["lpr_cnt"] += 1`, add:

  ```python
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
  ```

- [ ] **Step 2: Add `build_l3_hierarchy()` function after `build_coverage()` (around line 391)**

  ```python
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
  ```

- [ ] **Step 3: Call `build_l3_hierarchy()` in `main()` after `build_coverage()` call**

  After line 585 (`coverage, rise_accounts = build_coverage(am, sah_l1_names, product_name_map)`), add:

  ```python
      print("Building L3 hierarchy...")
      sah_l3_per_l2_dict = build_l3_hierarchy(am)
  ```

- [ ] **Step 4: Emit `sah_l3_per_l2` in the output dict**

  In `main()`, in the `output` dict (around line 761, after `"sah_hierarchy"`), add:

  ```python
          "sah_l3_per_l2": sah_l3_per_l2_dict,
  ```

- [ ] **Step 5: Smoke-test ingest**

  Run: `python3 ingest.py --am example-data/MW_MU_AM_2026-07-06.csv --am-tp example-data/MW_MU_AM_TP_2026-07-08.csv --iaa example-data/MW_MU_IAA_2026-07-06.csv --tao example-data/MW_MU_TAO_2026-08-17.csv --adrm example-data/MW_MU_ADRM_2026-07-06.csv --spi example-data/MW_MU_SPI_2026-07-06.csv --ref "reference-data/SAP_Industry_Solution_Reference.xlsx" --sah "reference-data/Copy of Solution Areas and Logical Products 2026 - update.xlsx" --out output/data.json`

  Then verify with python:
  ```python
  import json
  d = json.load(open("output/data.json"))
  l3 = d["sah_l3_per_l2"]
  print("L3 hierarchy keys:", list(l3.keys())[:3])
  # Pick a known L1 and L2 that should have L3s, e.g.:
  fsm = l3.get("Finance and Spend Management", {})
  for l2, l3s in list(fsm.items())[:3]:
      print(f"  {l2}: {l3s[:3]}")
  # Should print L3 names (not empty lists)
  ```

  Expected: non-empty L3 lists for at least one L1/L2 pair. If all lists are empty, `Solution Area Level 3` column may be named differently — check with `print(list(am.columns))` in a one-liner.

- [ ] **Step 6: Commit**

  ```bash
  git add ingest.py
  git commit -m "feat: capture L3 coverage in build_coverage; emit sah_l3_per_l2 in data.json"
  ```

---

### Task 2: build.py — add `l3s` compact field + `sah_l3_per_l2` DATA payload

**Files:**
- Modify: `build.py:65` — `compact_account()` signature + body
- Modify: `build.py:197-217` — `main()` (build indexed `sah_l3_per_l2`, pass to compact_account)
- Modify: `build.py:239-244` — DATA payload dict (add `sah_l3_per_l2`)

**Interfaces:**
- Consumes: `data["sah_l3_per_l2"]` — `{l1_name: {l2_name: [l3_names]}}` (from Task 1)
- Consumes: `sah_l2_per_l1` — already built at line 199
- Produces: `compact_account(...)["l3s"]` — `l3s[i][j][k]`: int 3/2/1/0
- Produces: `DATA.sah_l3_per_l2` — `[[[ l3_name, ...], ...], ...]` (2D indexed array parallel to `sah_l2_per_l1`)

- [ ] **Step 1: Add `sah_l3_per_l2` parameter to `compact_account()` and build `l3s`**

  Change the signature at line 65 from:
  ```python
  def compact_account(a, sah_l1, sah_l2_per_l1, tp_coverage=None, tp_name_map=None):
  ```
  to:
  ```python
  def compact_account(a, sah_l1, sah_l2_per_l1, tp_coverage=None, tp_name_map=None, sah_l3_per_l2=None):
  ```

  After the `l2s` / `l2_lpr_cnt` block (after line 85, before line 87 `tp_id = ...`), add:

  ```python
      # l3s[i][j][k]: 3=Live, 2=Project, 1=Shelfware, 0=None per L3 k under L2 j under L1 i
      l3s = []
      for i, l1 in enumerate(sah_l1):
          l2_dict = a["coverage"].get(l1, {}).get("l2", {})
          l1_l3s = []
          for j, l2 in enumerate(sah_l2_per_l1[i]):
              l3_dict = l2_dict.get(l2, {}).get("l3", {})
              l3_names = (sah_l3_per_l2 or [[]])[i][j] if sah_l3_per_l2 else []
              row = []
              for l3 in l3_names:
                  e = l3_dict.get(l3, {})
                  if e.get("live"):         row.append(3)
                  elif e.get("project"):    row.append(2)
                  elif e.get("shelfware"):  row.append(1)
                  else:                     row.append(0)
              l1_l3s.append(row)
          l3s.append(l1_l3s)
  ```

  Add `"l3s": l3s` to the returned dict (after `"l2_lpr_cnt": l2_lpr_cnt` around line 175):
  ```python
          "l3s":  l3s,
  ```

- [ ] **Step 2: Build indexed `sah_l3_per_l2` in `main()` and pass to `compact_account()`**

  After line 202 (`]`  — end of `sah_l2_per_l1` list comprehension), add:

  ```python
      l3_dict = data.get("sah_l3_per_l2", {})
      sah_l3_per_l2 = [
          [l3_dict.get(l1, {}).get(l2, []) for l2 in sah_l2_per_l1[i]]
          for i, l1 in enumerate(sah_l1)
      ]
  ```

  Change line 217 from:
  ```python
      compact_accounts = [compact_account(a, sah_l1, sah_l2_per_l1, tp_coverage, tp_name_map) for a in data["accounts"]]
  ```
  to:
  ```python
      compact_accounts = [compact_account(a, sah_l1, sah_l2_per_l1, tp_coverage, tp_name_map, sah_l3_per_l2) for a in data["accounts"]]
  ```

- [ ] **Step 3: Emit `sah_l3_per_l2` in DATA payload**

  In the payload dict (around line 241, after `"sah_l2_per_l1": sah_l2_per_l1`), add:
  ```python
          "sah_l3_per_l2": sah_l3_per_l2,
  ```

- [ ] **Step 4: Run build.py and verify**

  Run: `python3 build.py --data output/data.json --clusters output/clusters.json --out output/whitespace-analyzer.html`

  Verify with Python:
  ```python
  import json
  d = json.load(open("output/whitespace-analyzer.html").read().split("/*__DATA__*/")[1].split("/*__DATA_END__*/")[0]) if "/*__DATA__*/" in open("output/whitespace-analyzer.html").read() else None
  # OR simpler: check that output/whitespace-analyzer.html was generated without errors
  # Then open the file in a browser and check console for JS errors
  ```

  The pipeline should complete with exit code 0. No Python exceptions.

- [ ] **Step 5: Commit**

  ```bash
  git add build.py
  git commit -m "feat: add l3s compact field and sah_l3_per_l2 DATA payload to build.py"
  ```

---

### Task 3: dashboard — L3 second drill level

**Files:**
- Modify: `dashboard-template.html:1179` — add `L3_PER_L2` runtime global
- Modify: `dashboard-template.html:1288` — add `treemapDrillL2: null` to state
- Modify: `dashboard-template.html:684-689` — add L3 back button in Account Details header
- Modify: `dashboard-template.html:2061-2246` — `renderTopAccountsTable()` (3-mode logic)
- Modify: `dashboard-template.html:1984-2058` — `downloadAccountDetailsCSV()` (L3 branch)

**Interfaces:**
- Consumes: `DATA.sah_l3_per_l2` — `[[[l3_name, ...], ...], ...]` (from Task 2)
- Consumes: `a.l3s[i][j][k]` — int status (from Task 2)
- Consumes: `this.treemapDrillL1` — L1 index (existing state)
- Produces: `this.treemapDrillL2` — L2 index within the drilled L1, or null
- Produces: `L3_PER_L2[i][j]` — list of L3 names for L2 j under L1 i

- [ ] **Step 1: Add `L3_PER_L2` runtime global**

  In `dashboard-template.html`, at line 1179, after:
  ```js
  const L2_PER_L1 = DATA.sah_l2_per_l1 || L1.map(() => []);
  ```
  add:
  ```js
  const L3_PER_L2 = DATA.sah_l3_per_l2 || L1.map(() => []);
  ```

- [ ] **Step 2: Add `treemapDrillL2: null` to Vue data state**

  In `dashboard-template.html` at line 1288, after:
  ```js
        treemapDrillL1: null,  // L1 index currently drilled into on overview treemap, or null
  ```
  add:
  ```js
        treemapDrillL2: null,  // L2 index within drilled L1 for L3 drill, or null
  ```

- [ ] **Step 3: Add L3 back button to Account Details header**

  In `dashboard-template.html` at line 689, the current back button is:
  ```html
        <button v-if="filters.selectedL1[0]" style="font-size:.72rem;padding:.15rem .5rem;cursor:pointer;border:1px solid #ccc;border-radius:3px;background:#f5f5f5" @click="filters.selectedL1 = []">&#8592; All Solution Areas</button>
  ```

  Replace this with two conditional buttons:
  ```html
        <button v-if="treemapDrillL2 !== null" style="font-size:.72rem;padding:.15rem .5rem;cursor:pointer;border:1px solid #ccc;border-radius:3px;background:#f5f5f5" @click="treemapDrillL2 = null; $nextTick(renderTopAccountsTable)">&#8592; Back to L2</button>
        <button v-else-if="filters.selectedL1[0]" style="font-size:.72rem;padding:.15rem .5rem;cursor:pointer;border:1px solid #ccc;border-radius:3px;background:#f5f5f5" @click="filters.selectedL1 = []; treemapDrillL2 = null">&#8592; All Solution Areas</button>
  ```

  Also, reset `treemapDrillL2` when `treemapDrillL1` changes. Find the watcher for `filters.selectedL1` at line ~1634 which sets `treemapDrillL1`. After `this.treemapDrillL1 = null;` (line ~1641), add:
  ```js
          this.treemapDrillL2 = null;
  ```
  (in both the `if` and `else` branches)

  Also reset `treemapDrillL2 = null` in `clearAllFilters()` at line ~1729.

- [ ] **Step 4: Rewrite `renderTopAccountsTable()` for 3-mode logic**

  The function currently has two modes (isDrilled = L2 mode / normal). Extend to three:

  ```js
  renderTopAccountsTable() {
    const el = document.getElementById("top-accounts-table");
    if (!el) return;

    const drillIdx   = this.treemapDrillL1;   // L1 index, or null
    const drillL2Idx = this.treemapDrillL2;   // L2 index within drillIdx, or null
    const isDrilled  = drillIdx !== null;
    const isL3Drilled = isDrilled && drillL2Idx !== null;
  ```

  **Account set:** Keep existing logic: when `isDrilled`, use `filterAccountsWithoutL1`; else use `filteredAccounts`.

  **Gap/wsGap calculation:** When `isL3Drilled`, same as `isDrilled` (use `tao_l2` for drillIdx). This is correct because TAO data only exists at L2 granularity; L3 drill shows coverage status only.

  **Column headers:**
  - `isL3Drilled`: show L3 names: `const l3Names = (L3_PER_L2[drillIdx] || [])[drillL2Idx] || [];` → `l3Names.forEach(n => html += \`<th title="${esc(n)}">${esc(n)}</th>\`)`
  - `isDrilled` (and not L3): L2 column headers, now clickable to drill into L3:
    ```js
    const l2Names = L2_PER_L1[drillIdx] || [];
    l2Names.forEach((n, j) => {
      html += `<th class="acct-col-header-l2" data-l2="${j}" style="cursor:pointer" title="Drill into ${esc(n)}">${esc(n)} &#8595;</th>`;
    });
    ```
  - Normal mode: existing logic (L1 abbreviations, clickable).

  **Also in normal mode, add Pipe column headers after each L1:**
  ```js
  L1_SHORT.forEach((s, i) => {
    html += `<th class="acct-col-header" data-li="${i}" style="cursor:pointer" title="Filter by ${esc(L1[i])}">${esc(s)}</th>`;
    html += `<th title="${esc(L1[i])} Pipeline" style="font-size:.72rem">${esc(s)} Pipe</th>`;
  });
  ```

  **Cell rendering — isL3Drilled:**
  ```js
  if (isL3Drilled) {
    const l3Names = (L3_PER_L2[drillIdx] || [])[drillL2Idx] || [];
    const l3s = a.l3s && a.l3s[drillIdx] && a.l3s[drillIdx][drillL2Idx];
    l3Names.forEach((l3, k) => {
      const status = l3s ? (l3s[k] || 0) : 0;
      let cell = "", cellCls = "";
      if (this.accountTableView === "tao_gap" || this.accountTableView === "lpr_count") {
        // L3 has no TAO gap or LPR count — show coverage status only
        cell = `<span class="text-muted">–</span>`;
      } else {
        if (status >= 3)     cell = `<span class="ws-badge ws-badge--covered" title="${esc(l3)}: Covered">Covered</span>`;
        else if (status === 2) cell = `<span class="ws-badge ws-badge--project" title="${esc(l3)}: Project">Project</span>`;
        else if (status === 1) cell = `<span class="ws-badge ws-badge--shelfware" title="${esc(l3)}: Shelfware">Shelfware</span>`;
        else                   cell = `<span class="text-muted">–</span>`;
      }
      html += `<td data-idx="${navIdx}">${cell}</td>`;
    });
  }
  ```

  **Cell rendering — normal mode, add Pipe cell after each WS cell:**
  ```js
  // After the existing WS cell for L1 i:
  const pipeVal = (a.pipe && a.pipe[i]) || 0;
  let pipeCell = `<span class="text-muted">–</span>`;
  if (w) {  // w = effectiveWs(a)[i]
    if (pipeVal === 0) {
      pipeCell = `<span class="ws-badge ws-badge--whitespace">Whitespace</span>`;
    } else {
      pipeCell = `<span style="font-size:.8rem">${fmtUSD(pipeVal)}</span>`;
    }
  }
  html += `<td data-idx="${navIdx}">${pipeCell}</td>`;
  ```

  **Click handler for L2 drill-into-L3:**
  After the existing `el.querySelectorAll("th.acct-col-header")` event binding, add:
  ```js
  el.querySelectorAll("th.acct-col-header-l2").forEach(th => {
    th.addEventListener("click", () => {
      this.treemapDrillL2 = +th.dataset.l2;
      this.overviewCurrentPage = 1;
      nextTick(() => this.renderTopAccountsTable());
    });
  });
  ```

- [ ] **Step 5: Update `downloadAccountDetailsCSV()` with L3 branch**

  In `downloadAccountDetailsCSV()` (line 1984), after `const drillIdx = this.treemapDrillL1;` add:
  ```js
  const drillL2Idx = this.treemapDrillL2;
  const isL3Drilled = drillIdx !== null && drillL2Idx !== null;
  const isDrilled = drillIdx !== null && !isL3Drilled;
  ```

  Rebuild `tableAccounts` to use `filterAccountsWithoutL1` for both `isDrilled` and `isL3Drilled`. Change existing:
  ```js
  if (isDrilled) {
  ```
  to:
  ```js
  if (isDrilled || isL3Drilled) {
  ```
  (both L2-drill and L3-drill use the same population)

  For `colHeaders`, extend the ternary to three cases:
  ```js
  const colHeaders = isL3Drilled
    ? ((L3_PER_L2[drillIdx] || [])[drillL2Idx] || [])
    : isDrilled
      ? (L2_PER_L1[drillIdx] || [])
      : L1.flatMap((l, i) => [l, l + ' (Pipeline)']);
  ```

  For gap/wsGap calculation: same as `isDrilled` for `isL3Drilled`:
  ```js
  if (isDrilled || isL3Drilled) {
    const l2row = a.tao_l2 && a.tao_l2[drillIdx];
    if (l2row) l2row.forEach(t => { if (t && t.gap) totalGap += t.gap; });
    if (this.effectiveWs(a)[drillIdx]) wsGap = totalGap;
  }
  ```

  For cell generation, add L3 branch:
  ```js
  if (isL3Drilled) {
    const l3Names = (L3_PER_L2[drillIdx] || [])[drillL2Idx] || [];
    const l3s = a.l3s && a.l3s[drillIdx] && a.l3s[drillIdx][drillL2Idx];
    l3Names.forEach((_, k) => {
      const status = l3s ? (l3s[k] || 0) : 0;
      cells.push(status >= 3 ? 'Covered' : status === 2 ? 'Project' : status === 1 ? 'Shelfware' : '');
    });
  } else if (isDrilled) {
    // existing L2 branch (unchanged)
    ...
  } else {
    // normal mode: per-L1 WS + Pipe
    L1.forEach((_, i) => {
      const w = this.effectiveWs(a)[i]; const covLP = a.cov[i]; const covAny = a.cov_any[i];
      if (this.accountTableView === 'tao_gap') {
        const t = a.tao && a.tao[i]; cells.push(t && t.gap > 0 ? t.gap.toFixed(1) : '');
      } else if (this.accountTableView === 'lpr_count') {
        cells.push(a.cov_products && a.cov_products[i] ? a.cov_products[i].length : 0);
      } else {
        cells.push(covLP ? 'Covered' : covAny ? 'Shelfware' : w ? 'Whitespace' : '');
      }
      // Pipeline column
      const pipeVal = (a.pipe && a.pipe[i]) || 0;
      cells.push(w ? (pipeVal > 0 ? pipeVal.toFixed(1) : 'Whitespace') : '');
    });
  }
  ```

- [ ] **Step 6: Run pipeline and test in browser**

  ```bash
  python3 run_pipeline.py
  ```

  Open `output/whitespace-analyzer.html` in a browser. Test:
  1. In Account Details (normal mode), verify there are two columns per Solution Area — the second column (e.g. "DAI Pipe") shows "Whitespace" or a KUSD value for whitespace accounts, "—" for covered accounts.
  2. Click a Solution Area column header → L2 drill. Verify L2 column names appear, each with a down-arrow "↓".
  3. Click an L2 column header → L3 drill. Verify L3 names appear as columns.
  4. Click "← Back to L2" → returns to L2 drill view.
  5. Click "← All Solution Areas" → returns to normal mode.
  6. Click Export CSV in each drill mode; verify the downloaded file has correct headers and data.
  7. Check browser console — no JavaScript errors.

- [ ] **Step 7: Commit**

  ```bash
  git add dashboard-template.html
  git commit -m "feat: add L3 drill level and WS×Pipeline columns to Account Details table"
  ```

---

### Task 4: Run the full pipeline and final QA

**Files:** none — verification only

- [ ] **Step 1: Full pipeline run with example data**

  ```bash
  python3 run_pipeline.py
  ```

  Expected: exit code 0, no FAIL validations. WARN is acceptable.

- [ ] **Step 2: Verify data integrity in browser**

  Open `output/whitespace-analyzer.html`.

  Check list:
  - [ ] Normal mode: every L1 has two header columns (e.g. "FSM" and "FSM Pipe")
  - [ ] Covered accounts: both WS and Pipe columns show "—"
  - [ ] Whitespace accounts with no pipeline: WS column = "Whitespace", Pipe column = "Whitespace"
  - [ ] Whitespace accounts with pipeline > 0: WS column = "Whitespace", Pipe column = KUSD value
  - [ ] Click L1 header → L2 drill; L2 column headers show "↓" and are clickable
  - [ ] Click L2 header → L3 drill; L3 names appear as columns
  - [ ] L3 cells show Covered/Project/Shelfware/— correctly
  - [ ] "← Back to L2" button visible in L3 mode; returns to L2 mode
  - [ ] "← All Solution Areas" button visible in L2 mode (but not L3 mode); returns to normal
  - [ ] Export CSV works in all 3 modes (normal, L2-drill, L3-drill)
  - [ ] No JS errors in browser console

- [ ] **Step 3: Commit final state**

  ```bash
  git add -A
  git status  # verify only expected files changed
  git commit -m "feat: complete L3 drill + WS×Pipeline — pipeline and dashboard fully wired"
  ```
