"""
validate.py — pipeline validation checks for the Whitespace Analysis pipeline

Called at the end of each script stage. Hard failures raise ValidationError,
which callers catch to decide whether to abort or continue (soft-block mode).

Check IDs match the validation plan:
  I-1 … I-8  : Input preflight (ingest.py)
  J-1 … J-7  : Join & coverage integrity (ingest.py post-join)
  B-1 … B-8  : Business logic correctness (ingest.py post-assembly)
  O-1 … O-7  : Output structure integrity (ingest.py / analyze.py)
  D-1 … D-4  : Dashboard KPI cross-check (build.py post-compact)
"""

from __future__ import annotations

import pandas as pd


from utils import EUR_TO_USD, strip_code

# Thresholds for join-coverage warnings
AM_IAA_JOIN_THRESHOLD = 0.80   # J-1: >= 80% of AM IDs should appear in IAA
IAA_AM_JOIN_THRESHOLD = 0.60   # J-2: >= 60% of IAA IDs should appear in AM
TAO_COVERAGE_THRESHOLD = 0.50  # J-3: >= 50% of non-prospects should have >= 1 TAO row

# Currency spot-check tolerance (B-7)
CURRENCY_SPOT_N = 5                 # number of rows to spot-check
CURRENCY_TOLERANCE = 0.011          # relative tolerance (1.1%)


class ValidationError(Exception):
    """Raised for hard-fail checks. Message includes the check ID."""


class ValidationReport:
    """Accumulates check results and prints a summary."""

    def __init__(self):
        self.results: list[tuple[str, str, str]] = []  # (status, id, message)

    def record(self, status: str, check_id: str, message: str):
        self.results.append((status, check_id, message))
        print(f"  [{status}] {check_id}: {message}")

    def passed(self, check_id: str, message: str):
        self.record("PASS", check_id, message)

    def warned(self, check_id: str, message: str):
        self.record("WARN", check_id, message)

    def failed(self, check_id: str, message: str):
        self.record("FAIL", check_id, message)
        raise ValidationError(f"{check_id}: {message}")

    @property
    def fail_count(self) -> int:
        return sum(1 for s, _, _ in self.results if s == "FAIL")

    @property
    def warn_count(self) -> int:
        return sum(1 for s, _, _ in self.results if s == "WARN")

    def summary(self) -> str:
        total = len(self.results)
        return f"{total} checks: {self.fail_count} failed, {self.warn_count} warnings"


# ---------------------------------------------------------------------------
# Layer 1 — Input preflight
# ---------------------------------------------------------------------------

def check_input_preflight(
    am: pd.DataFrame,
    iaa: pd.DataFrame,
    tao: pd.DataFrame,
    adrm: pd.DataFrame,
    ref_df: pd.DataFrame,
    report: ValidationReport,
):
    """I-1 … I-8: Verify required columns exist and basic sanity."""

    # I-1: AM required columns
    am_required = {
        "Planning Entity ID",
        "Solution Area Level 1",
        "Max / Highest Adoption State",
        "Standard Industry Code (Key + Text)",
    }
    missing_am = am_required - set(am.columns)
    if missing_am:
        report.failed("I-1", f"AM missing required columns: {sorted(missing_am)}")
    else:
        report.passed("I-1", f"AM required columns present ({len(am)} rows)")

    # I-2: IAA required columns
    iaa_required = {"Planning Entity ID", "Market Unit", "Sales Office: Current", "Sales Group: Current"}
    missing_iaa = iaa_required - set(iaa.columns)
    if missing_iaa:
        report.failed("I-2", f"IAA missing required columns: {sorted(missing_iaa)}")
    else:
        report.passed("I-2", f"IAA required columns present ({len(iaa)} rows)")

    # I-3: TAO required columns
    tao_required = {"Planning Entity ID", "Solution Area", "Sub Solution Area", "GAP_TO_ESTIMATED_WALLET", "ESTIMATED_WALLET_EUR"}
    missing_tao = tao_required - set(tao.columns)
    if missing_tao:
        report.failed("I-3", f"TAO missing required columns: {sorted(missing_tao)}")
    else:
        report.passed("I-3", f"TAO required columns present ({len(tao)} rows)")

    # I-4: ADRM required columns
    adrm_required = {"Planning Entity ID", "Solution Area L2", "Total @ FC"}
    missing_adrm = adrm_required - set(adrm.columns)
    if missing_adrm:
        report.failed("I-4", f"ADRM missing required columns: {sorted(missing_adrm)}")
    else:
        report.passed("I-4", f"ADRM required columns present ({len(adrm)} rows)")

    # I-5: Reference sheet columns
    ref_required = {"Industry", "Priority", "Tag"}
    missing_ref = ref_required - set(ref_df.columns)
    if missing_ref:
        report.failed("I-5", f"Reference sheet missing required columns: {sorted(missing_ref)}")
    else:
        report.passed("I-5", f"Reference sheet columns present ({len(ref_df)} rows)")

    # I-6: Non-empty source files
    empty_files = [label for label, df in [("AM", am), ("IAA", iaa), ("TAO", tao), ("ADRM", adrm)] if len(df) == 0]
    if empty_files:
        report.failed("I-6", f"{', '.join(empty_files)} file(s) have zero rows after filtering")
    else:
        report.passed("I-6", "AM, IAA, TAO, and ADRM all non-empty after filtering")

    # I-7: TAO gap values >= 0
    if "GAP_TO_ESTIMATED_WALLET" in tao.columns:
        gap_col = pd.to_numeric(tao["GAP_TO_ESTIMATED_WALLET"], errors="coerce")
        neg_count = int((gap_col < 0).sum())
        if neg_count > 0:
            report.warned("I-7", f"{neg_count} TAO rows have negative gap values")
        else:
            report.passed("I-7", "All TAO gap values >= 0")

    # I-8: ADRM Total @ FC is numeric
    if "Total @ FC" in adrm.columns:
        raw_col = pd.to_numeric(adrm["Total @ FC"], errors="coerce")
        non_numeric = int(raw_col.isna().sum()) - int(adrm["Total @ FC"].isna().sum())
        if non_numeric > 0:
            report.warned("I-8", f"{non_numeric} ADRM rows have non-numeric 'Total @ FC' (coerced to 0)")
        else:
            report.passed("I-8", "All ADRM 'Total @ FC' values are numeric")


# ---------------------------------------------------------------------------
# Layer 2 — Join & coverage integrity
# ---------------------------------------------------------------------------

def check_join_integrity(
    am_ids: set[str],
    iaa_ids: set[str],
    non_prospect_ids: set[str],
    tao_ids: set[str],
    am_l1_names: set[str],
    canonical_l1_names: set[str],
    tao_industries: set[str],
    known_crosswalk_keys: set[str],
    report: ValidationReport,
    tao_raw: "pd.DataFrame | None" = None,
):
    """J-1 … J-7: Check join coverage rates and SAH/crosswalk completeness."""

    # J-1: AM → IAA join coverage
    if am_ids:
        rate = len(am_ids & iaa_ids) / len(am_ids)
        if rate < AM_IAA_JOIN_THRESHOLD:
            report.warned(
                "J-1",
                f"Only {rate:.1%} of AM accounts appear in IAA "
                f"(threshold {AM_IAA_JOIN_THRESHOLD:.0%}); "
                f"{len(am_ids - iaa_ids)} orphaned AM accounts",
            )
        else:
            report.passed("J-1", f"{rate:.1%} of AM accounts found in IAA ({len(am_ids)} AM accounts)")

    # J-2: IAA → AM join coverage
    if iaa_ids:
        rate = len(iaa_ids & am_ids) / len(iaa_ids)
        if rate < IAA_AM_JOIN_THRESHOLD:
            report.warned(
                "J-2",
                f"Only {rate:.1%} of IAA accounts appear in AM "
                f"(threshold {IAA_AM_JOIN_THRESHOLD:.0%}); "
                f"{len(iaa_ids - am_ids)} IAA accounts have no product data",
            )
        else:
            report.passed("J-2", f"{rate:.1%} of IAA accounts found in AM ({len(iaa_ids)} IAA accounts)")

    # J-3: TAO coverage of non-prospects
    if non_prospect_ids:
        rate = len(non_prospect_ids & tao_ids) / len(non_prospect_ids)
        if rate < TAO_COVERAGE_THRESHOLD:
            report.warned(
                "J-3",
                f"Only {rate:.1%} of non-prospect accounts have TAO data "
                f"(threshold {TAO_COVERAGE_THRESHOLD:.0%}); "
                f"opportunity scores will be zero for {len(non_prospect_ids - tao_ids)} accounts",
            )
        else:
            report.passed("J-3", f"{rate:.1%} of non-prospects have >= 1 TAO row")

    # J-4: ADRM coverage (informational)
    # Caller logs this separately; nothing to assert here.

    # J-5: Every AM L1 maps to a canonical SAH name — HARD FAIL (upgraded from warning)
    unknown_l1 = am_l1_names - canonical_l1_names - {""}
    if unknown_l1:
        report.failed(
            "J-5",
            f"{len(unknown_l1)} AM L1 names not in SAH-Hierarchy.md: {sorted(unknown_l1)}",
        )
    else:
        n_known = len(am_l1_names - {""})
        report.passed("J-5", f"All AM L1 names map to canonical SAH ({n_known} unique names)")

    # J-5b: Every TAO Solution Area name maps to a canonical SAH L1 name
    if tao_raw is not None and "Solution Area" in tao_raw.columns:
        tao_sa_names = {str(r).strip() for r in tao_raw["Solution Area"].dropna()}
        unexpected = tao_sa_names - canonical_l1_names - {""}
        if unexpected:
            unmatched_rate = len(unexpected) / len(tao_sa_names) if tao_sa_names else 0.0
            msg = f"TAO SA names not in canonical SAH L1: {sorted(unexpected)[:5]}"
            if unmatched_rate > 0.20:
                report.failed("J-5b", msg)
            else:
                report.warned("J-5b", msg)
        else:
            report.passed("J-5b", f"All TAO Solution Area names map to canonical SAH L1 ({len(tao_sa_names)} unique names)")

    # J-6: Industry crosswalk completeness
    unmapped = tao_industries - known_crosswalk_keys - {""}
    if unmapped:
        report.warned("J-6", f"{len(unmapped)} TAO industry values not in INDUSTRY_CROSSWALK: {sorted(unmapped)}")
    else:
        report.passed("J-6", f"All TAO industry values covered by INDUSTRY_CROSSWALK ({len(tao_industries)} values)")

    # J-7: No duplicate account × L1 pairs in final coverage
    # (Checked by build_coverage logic; caller passes True/False.)


def check_no_coverage_duplicates(am: pd.DataFrame, report: ValidationReport):
    """J-7: No duplicate Planning Entity ID × L1 rows in AM input (after stripping codes)."""
    if "Planning Entity ID" not in am.columns or "Solution Area Level 1" not in am.columns:
        report.warned("J-7", "Required columns absent — J-7 check skipped")
        return
    am2 = am.copy()
    am2["_l1"] = am2["Solution Area Level 1"].apply(strip_code)
    # Multiple rows per account × L1 are expected (one per product); what we want to
    # verify is that build_coverage deduplicates correctly. We check there are no rows
    # that would contribute the exact same product twice.
    if "Logical Product" in am.columns:
        triple_dupes = am2.groupby(["Planning Entity ID", "_l1", "Logical Product"]).size()
        over_once = (triple_dupes > 1).sum()
        if over_once > 0:
            report.warned("J-7", f"{over_once} duplicate (account, L1, product) rows in AM — may double-list products")
        else:
            report.passed("J-7", "No duplicate (account, L1, product) rows in AM")
    else:
        report.passed("J-7", "J-7 product-dedup check skipped (Logical Product column absent)")


# ---------------------------------------------------------------------------
# Layer 3 — Business logic correctness
# ---------------------------------------------------------------------------

def check_business_logic(
    accounts_data: list[dict],
    sah_l1_names: list[str],
    tao_raw: pd.DataFrame,
    report: ValidationReport,
):
    """B-1 … B-8: Verify scoring logic, prospects, whitespace flags, currency."""

    prospect_ids = [a["id"] for a in accounts_data if a["is_prospect"]]

    # B-1: Prospect accounts must have all-False coverage
    bad_prospects = []
    for a in accounts_data:
        if not a["is_prospect"]:
            continue
        if any(a["coverage"].get(l1, {}).get("live_project") for l1 in sah_l1_names):
            bad_prospects.append(a["id"])
    if bad_prospects:
        report.failed(
            "B-1",
            f"{len(bad_prospects)} prospect accounts have live/project coverage (should be impossible): "
            f"{bad_prospects[:5]}{'...' if len(bad_prospects) > 5 else ''}",
        )
    else:
        report.passed("B-1", f"All {len(prospect_ids)} prospects have zero coverage (correct)")

    # B-2: is_whitespace=True cells must have live_project=False and is_prospect=False
    b2_violations = []
    for a in accounts_data:
        for l1 in sah_l1_names:
            opp = a["opportunity"].get(l1, {})
            if opp.get("is_whitespace"):
                if a["is_prospect"]:
                    b2_violations.append((a["id"], l1, "prospect flagged as whitespace"))
                if a["coverage"].get(l1, {}).get("live_project"):
                    b2_violations.append((a["id"], l1, "covered L1 flagged as whitespace"))
    if b2_violations:
        report.failed(
            "B-2",
            f"{len(b2_violations)} whitespace cells violate definition: "
            f"{b2_violations[:3]}{'...' if len(b2_violations) > 3 else ''}",
        )
    else:
        ws_count = sum(
            1 for a in accounts_data for l1 in sah_l1_names
            if a["opportunity"].get(l1, {}).get("is_whitespace")
        )
        report.passed("B-2", f"All {ws_count} whitespace cells satisfy definition")

    # B-3: Covered cells must NOT be whitespace
    b3_violations = []
    for a in accounts_data:
        for l1 in sah_l1_names:
            if a["coverage"].get(l1, {}).get("live_project"):
                if a["opportunity"].get(l1, {}).get("is_whitespace"):
                    b3_violations.append((a["id"], l1))
    if b3_violations:
        report.failed(
            "B-3",
            f"{len(b3_violations)} covered L1 cells are also marked whitespace: "
            f"{b3_violations[:3]}{'...' if len(b3_violations) > 3 else ''}",
        )
    else:
        report.passed("B-3", "No covered L1 cell is also marked whitespace")

    # B-4: Non-prospect accounts must have at least one covered L1 (sanity: prospect flag is derived from coverage)
    b4_bad = [
        a["id"] for a in accounts_data
        if not a["is_prospect"]
        and not any(a["coverage"].get(l1, {}).get("live_project") for l1 in sah_l1_names)
    ]
    if b4_bad:
        report.failed(
            "B-4",
            f"{len(b4_bad)} non-prospect accounts have zero live/project coverage (classification inconsistency): "
            f"{b4_bad[:5]}{'...' if len(b4_bad) > 5 else ''}",
        )
    else:
        n_non_prospects = sum(1 for a in accounts_data if not a["is_prospect"])
        report.passed("B-4", f"All {n_non_prospects} non-prospect accounts have >= 1 covered L1")

    # B-5: All ADRM pipeline_kusd values must be non-negative
    b5_neg = [
        (a["id"], l1, v)
        for a in accounts_data
        for l1, v in a.get("pipeline_kusd", {}).items()
        if isinstance(v, (int, float)) and v < 0
    ]
    if b5_neg:
        report.warned("B-5", f"{len(b5_neg)} negative pipeline_kusd values in assembled accounts: {b5_neg[:3]}")
    else:
        report.passed("B-5", "All pipeline_kusd values are non-negative")

    # B-6: All assembled TAO gap/wallet values must be non-negative
    b6_neg = []
    for a in accounts_data:
        for l1, t in a.get("tao", {}).items():
            if t is None:
                continue
            if isinstance(t.get("gap_kusd"), (int, float)) and t["gap_kusd"] < 0:
                b6_neg.append((a["id"], l1, "gap", t["gap_kusd"]))
            if isinstance(t.get("estimated_wallet_kusd"), (int, float)) and t["estimated_wallet_kusd"] < 0:
                b6_neg.append((a["id"], l1, "wallet", t["estimated_wallet_kusd"]))
    if b6_neg:
        report.warned("B-6", f"{len(b6_neg)} negative TAO gap/wallet values in assembled accounts: {b6_neg[:3]}")
    else:
        report.passed("B-6", "All assembled TAO gap/wallet values are non-negative")

    # B-8: RISE accounts (is_rise=True) should have Cloud ERP Private any-status coverage
    b8_bad = [
        a["id"] for a in accounts_data
        if a.get("is_rise")
        and not a["coverage"].get("Cloud ERP Private", {}).get("any_status")
    ]
    if b8_bad:
        report.warned(
            "B-8",
            f"{len(b8_bad)} RISE accounts lack Cloud ERP Private coverage: "
            f"{b8_bad[:5]}{'...' if len(b8_bad) > 5 else ''}",
        )
    else:
        n_rise = sum(1 for a in accounts_data if a.get("is_rise"))
        report.passed("B-8", f"All {n_rise} RISE accounts have Cloud ERP Private coverage")

    # B-7: Currency spot-check (5 known TAO rows, re-derive KUSD from source KEuro)
    _check_currency_spot(accounts_data, tao_raw, report)


def _check_currency_spot(
    accounts_data: list[dict],
    tao_raw: pd.DataFrame,
    report: ValidationReport,
):
    """B-7: Spot-check EUR→KUSD conversion on up to CURRENCY_SPOT_N known TAO rows."""
    gap_col = "GAP_TO_ESTIMATED_WALLET"
    if gap_col not in tao_raw.columns or "Planning Entity ID" not in tao_raw.columns:
        report.warned("B-7", "Cannot spot-check currency: TAO raw data unavailable")
        return
    if "Solution Area" not in tao_raw.columns:
        report.warned("B-7", "Cannot spot-check currency: TAO 'Solution Area' column missing")
        return

    has_l2 = "Sub Solution Area" in tao_raw.columns
    acct_by_id = {a["id"]: a for a in accounts_data}
    checked = 0
    violations = []

    for _, row in tao_raw.iterrows():
        if checked >= CURRENCY_SPOT_N:
            break
        raw_gap_keur = row.get(gap_col)
        if pd.isna(raw_gap_keur):
            continue
        acct_id = str(row["Planning Entity ID"]).strip()
        sa = str(row.get("Solution Area", "")).strip()
        if acct_id not in acct_by_id:
            continue

        acct = acct_by_id[acct_id]
        expected_kusd = round(float(raw_gap_keur) * EUR_TO_USD, 2)

        if has_l2:
            l2 = str(row.get("Sub Solution Area", "")).strip()
            tao_cell = acct.get("tao_l2", {}).get(sa, {}).get(l2)
            actual_kusd = tao_cell.get("gap_kusd") if tao_cell else None
        else:
            tao_cell = acct.get("tao", {}).get(sa)
            actual_kusd = tao_cell.get("gap_kusd") if tao_cell else None

        if actual_kusd is None:
            continue
        rel_err = abs(actual_kusd - expected_kusd) / (abs(expected_kusd) + 1e-9)
        if rel_err > CURRENCY_TOLERANCE:
            violations.append(
                f"acct={acct_id} sa={sa!r}: expected {expected_kusd} KUSD, got {actual_kusd}"
            )
        checked += 1

    if violations:
        report.failed("B-7", f"Currency conversion errors in {len(violations)} spot-check rows: {violations}")
    elif checked == 0:
        report.warned("B-7", "Currency spot-check: no matchable rows found in TAO data (all first rows outside IAA scope)")
    else:
        report.passed("B-7", f"Currency spot-check passed ({checked} rows verified, rate={EUR_TO_USD})")


# ---------------------------------------------------------------------------
# Layer 4 — Output structure integrity
# ---------------------------------------------------------------------------

def check_data_json_structure(data: dict, report: ValidationReport):
    """O-1 … O-3: Verify data.json has correct array lengths and metadata."""
    sah_l1 = data.get("sah_l1", [])
    n_l1 = len(sah_l1)
    accounts = data.get("accounts", [])

    # O-1: Per-account arrays must all have length n_l1
    # Note: 'opportunity' is a sparse dict — only whitespace cells are stored.
    # We only check the three fields that are always fully populated.
    bad_lengths = []
    for a in accounts:
        for field in ("coverage", "tao", "pipeline_kusd"):
            val = a.get(field, {})
            if hasattr(val, "__len__") and len(val) != n_l1:
                bad_lengths.append((a["id"], field, len(val), n_l1))
    if bad_lengths:
        report.failed(
            "O-1",
            f"{len(bad_lengths)} account-field length mismatches vs sah_l1 ({n_l1}): "
            f"{bad_lengths[:3]}{'...' if len(bad_lengths) > 3 else ''}",
        )
    else:
        report.passed("O-1", f"All account arrays have correct length ({n_l1}) in {len(accounts)} accounts")

    # O-2: Required top-level keys present in data.json
    required_keys = {"sah_l1", "sah_l1_short", "sah_hierarchy", "accounts", "meta"}
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        report.failed("O-2", f"data.json missing required top-level keys: {sorted(missing_keys)}")
    else:
        report.passed("O-2", f"All required top-level keys present in data.json ({len(required_keys)} checked)")

    # O-3: Metadata currency and exchange rate
    meta = data.get("meta", {})
    if meta.get("currency") != "KUSD":
        report.failed("O-3", f"meta.currency is {meta.get('currency')!r}, expected 'KUSD'")
    elif meta.get("eur_to_usd") != EUR_TO_USD:
        report.failed("O-3", f"meta.eur_to_usd is {meta.get('eur_to_usd')}, expected {EUR_TO_USD}")
    else:
        report.passed("O-3", f"meta.currency=KUSD, meta.eur_to_usd={EUR_TO_USD}")


def check_clusters_json_structure(clusters_data: dict, data: dict, report: ValidationReport):
    """O-4 … O-7: Verify clusters.json referential integrity and arithmetic."""
    sah_l1 = data.get("sah_l1", [])
    account_ids_in_data = {str(a["id"]) for a in data.get("accounts", [])}
    acct_by_id = {str(a["id"]): a for a in data.get("accounts", [])}
    clusters = clusters_data.get("clusters", [])

    # Build L2→L1 map for O-6 gap validation
    l2_to_l1 = {
        l2: l1
        for l1, l1d in data.get("sah_hierarchy", {}).items()
        for l2 in l1d.get("l2", {}).keys()
    }

    # O-4: Every account_id in clusters exists in data.json
    missing_accts = []
    for c in clusters:
        for aid in c.get("account_ids", []):
            if str(aid) not in account_ids_in_data:
                missing_accts.append((c["id"], aid))
    if missing_accts:
        report.failed(
            "O-4",
            f"{len(missing_accts)} cluster account IDs not found in data.json: "
            f"{missing_accts[:3]}{'...' if len(missing_accts) > 3 else ''}",
        )
    else:
        report.passed("O-4", f"All cluster account IDs exist in data.json ({len(clusters)} clusters)")

    # O-5: account_count == len(account_ids) for each cluster
    bad_counts = [
        (c["id"], c.get("account_count"), len(c.get("account_ids", [])))
        for c in clusters
        if c.get("account_count") != len(c.get("account_ids", []))
    ]
    if bad_counts:
        report.failed("O-5", f"{len(bad_counts)} clusters have mismatched account_count: {bad_counts[:3]}")
    else:
        report.passed("O-5", f"account_count matches len(account_ids) in all {len(clusters)} clusters")

    # O-6: total_gap_kusd within 1% of L2-specific TAO gap summed across all ws_l2s
    bad_gaps = []
    for c in clusters:
        expected_gap = 0.0
        for aid in c.get("account_ids", []):
            a = acct_by_id.get(str(aid))
            if not a:
                continue
            for target_l2 in (c.get("ws_l2s") or []):
                target_l1 = l2_to_l1.get(target_l2)
                if not target_l1:
                    continue
                l2_data = (a.get("tao_l2") or {}).get(target_l1, {}).get(target_l2) or {}
                expected_gap += l2_data.get("gap_kusd", 0) or 0.0
        stored = c.get("total_gap_kusd", 0.0) or 0.0
        rel_err = abs(stored - expected_gap) / (abs(expected_gap) + 1e-9)
        if rel_err > 0.01 and abs(stored - expected_gap) > 0.1:
            bad_gaps.append((c["id"], stored, round(expected_gap, 2), f"{rel_err:.2%}"))
    if bad_gaps:
        report.failed(
            "O-6",
            f"{len(bad_gaps)} clusters have total_gap_kusd > 1% off from computed sum: "
            f"{bad_gaps[:3]}{'...' if len(bad_gaps) > 3 else ''}",
        )
    else:
        report.passed("O-6", f"total_gap_kusd arithmetic correct in all {len(clusters)} clusters (within 1%)")

    # O-7: Count accounts that appear in multiple clusters (expected with subset clustering)
    id_cluster_count: dict[str, int] = {}
    for c in clusters:
        for aid in c.get("account_ids", []):
            id_cluster_count[str(aid)] = id_cluster_count.get(str(aid), 0) + 1
    multi = sum(1 for cnt in id_cluster_count.values() if cnt > 1)
    report.passed(
        "O-7",
        f"{len(id_cluster_count)} unique accounts across {len(clusters)} clusters "
        f"({multi} accounts in 2+ clusters)",
    )


# ---------------------------------------------------------------------------
# Layer 5 — Dashboard KPI cross-check (build.py compact)
# ---------------------------------------------------------------------------

def check_compact_payload(
    compact_accounts: list[dict],
    data: dict,
    report: ValidationReport,
):
    """D-1 … D-4: Verify compaction preserves all KPI-relevant data."""
    sah_l1 = data.get("sah_l1", [])
    source_accounts = data.get("accounts", [])

    # D-1: Compact whitespace cell count matches source
    compact_ws_count = sum(1 for a in compact_accounts for w in a.get("ws", []) if w)

    source_ws_count = sum(
        1
        for a in source_accounts
        for l1 in sah_l1
        if a["opportunity"].get(l1, {}).get("is_whitespace")
    )

    if compact_ws_count != source_ws_count:
        report.failed(
            "D-1",
            f"Compact whitespace cell count ({compact_ws_count}) differs from source ({source_ws_count})",
        )
    else:
        report.passed("D-1", f"Compact whitespace cell count matches source ({source_ws_count} cells)")

    # D-2: Compact tao gap total matches source tao gap total (within 0.1%)
    source_tao_total = sum(
        (t.get("gap_kusd") or 0)
        for a in source_accounts
        for l1 in sah_l1
        for t in [a["tao"].get(l1)]
        if t is not None
    )
    compact_tao_total = sum(
        (t.get("gap") or 0)
        for a in compact_accounts
        for t in a.get("tao", [])
        if t is not None
    )
    tao_rel_err = abs(compact_tao_total - source_tao_total) / (abs(source_tao_total) + 1e-9)
    if tao_rel_err > 0.001:
        report.failed(
            "D-2",
            f"Compact tao gap total ({compact_tao_total:.0f} KUSD) differs from source "
            f"({source_tao_total:.0f} KUSD) by {tao_rel_err:.2%}",
        )
    else:
        report.passed("D-2", f"Compact tao gap total matches source ({source_tao_total:.0f} KUSD, within 0.1%)")

    # D-3: sah_l1 and sah_l1_short arrays
    sah_short = data.get("sah_l1_short", [])
    if len(sah_l1) != len(sah_short):
        report.failed("D-3", f"sah_l1 length ({len(sah_l1)}) != sah_l1_short length ({len(sah_short)})")
    elif any(not s for s in sah_l1) or any(not s for s in sah_short):
        report.failed("D-3", "sah_l1 or sah_l1_short contains empty strings")
    elif len(set(sah_l1)) != len(sah_l1) or len(set(sah_short)) != len(sah_short):
        report.failed("D-3", "sah_l1 or sah_l1_short contains duplicate values")
    else:
        report.passed("D-3", f"sah_l1 and sah_l1_short: {len(sah_l1)} unique non-empty entries each")

    # D-4: Prospect count matches
    compact_prospect_count = sum(1 for a in compact_accounts if a.get("is_p"))
    source_prospect_count = sum(1 for a in source_accounts if a.get("is_prospect"))
    if compact_prospect_count != source_prospect_count:
        report.failed(
            "D-4",
            f"Compact prospect count ({compact_prospect_count}) != source ({source_prospect_count})",
        )
    else:
        report.passed("D-4", f"Prospect count matches: {source_prospect_count}")
