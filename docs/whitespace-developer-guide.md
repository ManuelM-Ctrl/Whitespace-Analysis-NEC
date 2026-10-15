# Understanding the Whitespace Analyzer (Plain-Language Guide for Builders)

*You don't need to code to build with this tool. You need to understand how it's organized so you can ask for changes clearly and spot when something's off. This guide teaches you the real names the tool uses — the same words the AI uses — so you're always speaking the same language.*

## 1. The whole thing in one sentence

A three-script Python pipeline reads six source files, crunches them, and writes a single self-contained HTML file that runs as an interactive sales dashboard in your browser with no installation.

## 2. The factory floor — four scripts, one pipeline

The pipeline always runs in the same order. Each script hands its output to the next one.

| Script | What it does | Output |
|---|---|---|
| **ingest.py** | Reads all source files; builds coverage, whitespace, and financial indexes | `data.json` |
| **analyze.py** | Groups accounts into clusters by shared coverage + whitespace pattern | `clusters.json` |
| **build.py** | Packs data, fetches libraries, and assembles the dashboard HTML | `whitespace-analyzer.html` |
| **run_pipeline.py** | Runs all three scripts in order; one command does everything | — |

`validate.py` is a helper shared by all three — it runs quality checks and reports PASS / WARN / FAIL. A FAIL stops the pipeline. A WARN lets it continue but flags the issue.

The quick way to run everything:
```
python3 run_pipeline.py --input-dir input/2026-08-10/
```

## 3. The dashboard — eight sections

The output HTML is a Vue 3 web app. Its code is organized into **eight sections, always in the same order**. Knowing the names tells the AI exactly where to make your change.

| Section | What it does | When you'd touch it |
|---|---|---|
| **Styles** | Colors, spacing, fonts | "Make the whitespace cells a brighter orange" |
| **Markup** | The page frame and panel layout | Rarely — the fixed shell |
| **Globals** | The full data payload injected at build time | Never edited directly — change `ingest.py` or `build.py` |
| **Computed** | Calculated views of the data (the source of truth for display) | Adding a new filter, changing KPI math |
| **Methods** | Helper functions like `effectiveWs`, `esc`, formatters | Changing how shelfware is handled, number formatting |
| **Render** | Functions that draw each panel to the screen | "Show the account's revenue band in the heatmap tooltip" |
| **Charts** | Chart.js instances (treemap, bubble, bar) | "Add a new bar to the pipeline chart" |
| **Events / Vue** | Reacting to button clicks, filter changes, tab switches | "Clicking a cluster row should highlight its accounts" |

The four you'll touch most are **Styles, Computed, Render, and Events / Vue.**

## 4. The single most important concept: `filteredAccounts`

The dashboard holds data for every account in the territory. But almost nothing on screen shows *all* of them — you've always filtered by market unit, industry, solution area, or something else.

`filteredAccounts` is a computed property that applies every active filter at once and returns only the matching accounts. **Every render method and KPI reads from `filteredAccounts`, never from `DATA.accounts`.**

> Think of `DATA.accounts` as the raw data warehouse — everything, unfiltered. `filteredAccounts` is the report that the whole dashboard is built from. If a render method reaches past it into the warehouse, filters stop working for that panel, and the numbers on screen won't match each other.

## 5. How data flows — one-way, forward only

```
Source files  →  ingest.py  →  data.json  →  analyze.py  →  clusters.json
                                                                    ↓
                                                              build.py  →  whitespace-analyzer.html
                                                                    ↓
                                          Browser loads HTML  →  DATA global  →  filteredAccounts  →  Render
```

Data only flows **forward**. The pipeline scripts write; the dashboard reads. Nothing in the dashboard changes `data.json`. Nothing in `build.py` changes `clusters.json`.

> **Why this matters:** if something looks wrong in the dashboard, there are only two places to look — either the data going *in* (a pipeline script) or the code doing the *display* (a dashboard section). It never flows backward, so you always know which direction to look.

## 6. Two more rules that keep things correct

**Rule: use `effectiveWs(a)`, not `a.ws`**

Every account has a `ws` array marking which solution areas it doesn't cover. But shelfware is a special case — an account with shelfware-only coverage looks "not covered" in `ws`, but it's not a real sales opportunity. `effectiveWs(a)` corrects for this by nulling out those cells.

> Always call `effectiveWs(a)` when you want to know whether an account has whitespace in a given solution area. Using `a.ws` directly will overcount opportunities.

**Rule: all money is KUSD**

Currency conversion happens exactly once — inside `ingest.py` when the data is first loaded. Everything that comes out is in thousands of US dollars (KUSD). The dashboard never converts currency; it always just reads KUSD.

> If you ever see a `× 1.16` or `÷ 1000` in dashboard code, that's a bug. The conversion already happened in the pipeline.

## 7. Naming — just enough to recognize things

| You'll see… | It means… |
|---|---|
| `DATA` | The full payload — all accounts, clusters, SAH hierarchy |
| `filteredAccounts` | Accounts matching the current filters — the source of truth for display |
| `effectiveWs(a)` | Whitespace for account `a`, with shelfware-only coverage excluded |
| `esc(str)` | HTML-safe version of a string — must wrap any data value shown in innerHTML |
| SAH / L1 / L2 | Solution Area Hierarchy; L1 = top level (e.g. "Finance and Spend Management"), L2 = sub-level |
| KUSD | Thousands of US dollars — all monetary values in the dashboard |
| `gap_kusd` | The outside-in wallet opportunity gap for this account × solution area |
| `cov[i]` | Whether the account has live/project coverage in solution area `i` |
| `cov_any[i]` | Whether the account has any coverage (incl. shelfware) in solution area `i` |
| `ws[i]` | Whether the account has whitespace in solution area `i` |
| `is_p` | Whether the account is a prospect (no AM coverage at all) |
| IAA | The master account list — the source of truth for which accounts exist |
| AM | Adoption Monitor — source of coverage data |
| TAO | Outside-in wallet and gap metrics |
| ADRM | Internal pipeline forecast |
| SPI | Planned pipeline |

## 8. The four things you never break

If you remember nothing else:

1. **Only `filteredAccounts` feeds the display** — never read `DATA.accounts` directly in a render method.
2. **Always use `effectiveWs(a)`, not `a.ws`** — shelfware-only coverage is not real whitespace.
3. **Money is always KUSD** — no currency conversions in dashboard code.
4. **Wrap data strings in `esc()`** — any account name, solution area, or industry value written into innerHTML must be escaped.

Everything else is detail. These four are the soul of the tool.
