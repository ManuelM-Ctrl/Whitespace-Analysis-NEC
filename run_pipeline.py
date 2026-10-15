#!/usr/bin/env python3
"""
run_pipeline.py — orchestrate ingest.py → analyze.py → build.py

Usage:
    python3 run_pipeline.py [options]

Runs the three pipeline scripts in sequence. On success, prints a one-line
summary per step then a final report. On failure, dumps the script output
and exits non-zero.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).parent.resolve()

# Glob patterns used by --input-dir auto-discovery.
# Each value is either a single pattern string (→ one file) or a list of patterns (→ ordered list).
# Required roles must match exactly one file each; optional roles (am_tp, spi) may match zero.
_INPUT_DIR_PATTERNS = {
    "am":    "??*_MU_AM_????-??-??.csv",
    "am_tp": "??*_MU_AM_TP_????-??-??.csv",
    "iaa":   "??*_MU_IAA_????-??-??.csv",
    "tao":   "??*_MU_TAO_????-??-??.csv",
    "adrm":  "??*_MU_ADRM_????-??-??.csv",
    "spi":   "??*_MU_SPI_????-??-??.csv",
}
_INPUT_DIR_OPTIONAL = {"am_tp", "spi"}

DEFAULTS = {
    "am":    "example-data/MW_MU_AM_2026-07-06.csv",
    "am_tp": "example-data/MW_MU_AM_TP_2026-07-08.csv",
    "iaa":   "example-data/MW_MU_IAA_2026-07-06.csv",
    "tao":   [
        "example-data/US_MIDWEST_TAO_26_05_2026_v2_1.csv",
        "example-data/US_MIDWEST_TAO_26_05_2026_v2_2.csv",
        "example-data/US_MIDWEST_TAO_26_05_2026_v2_3.csv",
    ],
    "adrm": "example-data/MW_MU_ADRM_2026-07-06.csv",
    "spi":  "example-data/MW_MU_SPI_2026-07-06.csv",
    "ref":  "reference-data/SAP_Industry_Solution_Reference.xlsx",
    "sah":  "reference-data/Copy of Solution Areas and Logical Products 2026 - update.xlsx",
}

FILE_ROLES = {
    "am":    "AM — adoption state per account × solution area",
    "am_tp": "AM (Top Parent) — adoption state for top-parent accounts",
    "iaa":   "IAA — account master (MU, Sales Office, Sales Group)",
    "tao":   "TAO — outside-in gap-to-wallet metrics",
    "adrm":  "ADRM — current-quarter pipeline forecast",
    "spi":   "SPI — planned pipeline forecast (optional)",
    "ref":   "Reference — industry solution reference (SAP_Industry_Solution_Reference.xlsx)",
    "sah":   "SAH — solution area hierarchy (Copy of Solution Areas and Logical Products 2026 - update.xlsx)",
}


def run_step(label, cmd, soft_block=False):
    """Run cmd, print label while running. Return (stdout, soft_blocked) on completion.

    If soft_block=True, exit code 2 is treated as a soft-block: the step's
    output is shown as a warning and the pipeline continues. Any other non-zero
    exit code is a hard failure that aborts the pipeline.
    """
    print(f"{label} ...", end="  ", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout, False
    if soft_block and result.returncode == 2:
        print("SOFT-BLOCKED")
        combined = (result.stdout + "\n" + result.stderr).strip()
        print(combined)
        return result.stdout, True
    print("FAILED")
    combined = (result.stdout + "\n" + result.stderr).strip()
    print(combined, file=sys.stderr)
    sys.exit(result.returncode)


def extract_done(output):
    """Return the text after 'Done. ' on the Done line, or 'OK'."""
    for line in output.splitlines():
        if line.startswith("Done."):
            return line[len("Done. "):].strip()
    return "OK"


def main():
    parser = argparse.ArgumentParser(
        description="Run the Whitespace Analysis pipeline: ingest → analyze → build."
    )
    for key, path in DEFAULTS.items():
        if key == "tao":
            parser.add_argument("--tao", nargs="+", default=path, metavar="FILE")
        elif key == "am_tp":
            parser.add_argument("--am-tp", default=path, metavar="FILE",
                                help="Top-parent Adoption Monitor CSV (optional; skipped if file not found)")
        else:
            parser.add_argument(f"--{key}", default=path, metavar="FILE")
    parser.add_argument("--data",     default="output/data.json",     metavar="FILE",
                        help="Intermediate data.json path (default: output/data.json)")
    parser.add_argument("--clusters", default="output/clusters.json", metavar="FILE",
                        help="Intermediate clusters.json path (default: output/clusters.json)")
    parser.add_argument("--out",      default="output/whitespace-analyzer.html",   metavar="FILE",
                        help="Output HTML path (default: output/whitespace-analyzer.html)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Bypass CDN asset cache in build step")
    parser.add_argument("--min-core-l2s", type=int, default=3, metavar="N",
                        help="Minimum L2s in a cluster coverage footprint (default 3)")
    parser.add_argument("--max-per-target", type=int, default=3, metavar="N",
                        help="Maximum clusters per target L2 in analyze step (default 3)")
    parser.add_argument("--ubiquity-threshold", type=float, default=0.5, metavar="F",
                        help="Exclude L2s in >F fraction of accounts from coverage fingerprints (default 0.5)")
    parser.add_argument("--snapshot-date", default=None, metavar="DATE",
                        help="Source data snapshot date (YYYY-MM-DD); shown in dashboard header")
    parser.add_argument("--input-dir", default=None, metavar="DIR",
                        help="Dated input folder (e.g. input/2026-07-13/); auto-discovers all "
                             "source files. Explicit file flags override per-file.")
    args = parser.parse_args()

    # --input-dir: auto-discover files not already overridden by an explicit flag.
    # Explicit flags always win; discovery only fills in DEFAULTS-valued arguments.
    if args.input_dir is not None:
        input_dir = pathlib.Path(args.input_dir)
        if not input_dir.is_absolute():
            input_dir = REPO_ROOT / input_dir
        if not input_dir.is_dir():
            print(f"ERROR: --input-dir not found: {input_dir}", file=sys.stderr)
            sys.exit(1)

        for key, patterns in _INPUT_DIR_PATTERNS.items():
            # Skip if the user explicitly provided this flag (value differs from the default)
            current = getattr(args, key)
            default = DEFAULTS.get(key)
            if current != default:
                continue  # explicit override — leave it alone

            optional = key in _INPUT_DIR_OPTIONAL
            matches = sorted(input_dir.glob(patterns))
            if len(matches) == 0:
                if optional:
                    setattr(args, key, None)
                else:
                    print(f"ERROR: no file matching '{patterns}' in {input_dir}", file=sys.stderr)
                    sys.exit(1)
            elif key == "tao":
                # Collect all matching TAO files (may be split into multiple parts)
                setattr(args, key, [str(m) for m in matches])
            elif len(matches) > 1:
                print(f"ERROR: multiple files matching '{patterns}' in {input_dir}: "
                      f"{[str(m) for m in matches]}", file=sys.stderr)
                sys.exit(1)
            else:
                setattr(args, key, str(matches[0]))

        # Auto-derive --snapshot-date from the folder name if not explicitly set
        if args.snapshot_date is None:
            folder_name = input_dir.name
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder_name):
                args.snapshot_date = folder_name

    # Auto-derive output directory from snapshot date.
    # Redirects --data/--clusters/--out to output/<YYYY-MM-DD>/ when they are still
    # at their argparse defaults (i.e. the user did not supply explicit output paths).
    _OUTPUT_DEFAULTS = {
        "data":     "output/data.json",
        "clusters": "output/clusters.json",
        "out":      "output/whitespace-analyzer.html",
    }
    if args.snapshot_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.snapshot_date):
        dated_out_dir = f"output/{args.snapshot_date}"
        for key, default in _OUTPUT_DEFAULTS.items():
            if getattr(args, key) == default:
                setattr(args, key, f"{dated_out_dir}/{pathlib.Path(default).name}")

    # Resolve relative paths against the repo root so the pipeline works
    # regardless of the caller's working directory.
    for key in list(DEFAULTS) + ["data", "clusters", "out"]:
        val = getattr(args, key)
        if key == "tao":
            setattr(args, key, [
                str(REPO_ROOT / p) if not pathlib.Path(p).is_absolute() else p
                for p in val
            ])
        else:
            if val is None:
                continue
            p = pathlib.Path(val)
            if not p.is_absolute():
                setattr(args, key, str(REPO_ROOT / p))

    # Preflight: verify source files (am_tp is optional — warn if missing but continue)
    OPTIONAL_KEYS = {"am_tp", "spi"}
    missing = []
    missing_optional = []
    for k, role in FILE_ROLES.items():
        paths = getattr(args, k)
        for path in (paths if isinstance(paths, list) else ([paths] if paths else [])):
            if not os.path.exists(path):
                if k in OPTIONAL_KEYS:
                    missing_optional.append((k, path, role))
                else:
                    missing.append((path, role))
    if missing_optional:
        for k, path, role in missing_optional:
            print(f"  INFO: optional file not found, skipping: {path}  —  {role}")
            setattr(args, k, None)
    if missing:
        print("Missing required input files:")
        for path, role in missing:
            print(f"  {path}  —  {role}")
        sys.exit(1)

    # Warn if any source filename has a malformed year in the date token (e.g. "20s26" instead of "2026")
    _filename_pat = re.compile(r"_(\d{4})-\d{2}-\d{2}\.")
    for k in FILE_ROLES:
        val = getattr(args, k)
        for path in (val if isinstance(val, list) else ([val] if val else [])):
            m = _filename_pat.search(os.path.basename(path))
            if m and not re.fullmatch(r"20\d{2}", m.group(1)):
                print(f"  WARNING: unexpected year '{m.group(1)}' in filename: {path}")

    for script in ("ingest.py", "analyze.py", "build.py"):
        if not (REPO_ROOT / script).exists():
            print(f"Missing script: {REPO_ROOT / script}", file=sys.stderr)
            sys.exit(1)

    for out_path in [args.data, args.clusters, args.out]:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # Step 1 — Ingest (soft-block on exit 2: warnings still write data.json; hard fail otherwise)
    out, ingest_soft_blocked = run_step("Ingest", [
        sys.executable, str(REPO_ROOT / "ingest.py"),
        "--am", args.am, "--iaa", args.iaa, "--tao", *args.tao,
        "--adrm", args.adrm, "--ref", args.ref, "--sah", args.sah, "--out", args.data,
        *( ["--am-tp", args.am_tp] if args.am_tp else [] ),
        *( ["--spi", args.spi] if args.spi and os.path.exists(args.spi) else [] ),
        *( ["--snapshot-date", args.snapshot_date] if args.snapshot_date else [] ),
    ], soft_block=True)
    if not os.path.exists(args.data):
        print(f"Ingest did not produce {args.data} — aborting.", file=sys.stderr)
        sys.exit(1)
    if not ingest_soft_blocked:
        print(extract_done(out))

    # Step 2 — Analyze (soft-block: clusters are optional for build)
    out, analyze_blocked = run_step("Analyze", [
        sys.executable, str(REPO_ROOT / "analyze.py"),
        "--data", args.data, "--out", args.clusters,
        "--min-core-l2s", str(args.min_core_l2s),
        "--max-per-target", str(args.max_per_target),
        "--ubiquity-threshold", str(args.ubiquity_threshold),
    ], soft_block=True)
    # Strip " written to output/clusters.json" from the done line
    print(re.sub(r"\s+written to \S+$", "", extract_done(out)))

    # Step 3 — Build (soft-block: report the issue but don't discard ingest output)
    build_cmd = [
        sys.executable, str(REPO_ROOT / "build.py"),
        "--data", args.data, "--out", args.out,
    ]
    if not analyze_blocked and os.path.exists(args.clusters):
        build_cmd += ["--clusters", args.clusters]
    if args.no_cache:
        build_cmd.append("--no-cache")
    out, build_blocked = run_step("Build", build_cmd, soft_block=True)

    # Parse the summary block from build.py output
    summary = {}
    for line in out.splitlines():
        s = line.strip()
        for key in ("Output:", "Accounts:", "Whitespace cells:", "Clusters:"):
            if s.startswith(key):
                summary[key] = s
    print(summary.get("Output:", "OK"))

    print("\nPipeline complete.")
    for key in ("Output:", "Accounts:", "Whitespace cells:", "Clusters:"):
        if key in summary:
            print(f"  {summary[key]}")

    if analyze_blocked:
        print("  WARNING: clusters.json was NOT written (analyze validation hard failure).")
    if build_blocked:
        print("  WARNING: whitespace-analyzer.html was NOT written (build validation hard failure).")
    if analyze_blocked or build_blocked or ingest_soft_blocked:
        sys.exit(2)


if __name__ == "__main__":
    main()
