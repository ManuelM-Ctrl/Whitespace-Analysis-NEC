"""
Export the distinct SAP Top Parent CRM IDs that need to be downloaded from the
Adoption Monitor (AM-TP).

Rule: include only rows where SAP Top Parent CRM ID != Planning Entity ID,
i.e. the account rolls up to a different top parent.

Output: a single-column CSV (header "Top Parent ID") with IDs zero-padded to
10 digits, written to example-data/top_parent_ids.csv by default.
"""

import argparse
import os
import sys

import pandas as pd

# Allow importing load_iaa from the project root regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ingest import load_iaa


def main():
    parser = argparse.ArgumentParser(description="Export Top Parent IDs for AM-TP download")
    parser.add_argument("--iaa", required=True, help="Path to IAA CSV file")
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: top_parent_ids.csv next to the IAA file)",
    )
    args = parser.parse_args()

    if args.out is None:
        args.out = os.path.join(os.path.dirname(os.path.abspath(args.iaa)), "top_parent_ids.csv")

    df = load_iaa(args.iaa)

    if "SAP Top Parent CRM ID" not in df.columns:
        print("ERROR: 'SAP Top Parent CRM ID' column not found in IAA file.", file=sys.stderr)
        sys.exit(1)

    mask = df["SAP Top Parent CRM ID"] != df["Planning Entity ID"]
    tp_ids = df.loc[mask, "SAP Top Parent CRM ID"].dropna().unique()

    # Zero-pad to 10 digits to match the format the AM download expects
    padded = sorted(str(tp_id).zfill(10) for tp_id in tp_ids if str(tp_id).strip())

    out_path = os.path.normpath(args.out)
    out = pd.DataFrame({"Top Parent ID": padded})
    out.to_csv(out_path, index=False)

    print(f"Wrote {len(padded)} Top Parent IDs to {out_path}")


if __name__ == "__main__":
    main()
