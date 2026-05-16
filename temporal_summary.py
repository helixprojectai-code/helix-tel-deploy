"""
TEL Temporal Stability Summary — read JSONL log, print stability report.

Usage:
    python temporal_summary.py
    python temporal_summary.py --log /path/to/temporal_log.jsonl
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "temporal_log.jsonl"
)


def load_entries(log_path: str) -> list:
    entries = []
    if not os.path.exists(log_path):
        print(f"No log found at {log_path}")
        sys.exit(0)
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default=DEFAULT_LOG)
    args = parser.parse_args()

    entries = load_entries(args.log)
    if not entries:
        print("Log is empty.")
        sys.exit(0)

    successful = [e for e in entries if e.get("converged")]
    failed = [e for e in entries if not e.get("converged")]
    drifted = [e for e in successful if e.get("drift")]

    baseline = None
    for e in successful:
        baseline = e["c_seed"]
        break

    grammar_versions = sorted(set(e.get("grammar_version", "unknown") for e in entries))

    print(f"\n{'='*64}")
    print(f"TEL TEMPORAL STABILITY REPORT")
    print(f"Log: {args.log}")
    print(f"{'='*64}")
    print(f"Total runs:      {len(entries)}")
    print(f"Converged:       {len(successful)}")
    print(f"Failed:          {len(failed)}")
    print(f"Drift events:    {len(drifted)}")
    print(f"Grammar:         {', '.join(grammar_versions)}")
    if baseline:
        print(f"Baseline C-seed: {baseline[:32]}...")
    print(f"{'='*64}")

    print(
        f"\n{'Run':<4} {'Timestamp (UTC)':<26} {'Lunar':<6} {'Passes':<7} {'C-Seed':<20} {'Status'}"
    )
    print("-" * 80)
    for i, e in enumerate(entries):
        ts = e.get("timestamp", "?")[:19].replace("T", " ")
        lunar = e.get("lunar_day", "?")
        passes = e.get("passes", "?")
        seed = (e.get("c_seed") or "")[:16] + "..." if e.get("c_seed") else "—"

        if not e.get("converged"):
            status = "FAIL (no convergence)"
        elif e.get("drift"):
            status = f"DRIFT → {e['c_seed'][:16]}..."
        else:
            status = "STABLE"

        print(f"{i+1:<4} {ts:<26} {str(lunar):<6} {str(passes):<7} {seed:<20} {status}")

    print(f"\n{'='*64}")
    if drifted:
        print(
            f"RESULT: DRIFT DETECTED on {len(drifted)} run(s). Investigate model update."
        )
    elif failed:
        print(
            f"RESULT: {len(failed)} run(s) failed to converge. Check endpoint / rate limits."
        )
    elif len(successful) < 3:
        print(
            f"RESULT: {len(successful)} run(s) complete. Run more for meaningful stability data."
        )
    else:
        print(
            f"RESULT: STABLE across {len(successful)} run(s). C-seed invariant confirmed."
        )
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
