# Whitespace Analyzer — How to Make a Change (Builder's Development Process)

*You don't write code. You describe outcomes, guide the AI, and shepherd the change through review. This guide walks you through the whole journey — while spending as few LLM tokens as possible, because tokens are a shared, limited budget.*

**Before you start, keep these open:**
- The **Prompt Cheat-Sheet** (the 4 golden rules and how to phrase requests)
- The **Plain-Language Guide** (filteredAccounts, effectiveWs, the eight dashboard sections, the pipeline scripts)
- `CLAUDE.md` (already loaded automatically — don't re-paste it)

---

## First, the token mindset (read this once)

Every time the AI reads or writes text, it spends tokens from a shared quota. You waste tokens mostly by making the AI **re-read things it doesn't need**. Four habits prevent almost all the waste:

| Habit | Why it saves tokens |
|---|---|
| **Distinguish pipeline changes from dashboard changes** | A dashboard-only change doesn't need the pipeline re-explained. A pipeline change doesn't need the render sections re-explained. |
| **Don't re-paste the rules every time** | `CLAUDE.md` is read automatically. The golden rules and architecture are already known — reference them by name. |
| **Get the plan right before building** | A wrong direction caught in Step 2 (cheap text) avoids a rebuild in Step 4 (expensive code). |
| **One focused task per prompt** | Long, rambling threads carry all their history forward and re-cost it on every reply. Finish a task, start fresh. |

> **Rule of thumb:** if you're about to paste something the AI has seen before, stop — point to it by name instead.

---

## Step 0 — Frame the change (60 seconds, do this every time)

Decide what kind of change this is. It sets the path *and* the token cost.

| Kind | Meaning | Example | Where the work happens |
|---|---|---|---|
| **Display tweak** | Look, wording, formatting | "Show gap in millions instead of thousands" | Dashboard only (`dashboard-template.html` → rebuild) |
| **New dashboard feature** | New panel, filter, or behavior | "Add a Revenue Band filter" | Dashboard only |
| **Data change** | Different accounts, metrics, or calculations | "Exclude Shell sales office accounts" | Pipeline (`ingest.py`) → full pipeline re-run |
| **Philosophy change** | Changes a golden rule or core definition | "Count shelfware as live coverage" | Escalate — don't build |

**If it's a philosophy change, stop and escalate to the reviewer.** Everything else, continue.

**Display tweak or new dashboard feature?** You can often skip a full pipeline run — just edit the template and rebuild:
```
python3 build.py --data output/data.json --clusters output/clusters.json --out output/whitespace-analyzer.html
```

**Data change?** You must run the full pipeline so `data.json` reflects the new logic:
```
python3 run_pipeline.py --input-dir input/2026-08-10/
```

---

## Step 1 — Turn a request into a full user story

Turn a vague ask (*"The cluster list is hard to read"*) into a clear story, using the AI as your interviewer.

> **As a** market unit manager, **I want** the cluster list sorted by total whitespace gap descending by default, **so that** the highest-opportunity clusters are always at the top without manual sorting.
>
> **Done when:** clusters render in gap-descending order on load; the sort survives filter changes; existing sort/click behaviors are unchanged.

**Prompt to use:**
> *"Help me turn this request into a user story (As-a / I-want / So-that) plus 3–5 'Done when' criteria. Ask clarifying questions first. Assume the golden rules in CLAUDE.md — no need to restate them."*

**Token tip:** *"no need to restate them"* stops the AI from echoing the whole architecture back at you. This step is all cheap text — iterate here until the story is sharp.

---

## Step 2 — Propose the spec + implementation plan (reviewed *before* building)

**The most important step, and the cheapest place to be wrong.**

**Part A — What changes:**
- Which behavior or data definition changes.
- Exact "Done when" lines — one per acceptance criterion.
- Any change to the data shape (new field in the compact account object, new key in clusters.json, etc.) — these require pipeline changes in addition to dashboard changes.

**Part B — Where the change lives (plain language):**
- **Pipeline scripts** affected (if any) and what each one does differently.
- **Dashboard sections** affected — name each section (Styles, Computed, Render, etc.).
- Confirmation it honors the four golden rules.
- Which docs need syncing (`CLAUDE.md`, the guides).

**Part C — Why this approach:**
- One sentence: why this approach over the obvious alternative(s).
- If there's only one sensible way to do it, say so — that's still an answer.
- If the approach adds a new field, explain why rather than extending an existing one. If it modifies an existing field, explain why rather than adding a new one.

> This is the design checkpoint. A plan that says *what* changes but not *why this way* gives the reviewer nothing to push back on.

**Prompt to use:**
> *"Draft (A) a plain-language description of what changes — behaviors, data shape, 'Done when' lines — (B) a plan listing which pipeline scripts and which dashboard sections are affected, with a note on how each changes, and flag any golden-rule impact — and (C) one sentence explaining why this approach was chosen over the alternatives."*

**Get reviewer sign-off before Step 3.** A plan costs almost nothing to revise; rebuilt code costs much more.

---

## Step 3 — Create the feature branch

Isolate your work from the live tool on `main`.

- **Branch name:** kebab-case, prefixed `feat/`, `fix/`, or `docs/` — e.g., `feat/revenue-band-filter`.
- Create it in the GitHub web interface; no local tools needed. **Never work on `main`.**

---

## Step 4 — Implement the change (spend tokens here carefully)

Guide the AI to make the change **on your branch**, using the section names from your approved plan.

**Token-frugal building:**
- **Name the section, not the whole file.** *"In the Computed section, update `filteredAccounts` to also filter by Revenue Band…"* — the AI reads only that part.
- **Reference rules by name, don't re-explain them.** *"Honor golden rule #1 — the new filter must narrow `filteredAccounts`, not filter inside the render method."*
- **Build one "Done when" at a time.** Check it; move on. Small asks = small responses.
- **End build requests with the magic closing line:**
  > *"…and confirm all render methods still read from `filteredAccounts`, `effectiveWs(a)` is used for whitespace checks, and all data strings going into innerHTML are wrapped in `esc()`."*

**Test cheaply — open the HTML in your browser.** After a dashboard change, rebuild with `build.py` and open the file. Check:
1. The new behavior works.
2. The KPI totals still match the panel sums.
3. The filters still narrow every panel (including the new one).
4. Nothing else looks broken.

This costs *zero tokens* — you're clicking, not prompting. Always prefer click-to-verify over asking the AI to explain.

**If you changed a pipeline script,** run the full pipeline and check the validation report. A WARN is fine; a FAIL must be resolved before continuing.

**Update the docs in the same branch** — `CLAUDE.md` and the guides if behavior changed. A behavior change with no doc update is not done.

---

## Step 5 — Open a pull request (PR)

A PR asks to merge your branch into `main` and shows the reviewer exactly what changed.

**Include in the PR description:**
- Links to the **user story** and **approved proposal** from Steps 1–2.
- The **"Done when" checklist**, each item checked, with how you verified it (e.g., "opened in browser, KPIs matched").
- **Docs updated:** `CLAUDE.md`, guides (if applicable).
- **Golden-rules confirmation:** one line — *"All four golden rules honored: filteredAccounts, effectiveWs, KUSD, esc()."*

**Two reviewers look at your PR:**
1. **The automated pr-bot** runs a pre-review check first. Read its comments; fix or reply to each. **Don't request human review until the bot is green or fully answered.**
2. **The human reviewer** does the real approval.

**Token tip:** let the AI write the PR description from the user story and proposal you already have — don't re-derive the change from the code.

---

## Step 6 — Respond to review feedback

- **Read each comment fully first.** Ask the AI to explain one in plain language only if you genuinely need it (that costs tokens — try to read it yourself first).
- **For a requested change:** guide the AI on the same branch, naming the section again. Re-run the free browser test.
- **If a comment would break a golden rule:** reply and explain rather than silently changing it — that's a philosophy change and needs escalation.
- **Reply to every comment**, even just "Fixed in latest commit," so the reviewer knows what's ready.

The reviewer merges. Delete the branch. Done.

---

## The whole flow at a glance

```
Token mindset → name sections, don't re-paste rules, plan before building, one task per prompt

0. Frame it     → display tweak / data change / philosophy? (escalate philosophy)
                  dashboard-only → rebuild with build.py
                  data change    → full pipeline run
1. User story   → As-a / I-want / So-that + "Done when"   (cheap text — iterate here)
2. Proposal     → what changes + which sections ── REVIEWER SIGN-OFF before building ──
3. Branch       → feat/ | fix/ | docs/, never main
4. Implement    → name the section, reference rules by name, test in browser (free),
                  run pipeline validation if data changed, update docs
5. Open PR      → story + proposal + "Done when" checklist; bot checks first
6. Review       → reply to every comment; escalate golden-rule conflicts
                → reviewer merges → delete branch → done
```
