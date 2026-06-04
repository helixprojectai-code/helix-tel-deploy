#!/usr/bin/env python3
"""
Cross-Substrate Convergence Analysis
Version: 1.0
Date: 2026-06-02

Compares verdict vectors from multiple substrate runs and computes:
  - γ_between: cross-substrate divergence (how much do verdicts differ across substrates?)
  - Per-test discriminatory power (which tests fail on some substrates but pass on others?)
  - Verdict vector alignment (do all substrates agree on which tests pass/fail?)
  - C-seed hypothesis (if all substrates have identical verdict vectors, their hashes match)

Usage:
  python compare_substrates.py <result_file_1> <result_file_2> [<result_file_3> ...]
  python compare_substrates.py results/convergence_v23_*.json
"""

import json
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict

def load_result(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)

def extract_verdict_vectors(result: Dict) -> Dict[str, List]:
    """
    From a single substrate result, extract the final verdict vectors.
    Returns: { 'objective': [...], 'interpretive': [...], 'judge': [...], 'flapper': [...] }
    (averaged/consensus across the N passes, handling None)
    """
    vectors_by_pass = result["pass_verdict_vectors"]
    categories = ["objective", "interpretive", "judge", "flapper"]

    consensus = {cat: [] for cat in categories}

    if not vectors_by_pass:
        return consensus

    # Get first pass to know dimensions
    first_pass_key = next(iter(vectors_by_pass.keys()))
    first_pass = vectors_by_pass[first_pass_key]

    for cat in categories:
        n_tests = len(first_pass[cat])

        for test_idx in range(n_tests):
            verdicts_across_passes = [
                vectors_by_pass[f"pass_{p}"][cat][test_idx]
                for p in range(1, len(vectors_by_pass) + 1)
            ]

            # Consensus: if all non-None agree, use that; else None (discordant)
            non_none = [v for v in verdicts_across_passes if v is not None]
            if not non_none:
                consensus[cat].append(None)  # all passes errored
            elif len(set(non_none)) == 1:
                consensus[cat].append(non_none[0])  # all agree
            else:
                consensus[cat].append(None)  # disagreement across passes -> excluded

    return consensus

def compute_gamma_between(substrate_verdicts: Dict[str, Dict]) -> Dict[str, float]:
    """
    Compute γ_between per category: what fraction of tests have inconsistent verdicts
    across substrates?

    Returns: { 'objective': γ, 'interpretive': γ, ... }
    """
    categories = ["objective", "interpretive", "judge", "flapper"]
    gamma_between = {}

    for cat in categories:
        n_tests = len(next(iter(substrate_verdicts.values()))[cat])
        disagreements = 0
        usable = 0

        for test_idx in range(n_tests):
            verdicts = [substrate_verdicts[sub][cat][test_idx] for sub in substrate_verdicts]

            # Skip if any substrate has None (error/excluded)
            if any(v is None for v in verdicts):
                continue

            usable += 1
            # Disagreement: not all verdicts are the same
            if len(set(verdicts)) > 1:
                disagreements += 1

        gamma = (disagreements / usable) if usable > 0 else None
        gamma_between[cat] = gamma

    return gamma_between

def verdict_hash(verdict_vector: Dict[str, List]) -> str:
    """
    Hash of the verdict vector (candidate for C-seed).
    Flattens all categories into a canonical byte string and hashes.
    """
    flat = []
    for cat in ["objective", "interpretive", "judge", "flapper"]:
        for v in verdict_vector[cat]:
            flat.append("T" if v is True else ("F" if v is False else "N"))

    canonical = "".join(flat).encode()
    return hashlib.sha3_256(canonical).hexdigest()

def print_summary(results: List[Dict], substrate_verdicts: Dict, gamma_between: Dict) -> None:
    print(f"\n{'='*70}")
    print(f"CROSS-SUBSTRATE CONVERGENCE ANALYSIS")
    print(f"{'='*70}\n")

    # List substrates
    subs = list(substrate_verdicts.keys())
    print(f"Substrates: {', '.join(subs)}")

    # Print γ_within for each (from original results)
    print(f"\nγ_within (within-substrate wobble):")
    for res in results:
        sub = res["metadata"]["substrate"]
        m = res["wobble_metrics"]
        overall = m.get("overall_weighted")
        print(f"  {sub:<12} {overall:.4f}" if overall else f"  {sub:<12} n/a")

    # Print γ_between (cross-substrate)
    print(f"\nγ_between (cross-substrate divergence):")
    for cat in ["objective", "interpretive", "judge", "flapper"]:
        g = gamma_between[cat]
        print(f"  {cat:<12} {g:.4f}" if g else f"  {cat:<12} n/a")

    # Compute and print C-seed hashes
    print(f"\nVerdict vector hashes (C-seed candidates):")
    for sub in subs:
        vv = substrate_verdicts[sub]
        h = verdict_hash(vv)
        print(f"  {sub:<12} {h[:32]}...")

    # Check convergence
    hashes = [verdict_hash(substrate_verdicts[sub]) for sub in subs]
    if len(set(hashes)) == 1:
        print(f"\n✓ UNIVERSAL C-SEED: all substrates have identical verdict vectors")
        print(f"  C-seed: {hashes[0]}")
    else:
        print(f"\n✗ NO UNIVERSAL C-SEED: verdict vectors differ across substrates")
        print(f"  Unique hashes: {len(set(hashes))}")

    # Discriminatory analysis
    print(f"\n{'='*70}")
    print(f"TEST DISCRIMINATORY POWER")
    print(f"{'='*70}\n")

    categories = ["objective", "interpretive", "judge", "flapper"]
    discriminators = defaultdict(list)

    for cat in categories:
        n_tests = len(substrate_verdicts[subs[0]][cat])
        for test_idx in range(n_tests):
            verdicts = [substrate_verdicts[sub][cat][test_idx] for sub in subs]
            if any(v is None for v in verdicts):
                continue
            if len(set(verdicts)) > 1:
                # This test discriminates
                test_id = f"{cat.upper()[:3]}_{test_idx:03d}"
                v_str = " | ".join([str(v) for sub, v in zip(subs, verdicts)])
                discriminators[cat].append((test_id, v_str))

    for cat in categories:
        if discriminators[cat]:
            print(f"{cat.upper()} ({len(discriminators[cat])} discriminators):")
            for test_id, verdict_str in discriminators[cat][:5]:  # show first 5
                print(f"  {test_id}  {verdict_str}")
            if len(discriminators[cat]) > 5:
                print(f"  ... and {len(discriminators[cat]) - 5} more")
        else:
            print(f"{cat.upper()}: all substrates agree")

    print()

def archive(results: List[Dict], substrate_verdicts: Dict, gamma_between: Dict, out_dir: str = "results") -> str:
    from pathlib import Path
    Path(out_dir).mkdir(exist_ok=True)

    ts = results[0]["metadata"]["timestamp"].replace(":", "-")[:19]
    subs = "-".join(sorted([r["metadata"]["substrate"] for r in results]))
    path = Path(out_dir) / f"convergence_comparison_{subs}_{ts}.json"

    output = {
        "timestamp": ts,
        "substrates": list(substrate_verdicts.keys()),
        "gamma_between": gamma_between,
        "verdict_hashes": {sub: verdict_hash(substrate_verdicts[sub]) for sub in substrate_verdicts},
        "gamma_within": {r["metadata"]["substrate"]: r["wobble_metrics"].get("overall_weighted") for r in results},
    }

    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"archived -> {path}")
    return str(path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: compare_substrates.py <result_file> [<result_file> ...]")
        sys.exit(1)

    result_files = sys.argv[1:]
    results = []
    substrate_verdicts = {}

    print(f"Loading {len(result_files)} result file(s)...")
    for fpath in result_files:
        try:
            res = load_result(fpath)
            sub = res["metadata"]["substrate"]
            results.append(res)
            substrate_verdicts[sub] = extract_verdict_vectors(res)
            print(f"  ✓ {sub}")
        except Exception as e:
            print(f"  ✗ {fpath}: {e}")
            sys.exit(1)

    gamma_between = compute_gamma_between(substrate_verdicts)
    print_summary(results, substrate_verdicts, gamma_between)
    archive(results, substrate_verdicts, gamma_between)
