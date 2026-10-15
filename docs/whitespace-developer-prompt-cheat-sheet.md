# Whitespace Analyzer — Prompt Cheat-Sheet
*Keep this next to you. You describe the outcome; the AI writes the code.*

---

## The 4 golden rules (say these when it matters)

| # | Rule | Plain meaning |
|---|---|---|
| 1 | **`filteredAccounts` feeds the display** | Every render method reads from the filtered list, never from `DATA.accounts` directly. |
| 2 | **`effectiveWs(a)`, not `a.ws`** | Always use the method — it correctly handles shelfware-only coverage. |
| 3 | **Money is always KUSD** | Currency conversion happened once in `ingest.py`. No conversions in dashboard code. |
| 4 | **`esc()` every data string** | Any account name, product, or industry value written into innerHTML must be wrapped in `esc()`. |

> **Magic closing line for any dashboard request:**
> *"…and confirm all render methods still read from `filteredAccounts`, `effectiveWs(a)` is used for whitespace checks, and all data strings going into innerHTML are wrapped in `esc()`."*

---

## How to write a good request

**① Describe what you see + what you want instead**
> *"In the heatmap, hovering a whitespace cell shows the gap amount. I also want it to show the account's revenue band."*

**② Name the script or section if you know it**
> *"In the Render section, in `renderHeatmap`, add the revenue band to the tooltip."*

**③ Say what should NOT change**
> *"Add the revenue band to the tooltip — but don't change how the cell colors or click behavior work."*

**④ For anything involving filters or KPIs, restate rule #1**
> *"Add a new filter for Revenue Band — it should narrow `filteredAccounts` like the other filters do."*

---

## Which script or section is my change in?

**Pipeline changes** (affect the data, require re-running the pipeline):

| I want to change… | Script | Example |
|---|---|---|
| Which accounts are included / excluded | **ingest.py** | "Exclude accounts in the Shell sales office" |
| How coverage or whitespace is calculated | **ingest.py** | "Count shelfware as coverage for SCM only" |
| How clusters are formed | **analyze.py** | "Require at least 3 shared L2s to form a cluster" |
| The data baked into the HTML | **build.py** | "Add the account's SIC code to the compact object" |
| Data quality checks | **validate.py** | "Warn if more than 10% of accounts have no TAO data" |

**Dashboard changes** (affect the display, edit `dashboard-template.html` then rebuild):

| I want to change… | Section | Example |
|---|---|---|
| Colors, spacing, fonts | **Styles** | "Make prospect rows a lighter gray" |
| A filter, KPI, or derived value | **Computed** | "Add a filter for Archetype" |
| How a number or label is formatted | **Methods** | "Show gap in millions instead of thousands" |
| What gets drawn in a panel | **Render** | "Show the L2 breakdown in the account detail view" |
| A chart | **Charts** | "Add a donut chart showing whitespace by L1" |
| What happens when you click something | **Events / Vue** | "Clicking a cluster name selects all its accounts" |

---

## Say it like this (copy these patterns)

| Instead of… | Say… |
|---|---|
| "Make it better" | "The cluster list is hard to scan — group clusters by whitespace L1." |
| "It's broken" | "After I change the Industry filter, the KPI totals don't update — they should recalculate from `filteredAccounts`." |
| "Fix the numbers" | "The total gap in the KPI bar doesn't match the sum of gaps in the heatmap — they should use the same source." |
| "Add currency" | "Show the gap in millions (e.g. $4.2M) — the value is already in KUSD so divide by 1000, no conversion needed." |

---

## Red flags to report (you can now name them)

- **A panel doesn't respond to filters** → rule #1 broken — that render method is reading `DATA.accounts` instead of `filteredAccounts`.
- **Shelfware accounts appear as whitespace opportunities** → rule #2 broken — code is reading `a.ws` instead of calling `effectiveWs(a)`.
- **Account names or product names show garbled characters or broken HTML** → rule #4 broken — a data string is being written into innerHTML without `esc()`.
- **KPI total doesn't match the table sum** → the two places are reading different account lists; one needs to switch to `filteredAccounts`.
- **Pipeline runs but the dashboard shows old data** → the HTML wasn't rebuilt after the pipeline — run `build.py` (or the full `run_pipeline.py`).

---

## Quick decoder

| Word | Means |
|---|---|
| `DATA` | The full payload baked into the HTML — all accounts, clusters, SAH hierarchy |
| `filteredAccounts` | Accounts matching active filters — source of truth for all display |
| `effectiveWs(a)` | Whitespace array for account `a`, shelfware-only cells nulled out |
| `esc(str)` | HTML-safe string — required before any data value goes into innerHTML |
| SAH | Solution Area Hierarchy — the product taxonomy (L1 → L2 → L4) |
| L1 / L2 | Hierarchy levels; L1 = top (e.g. "Finance and Spend Management"), L2 = sub-level |
| KUSD | Thousands of US dollars — all monetary values |
| `gap_kusd` | Outside-in wallet opportunity gap |
| `cov[i]` | Live/project coverage in solution area `i` |
| `ws[i]` | Whitespace (no live/project coverage) in solution area `i` |
| `is_p` | Account is a prospect — no AM coverage at all |
| IAA | Account master list |
| AM / AM-TP | Adoption Monitor (coverage); AM-TP is the top-parent version |
| TAO | Outside-in wallet and gap metrics |
| ADRM | Internal pipeline forecast |

---

*If a request would change how whitespace is defined, how clusters are formed, or what counts as a currency — flag it as a big decision before building. Those are philosophy changes that affect everything downstream.*
