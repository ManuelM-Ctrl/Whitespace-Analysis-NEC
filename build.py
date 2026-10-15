"""
build.py — assemble whitespace-analyzer.html from template + data + CDN libraries

Usage:
    python3 build.py [--data output/data.json] [--out output/whitespace-analyzer.html] [--no-cache]
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
import sys
import urllib.request

import validate
from validate import ValidationError, ValidationReport

CDN_ASSETS = {
    "__CSS_HORIZON__": "https://cdn.jsdelivr.net/npm/fundamental-styles@0.41.7/dist/theming/sap_horizon.css",
    "__CSS_FD__": "https://cdn.jsdelivr.net/npm/fundamental-styles@0.41.7/dist/fundamental-styles.css",
    "__LIB_VUE__": "https://cdn.jsdelivr.net/npm/vue@3.5.38/dist/vue.global.prod.js",
    "__LIB_CHARTJS__": "https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js",
    "__LIB_TREEMAP__": "https://cdn.jsdelivr.net/npm/chartjs-chart-treemap@3.1.0/dist/chartjs-chart-treemap.min.js",
}

# SHA-256 hashes for each CDN asset. Populate after a trusted initial fetch:
#   python3 -c "import hashlib; print(hashlib.sha256(open('.cdn-cache/KEY.js','rb').read()).hexdigest())"
# When a hash is present, fetch_asset verifies the downloaded content against it.
CDN_ASSET_SHAS: dict[str, str] = {
    # "__LIB_VUE__":     "abc123...",
    # "__LIB_CHARTJS__": "abc123...",
    # "__LIB_TREEMAP__": "abc123...",
    # "__CSS_HORIZON__": "abc123...",
    # "__CSS_FD__":      "abc123...",
}

CACHE_DIR = ".cdn-cache"


def fetch_asset(key, url, use_cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    filename = key.strip("_").lower() + ("." + url.rsplit(".", 1)[-1] if "." in url.rsplit("/", 1)[-1] else ".txt")
    cache_path = os.path.join(CACHE_DIR, filename)
    if use_cache and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read()
    print(f"  Fetching {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "build.py/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read().decode("utf-8")
    expected_sha = CDN_ASSET_SHAS.get(key)
    if expected_sha:
        actual_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"SRI check failed for {key}: expected {expected_sha}, got {actual_sha}. "
                "Delete the CDN cache and re-fetch from a trusted source."
            )
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def compact_account(a, sah_l1, sah_l2_per_l1, tp_coverage=None, tp_name_map=None, sah_l3_per_l2=None):
    cov     = [a["coverage"].get(l, {}).get("live_project", False) for l in sah_l1]
    cov_any = [a["coverage"].get(l, {}).get("any_status", False) for l in sah_l1]
    cov_products = [a["coverage"].get(l, {}).get("products", []) for l in sah_l1]

    # l2s[i][j]: 3=Live, 2=Project, 1=Shelfware, 0=No coverage
    l2s = []
    l2_lpr_cnt = []
    for i, l1 in enumerate(sah_l1):
        l2_dict = a["coverage"].get(l1, {}).get("l2", {})
        row = []
        cnt_row = []
        for l2 in sah_l2_per_l1[i]:
            e = l2_dict.get(l2, {})
            if e.get("live"):       row.append(3)
            elif e.get("project"):  row.append(2)
            elif e.get("shelfware"): row.append(1)
            else:                   row.append(0)
            cnt_row.append(e.get("lpr_cnt", 0))
        l2s.append(row)
        l2_lpr_cnt.append(cnt_row)

    # l3s[i][j][k]: 3=Live, 2=Project, 1=Shelfware, 0=None per L3 k under L2 j under L1 i
    l3s = []
    for i, l1 in enumerate(sah_l1):
        l2_dict = a["coverage"].get(l1, {}).get("l2", {})
        l1_l3s = []
        for j, l2 in enumerate(sah_l2_per_l1[i]):
            l3_dict = l2_dict.get(l2, {}).get("l3", {})
            l3_names = sah_l3_per_l2[i][j] if sah_l3_per_l2 else []
            row = []
            for l3 in l3_names:
                e = l3_dict.get(l3, {})
                if e.get("live"):         row.append(3)
                elif e.get("project"):    row.append(2)
                elif e.get("shelfware"):  row.append(1)
                else:                     row.append(0)
            l1_l3s.append(row)
        l3s.append(l1_l3s)

    tp_id = a.get("top_parent_id") or ""
    tp_cov = (tp_coverage or {}).get(tp_id, {})
    tp_name = (tp_name_map or {}).get(tp_id) if not a.get("is_top_parent") else None
    tp_l2s = []
    for i, l1 in enumerate(sah_l1):
        row = [1 if tp_cov.get(l1, {}).get(l2) else 0 for l2 in sah_l2_per_l1[i]]
        tp_l2s.append(row)

    tao = []
    for l in sah_l1:
        t = a["tao"].get(l)
        if t is None:
            tao.append(None)
        else:
            tao.append({
                "gap":      t.get("gap_kusd"),
                "wallet":   t.get("estimated_wallet_kusd"),
                "pri":      t.get("priority_score"),
                "strat":    t.get("strategy"),
                "hist":     t.get("historical_pipeline"),
                "acv":      t.get("acv_kusd"),
                "acv_risk": t.get("acv_at_risk_kusd"),
                "cy":       t.get("cy_pipeline_kusd"),
                "cy1":      t.get("cy1_pipeline_kusd"),
            })

    tao_l2 = []
    for i, l1 in enumerate(sah_l1):
        l2_map = a.get("tao_l2", {}).get(l1, {})
        row = []
        for l2 in sah_l2_per_l1[i]:
            t = l2_map.get(l2)
            row.append({"gap": t["gap_kusd"], "wallet": t["estimated_wallet_kusd"]} if t else None)
        tao_l2.append(row)

    pipe = [a["pipeline_kusd"].get(l, 0.0) for l in sah_l1]
    spi  = [a.get("planned_pipeline_kusd", {}).get(l, 0.0) for l in sah_l1]

    ws = []
    for l in sah_l1:
        w = a["opportunity"].get(l)
        ws.append(True if (w and w.get("is_whitespace")) else None)

    prods = []
    for p in a.get("applicable_products", []):
        _kg = p.get("kg_uri")
        prods.append({
            "p":   p.get("product"),
            "tag": p.get("tag"),
            "cat": p.get("category"),
            "pri": p.get("priority"),
            "l1":  p.get("sah_l1"),
            "l2":  p.get("sah_l2"),
            "l4":  p.get("sah_l4"),
            "kg":  _kg if isinstance(_kg, str) and _kg.startswith(("https://", "http://")) else None,
            "url": p.get("external_url"),
        })

    return {
        "id":   a["id"],
        "name": a["name"],
        "so":   a["sales_office"],
        "sg":   a["sales_group"],
        "ind":    a.get("industry"),
        "ind_b":  a.get("industry_bucket"),
        "arch":   a.get("archetype"),
        "rev":    a.get("revenue_band"),
        "iac":    a.get("iac"),
        "geo_l3": a.get("geo_l3"),
        "terr_emp": a.get("terr_employee"),
        "terr_mgr": a.get("terr_manager"),
        "seg":    a.get("segment"),
        "rbc":    a.get("rbc"),
        "n_sol":  a.get("num_solutions"),
        "n_sol_b":a.get("num_solutions_band"),
        "sic":  a.get("sic"),
        "is_p": a.get("is_prospect", False),
        "rise": a.get("is_rise", False),
        "is_tp": a.get("is_top_parent", False),
        "cov":  cov,
        "cov_any": cov_any,
        "cov_products": cov_products,
        "tao":  tao,
        "tao_l2": tao_l2,
        "pipe": pipe,
        "spi":  spi,
        "ws":   ws,
        "l2s":  l2s,
        "l2_lpr_cnt": l2_lpr_cnt,
        "l3s":  l3s,
        "tp_l2s": tp_l2s,
        "tp_name": tp_name,
        "prods": prods,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",     default="output/data.json")
    parser.add_argument("--clusters", default="output/clusters.json", help="Path to clusters.json from analyze.py (optional)")
    parser.add_argument("--template", default="dashboard-template.html")
    parser.add_argument("--out",      default="output/whitespace-analyzer.html")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    use_cache = not args.no_cache

    print(f"Loading {args.data} ...")
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    sah_l1 = data["sah_l1"]
    sah_hierarchy = data["sah_hierarchy"]
    sah_l2_per_l1 = [
        list(sah_hierarchy.get(l1, {}).get("l2", {}).keys())
        for l1 in sah_l1
    ]
    l3_dict = data.get("sah_l3_per_l2", {})
    sah_l3_per_l2 = [
        [l3_dict.get(l1, {}).get(l2, []) for l2 in sah_l2_per_l1[i]]
        for i, l1 in enumerate(sah_l1)
    ]
    print(f"  {len(data['accounts'])} accounts, {len(sah_l1)} SAH L1s")

    clusters_data = None
    if args.clusters and os.path.exists(args.clusters):
        print(f"Loading clusters from {args.clusters} ...")
        with open(args.clusters, "r", encoding="utf-8") as f:
            clusters_data = json.load(f)
        print(f"  {len(clusters_data.get('clusters', []))} clusters")
    elif args.clusters:
        print(f"  clusters file not found ({args.clusters}), skipping — Portfolio tab will be hidden")

    print("Compact-encoding accounts ...")
    tp_coverage = data.get("tp_coverage", {})
    tp_name_map = data.get("tp_name_map", {})
    compact_accounts = [compact_account(a, sah_l1, sah_l2_per_l1, tp_coverage, tp_name_map, sah_l3_per_l2) for a in data["accounts"]]

    # ------------------------------------------------------------------
    # Layer 5: Dashboard KPI cross-check (D-1 … D-4)
    # ------------------------------------------------------------------
    print("\nValidation — Layer 5: Compact payload")
    report = ValidationReport()
    hard_fail = False
    try:
        validate.check_compact_payload(compact_accounts, data, report)
    except ValidationError as exc:
        hard_fail = True
        print(f"\n  Compact validation hard failure: {exc}", file=sys.stderr)

    print(f"\n{report.summary()}")

    if hard_fail:
        print("Build soft-blocked: whitespace-analyzer.html NOT written due to hard validation failure.", file=sys.stderr)
        sys.exit(2)

    payload = {
        "meta":          data["meta"],
        "sah_l1":        sah_l1,
        "sah_l1_short":  data.get("sah_l1_short", sah_l1),
        "sah_l2_per_l1": sah_l2_per_l1,
        "sah_l3_per_l2": sah_l3_per_l2,
        "sah_hierarchy": data["sah_hierarchy"],
        "accounts":      compact_accounts,
        "clusters":      clusters_data["clusters"] if clusters_data else None,
    }
    data_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    data_json = data_json.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    data_json = data_json.replace("</script>", r"<\/script>")
    print(f"  Compact payload: {len(data_json)/1e6:.2f} MB")
    data_gz_b64 = base64.b64encode(
        gzip.compress(data_json.encode("utf-8"), compresslevel=6)
    ).decode("ascii")
    print(f"  Compressed payload: {len(data_gz_b64)/1e6:.2f} MB (base64)")

    print("Fetching CDN assets ...")
    assets = {}
    for key, url in CDN_ASSETS.items():
        assets[key] = fetch_asset(key, url, use_cache)

    print(f"Reading template {args.template} ...")
    with open(args.template, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject CSS assets (inside <style> tags — replace the comment marker)
    for key in ("__CSS_HORIZON__", "__CSS_FD__"):
        html = html.replace(f"/*{key}*/", assets[key])

    # Inject JS libraries (inside <script> tags)
    for key in ("__LIB_VUE__", "__LIB_CHARTJS__", "__LIB_TREEMAP__"):
        html = html.replace(f"/*{key}*/", assets[key])

    # Inject data (base64-encoded gzip; decompressed at runtime via DecompressionStream)
    html = html.replace('"/*__DATA_GZ__*/"', '"' + data_gz_b64 + '"')

    print(f"Writing {args.out} ...")
    out_dir = os.path.dirname(args.out) or "."
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    version_path = os.path.join(out_dir, "version.json")
    with open(version_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": data["meta"]["generated_at"]}, f)
    print(f"  Version:   {version_path}")

    size_mb = os.path.getsize(args.out) / 1e6

    # Stats
    n_accounts  = len(compact_accounts)
    n_prospects = sum(1 for a in compact_accounts if a["is_p"])
    n_ws_cells  = sum(1 for a in compact_accounts for w in a["ws"] if w)

    print(f"\nDone.")
    print(f"  Output:    {args.out} ({size_mb:.1f} MB)")
    print(f"  Accounts:  {n_accounts} ({n_prospects} prospects)")
    print(f"  Whitespace cells: {n_ws_cells}")
    if clusters_data:
        print(f"  Clusters:  {len(clusters_data.get('clusters', []))}")


if __name__ == "__main__":
    main()
