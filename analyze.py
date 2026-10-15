"""
analyze.py — cluster non-prospect accounts by shared coverage + whitespace fingerprints

Clustering logic:
  - Coverage fingerprint: sorted tuple of live/project L2s, excluding L2s whose parent
    L1 is "Other" (catch-all bucket that adds noise without signal).
  - Whitespace target: a single TAO-backed whitespace L2 per cluster key.
  - Cluster key: (coverage_subset, (target_l2,)).
  - Industry is NOT part of the key — cross-industry patterns are intentional.
  - Each account contributes one key per whitespace L2 × coverage subset (size 2–4).
  - Accounts with fewer than min_core_l2s covered L2s are excluded (hard minimum).
  - Top max_per_target clusters per target L2 are kept; then the global max_clusters cap applies.
  - Identity deduplication: if two clusters share the exact same account set and one's
    core is a superset of the other's, the subset cluster is dropped.

Usage:
    python3 analyze.py [--data output/data.json] [--out output/clusters.json]
                       [--min-size 5] [--min-core-l2s 2] [--max-core-l2s 4]
                       [--max-per-target 3] [--max-clusters 200]

Must be run after ingest.py and before build.py.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations

import validate
from validate import ValidationError, ValidationReport


_CATCHALL_L1 = "Other"


def _coverage_fingerprint(account, other_l2s):
    """Sorted tuple of live/project L2s, excluding the catch-all L1's children."""
    l2s = set()
    for l1, cov in account.get("coverage", {}).items():
        if l1 == _CATCHALL_L1:
            continue
        for l2_name, st in (cov.get("l2") or {}).items():
            if st.get("live") or st.get("project"):
                l2s.add(l2_name)
    return tuple(sorted(l2s - other_l2s))


def _whitespace_l2s(account, sah_l1):
    """Flat list of whitespace L2s backed by TAO sub-solution data, excluding catch-all."""
    l2s = []
    tao_l2 = account.get("tao_l2", {})
    for l1 in sah_l1:
        if l1 == _CATCHALL_L1:
            continue
        if account.get("opportunity", {}).get(l1, {}).get("is_whitespace"):
            l2s.extend(tao_l2.get(l1, {}).keys())
    return l2s


def build_clusters(data, min_size, min_core_l2s=2, max_core_l2s=4, max_per_target=3, ubiquity_threshold=0.5):
    sah_l1 = data["sah_l1"]
    hierarchy = data.get("sah_hierarchy", {})

    # L2s that belong to the catch-all L1 — excluded from fingerprints
    other_l2s = set(hierarchy.get(_CATCHALL_L1, {}).get("l2", {}).keys())

    # L2 → parent L1 map (needed for L2 gap lookup)
    l2_to_l1 = {
        l2: l1
        for l1, l1d in hierarchy.items()
        for l2 in l1d.get("l2", {}).keys()
    }

    # Compute L2 frequency across non-prospect accounts; exclude ubiquitous L2s
    # (those present in > ubiquity_threshold of candidates) from coverage fingerprints.
    l2_freq = Counter()
    n_candidates = 0
    for account in data["accounts"]:
        if account.get("is_prospect"):
            continue
        n_candidates += 1
        for l1, cov in account.get("coverage", {}).items():
            if l1 == _CATCHALL_L1:
                continue
            for l2_name, st in (cov.get("l2") or {}).items():
                if st.get("live") or st.get("project"):
                    l2_freq[l2_name] += 1
    ubiquitous_l2s = {
        l2 for l2, cnt in l2_freq.items()
        if n_candidates > 0 and cnt / n_candidates > ubiquity_threshold
    }
    excluded_l2s = other_l2s | ubiquitous_l2s
    if ubiquitous_l2s:
        print(f"  Excluding {len(ubiquitous_l2s)} ubiquitous L2s (>{ubiquity_threshold*100:.0f}% of accounts): "
              f"{', '.join(sorted(ubiquitous_l2s))}")

    raw_clusters = {}  # (cov_subset_tuple, (target_l2,)) → list of account dicts

    for account in data["accounts"]:
        if account.get("is_prospect"):
            continue

        cov_fp = _coverage_fingerprint(account, excluded_l2s)
        ws_l2s = _whitespace_l2s(account, sah_l1)

        # Hard minimum: skip accounts without enough coverage to form a meaningful play
        if len(cov_fp) < min_core_l2s or not ws_l2s:
            continue

        for ws_l2 in ws_l2s:
            for size in range(min_core_l2s, min(len(cov_fp), max_core_l2s) + 1):
                for subset in combinations(cov_fp, size):
                    raw_clusters.setdefault((subset, (ws_l2,)), []).append(account)

    # Filter to min_size and deduplicate account ids within each bucket
    sized = {}
    for key, accts in raw_clusters.items():
        seen_ids = set()
        unique = []
        for a in accts:
            aid = a["id"]
            if aid not in seen_ids:
                seen_ids.add(aid)
                unique.append(a)
        if len(unique) >= min_size:
            sized[key] = (unique, frozenset(a["id"] for a in unique))

    # Identity deduplication: for each unique (ws_fp, account_set) pair, keep only the
    # cluster with the largest core — it's strictly more informative than any subset core
    # with the same members.
    best = {}  # (ws_fp, acct_frozenset) → (core_size, key)
    for key, (accounts, acct_set) in sized.items():
        cov_fp, ws_fp = key
        dedup_key = (ws_fp, acct_set)
        if dedup_key not in best or len(cov_fp) > best[dedup_key][0]:
            best[dedup_key] = (len(cov_fp), key)
    surviving_keys = {v[1] for v in best.values()}

    # Whitespace-subset merge: with single-element targets this is a no-op, but kept
    # for correctness in case max_per_target > 1 produces same-target clusters.
    cov_groups = defaultdict(list)
    for key in surviving_keys:
        cov_groups[key[0]].append(key)

    merged = {}  # (cov_fp, ws_fp) → (account_list, acct_frozenset)
    for cov_fp, keys in cov_groups.items():
        keys_sorted = sorted(keys, key=lambda k: len(k[1]))
        committed = []  # list of (ws_set, canonical_key)

        for key in keys_sorted:
            _, ws_fp = key
            ws_set = set(ws_fp)
            accts, acct_set = sized[key]

            absorbed_into = None
            for ws_short_set, canonical_key in committed:
                if ws_short_set <= ws_set:
                    absorbed_into = canonical_key
                    break

            if absorbed_into is None:
                merged[key] = (list(accts), frozenset(a["id"] for a in accts))
                committed.append((ws_set, key))
            else:
                existing_accts, existing_ids = merged[absorbed_into]
                new_accts = existing_accts + [a for a in accts if a["id"] not in existing_ids]
                merged[absorbed_into] = (new_accts, frozenset(a["id"] for a in new_accts))

    clusters = []
    for key, (accounts, _) in merged.items():
        cov_fp, ws_fp = key
        if not ws_fp:
            continue

        target_l2 = ws_fp[0]
        target_l1 = l2_to_l1.get(target_l2)

        account_ids    = [str(a["id"]) for a in accounts]
        total_gap_kusd = 0.0
        for a in accounts:
            l2_data = (a.get("tao_l2") or {}).get(target_l1 or "", {}).get(target_l2) or {}
            total_gap_kusd += l2_data.get("gap_kusd", 0) or 0

        # Target L2s: applicable_products in whitespace L1s, keyed by sah_l4 (or sah_l2),
        # ranked by how many accounts in the cluster share them.
        l2_hit_count = Counter()
        for a in accounts:
            seen = set()
            for p in (a.get("applicable_products") or []):
                if p.get("sah_l1") in ws_fp:
                    prod_key = p.get("sah_l4") or p.get("sah_l2")
                    if prod_key and prod_key not in seen:
                        l2_hit_count[prod_key] += 1
                        seen.add(prod_key)
        target_l2s = [k for k, _ in l2_hit_count.most_common()]

        cov_str        = " + ".join(cov_fp) if cov_fp else "(none)"
        campaign_label = f"{cov_str} → {target_l2}"

        clusters.append({
            "_sort_key":      total_gap_kusd,
            "campaign_label": campaign_label,
            "covered_l2s":    list(cov_fp),
            "ws_l2s":         [target_l2],
            "target_l2s":     target_l2s,
            "account_ids":    account_ids,
            "account_count":  len(account_ids),
            "total_gap_kusd": round(total_gap_kusd, 2),
        })

    clusters.sort(key=lambda c: c["_sort_key"], reverse=True)
    for c in clusters:
        del c["_sort_key"]

    # Keep top max_per_target clusters per target L2 (best coverage footprints per play)
    if max_per_target and max_per_target > 0:
        l2_count = defaultdict(int)
        capped = []
        for c in clusters:
            key = (c.get("ws_l2s") or [None])[0]
            if l2_count[key] < max_per_target:
                capped.append(c)
                l2_count[key] += 1
        clusters = capped

    return clusters


def main():
    parser = argparse.ArgumentParser(description="Cluster accounts by coverage + whitespace fingerprints.")
    parser.add_argument("--data",            default="output/data.json",     help="Path to data.json from ingest.py")
    parser.add_argument("--out",             default="output/clusters.json", help="Output path for clusters.json")
    parser.add_argument("--min-size",        type=int, default=5,            help="Minimum accounts per cluster (default 5)")
    parser.add_argument("--min-core-l2s",    type=int, default=2,            help="Minimum L2s in a cluster core (default 2)")
    parser.add_argument("--max-core-l2s",    type=int, default=4,            help="Maximum L2s in a cluster core (default 4)")
    parser.add_argument("--max-per-target",      type=int,   default=3,    help="Maximum clusters per target L2 (default 3; 0 = no cap)")
    parser.add_argument("--max-clusters",        type=int,   default=200,  help="Maximum clusters to output, top-N by gap (default 200; 0 = no cap)")
    parser.add_argument("--ubiquity-threshold",  type=float, default=0.5,  help="Exclude L2s present in more than this fraction of accounts from coverage fingerprints (default 0.5)")
    args = parser.parse_args()

    print(f"Loading {args.data} ...")
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    n_accounts   = len(data["accounts"])
    n_prospects  = sum(1 for a in data["accounts"] if a.get("is_prospect"))
    n_candidates = n_accounts - n_prospects
    print(f"  {n_accounts} accounts ({n_prospects} prospects, {n_candidates} candidates for clustering)")

    print(f"Clustering (min-size={args.min_size}, core-l2s={args.min_core_l2s}–{args.max_core_l2s}, max-per-target={args.max_per_target}, ubiquity-threshold={args.ubiquity_threshold}) ...")
    clusters = build_clusters(data, args.min_size, args.min_core_l2s, args.max_core_l2s, args.max_per_target, args.ubiquity_threshold)

    if args.max_clusters and len(clusters) > args.max_clusters:
        print(f"  Trimmed from {len(clusters)} to top {args.max_clusters} clusters by gap")
        clusters = clusters[:args.max_clusters]

    # Assign final IDs after trimming
    for n, c in enumerate(clusters, start=1):
        c["id"] = f"c{n:03d}"

    n_clustered = len({acct_id for c in clusters for acct_id in c["account_ids"]})
    print(f"  {len(clusters)} clusters covering {n_clustered} accounts")

    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_size":     args.min_size,
            "source":       args.data,
        },
        "clusters": clusters,
    }

    print("\nValidation — Layer 4: Clusters output structure")
    report    = ValidationReport()
    hard_fail = False
    try:
        validate.check_clusters_json_structure(output, data, report)
    except ValidationError as exc:
        hard_fail = True
        print(f"\n  Cluster validation hard failure: {exc}", file=sys.stderr)

    print(f"\n{report.summary()}")

    if hard_fail:
        print("Analyze soft-blocked: clusters.json NOT written due to hard validation failure.", file=sys.stderr)
        sys.exit(2)

    os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Done. {len(clusters)} clusters ({n_clustered} accounts) written to {args.out}")


if __name__ == "__main__":
    main()
