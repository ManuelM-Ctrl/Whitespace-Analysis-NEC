# Specs Guide — HTML Dashboard Changes
 
## Context

We are modifying a dashboard built in HTML (using Claude Code).

The changes are grouped into two areas: the **Account Details** table and the **Top Filters**.
 
> **Note to developer:** Do not modify styles, general layout, or any logic unrelated to the points described below. Preserve the existing code structure and conventions.
 
---
 
## 1. "Account Details" Table
 
### 1.1 Pipeline Whitespace when value is 0

**Current behavior:** When the pipeline value is `0`, the *whitespace* column displays a dash (`-`).
 
**Expected behavior:** When `pipeline == 0` (strict comparison with zero), the cell should display the **"whitespace"** title/label instead of the dash.
 
**Null / empty value handling:**

- For **text columns**: `null`, `undefined`, or empty values must remain as `"null"`.

- For **numeric columns**: `null`, `undefined`, or empty values must be treated as `0` (and therefore display the "whitespace" label as described above).
 
**Acceptance criteria:**

- [ ] If `pipeline === 0` → display the "whitespace" text/label.

- [ ] If `pipeline !== 0` → keep the current behavior.

- [ ] For text columns, `null` / `undefined` / empty values remain as `"null"`.

- [ ] For numeric columns, `null` / `undefined` / empty values are treated as `0`.
 
---
 
### 1.2 Duplicate accounts

**Problem:** The table is showing duplicate accounts.
 
**Goal:** Investigate and fix the root cause of the duplication.
 
**Unique key:** The column that uniquely identifies an account is **`Planning Entity ID`**.
 
**Tasks:**

- [ ] Identify the source of the duplication (join/merge of datasets? multiple rows per account in the source? missing grouping/deduplication?).

- [ ] Apply deduplication by `Planning Entity ID` or fix the data-joining logic so that each `Planning Entity ID` appears only once.

- [ ] Briefly document in a comment the identified cause and the applied solution.
 
**Acceptance criteria:**

- [ ] Each `Planning Entity ID` appears only once in the table.

- [ ] Totals/aggregates (including pipeline) reflect correct values without double counting.
 
---
 
## 2. Top Filters — Change data source from TAO to IAA Account Master
 
**Context:** Currently, the following filters pull their values from the **TAO** source. They must instead pull their values from the corresponding columns in the **IAA Account Master**.
 
**Exception — Segment:** The `Segment` filter must **not** come directly from the IAA. It must be **calculated** based on the `IAC` field (which comes from the IAA). See the mapping rules in section 2.1.
 
| # | Filter       | Current source (TAO) | New source (IAA Account Master)          |

|---|--------------|----------------------|------------------------------------------|

| 1 | Industry     | TAO column           | `Industry`                        |

| 2 | Segment      | TAO column           | **Calculated from IAC** (see section 2.1)|

| 3 | RBC          | TAO column           | `RBC: Current`                        |

| 4 | Archetype    | TAO column           | `PE Agg Archetype: Current`                        |

| 5 | IAC          | TAO column           | `IAC (Engagement Model): Current`                        |

| 6 | Revenue Band | TAO column           | `Revenue Band`                        |
 
> **Note:** The exact IAA Account Master column names will be filled in manually by our team. Please leave clearly marked placeholders (e.g., `<IAA column TBD>`) so they can be easily located and replaced.
 
**Tasks:**

- [ ] Repoint the data source of each listed filter (except Segment) from TAO to the corresponding column in the IAA Account Master.

- [ ] Implement `Segment` as a calculated field derived from `IAC` (see section 2.1).

- [ ] Ensure the unique options for each filter are generated from the new source (or calculated values, in the case of Segment).

- [ ] Verify that filtering still applies correctly to the data shown in the table.

- [ ] Keep the order, visible label, and style of each filter exactly as they are today.
 
**Acceptance criteria:**

- [ ] Each filter (except Segment) displays values sourced from the IAA Account Master.

- [ ] Segment displays calculated values according to the mapping in section 2.1.

- [ ] When a value is selected, the table and other components filter correctly.

- [ ] No residual references to TAO remain in these 6 filters.
 
---
 
### 2.1 Segment — Calculation logic based on IAC
 
The `Segment` field must be derived from the `IAC` value (sourced from the IAA Account Master) using the following mapping:
 
| IAC value        | Resulting Segment |

|------------------|-------------------|

| `C-Digital`      | `Corporate`       |

| `C-Field`        | `Corporate`       |

| `E-High Touch`   | `Enterprise`      |

| `E-SCP`          | `Enterprise`      |

| `Partner Driven` | `Partner Driven`  |

| Any other value / empty / `null` | `Null` |
 
**Rules:**

- If `IAC` is `C-Digital` or `C-Field` → `Segment = "Corporate"`.

- If `IAC` is `E-High Touch` or `E-SCP` → `Segment = "Enterprise"`.

- If `IAC` is `Partner Driven` → `Segment = "Partner Driven"` (unchanged).

- If `IAC` is empty, `null`, or any value not listed above → `Segment = "Null"`.
 
**Acceptance criteria:**

- [ ] Segment values are computed exactly according to the mapping table above.

- [ ] Unmapped, empty, or `null` IAC values result in `Segment = "Null"`.

- [ ] The Segment filter options are generated from the calculated values (not raw IAC values).
 
---
 
## General considerations

- Do not break the relationship between filters and the table when changing the data source.

- Verify that the data source change (item 2) does not reintroduce the duplicate issue (item 1.2).

- Test all changes together to avoid regressions.
 