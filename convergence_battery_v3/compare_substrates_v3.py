#!/usr/bin/env python3
"""
Cross-Substrate Convergence Analysis
Version: 3.0
Date: 2026-06-03

Changes over 1.0:
  (1) KEYED BY MODEL not substrate. v1.0 collapsed all azure runs into one
      key (last-writer-wins), making γ_between meaningless. Now each result
      file is keyed by model name, so six models = six distinct vectors.
  (2) γ_between computed properly across all model pairs, not just substrates.
  (3) JUDGE QUALITY section: measures how often Hermes (the fixed judge)
      produces None verdicts (ambiguous/unparseable output) per category.
      High judge-None rate on a category means the rubric or judge is the
      noise source, not the model. This is the 3.0 headline metric.
  (4) None-coverage report: per-test None rate across all models. Tests with
      high None rates are measurement gaps, not discriminators.
  (5) Weighted γ_between: test-count-weighted mean across categories,
      matching the γ_within calculation convention.
  (6) Archive keyed by model names not substrate string.

Usage:
  python compare_substrates_v3.py results/convergence_v29_*.json
  python compare_substrates_v3.py results/convergence_v29_azure_*.json results/convergence_v29_local_*.json
"""

import json
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


CATEGORIES = ["objective", "interpretive", "judge", "flapper"]


def load_result(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def model_key(result: Dict) -> str:
    """Unique key: model name. If duplicate model names exist, append substrate."""
    return result["metadata"]["model"]


def extract_consensus_vector(result: Dict) -> Dict[str, List[Optional[bool]]]:
    """
    From a single result, build a consensus verdict vector across passes.
    - All non-None passes agree → use that verdict
    - Any disagreement across passes → None (unstable, excluded)
    - All passes None → None (error/excluded)
    """
    vectors_by_pass = result["pass_verdict_vectors"]
    consensus = {cat: [] for cat in CATEGORIES}

    if not vectors_by_pass:
        return consensus

    n_passes = len(vectors_by_pass)
    first = vectors_by_pass["pass_1"]

    for cat in CATEGORIES:
        n_tests = len(first[cat])
        for i in range(n_tests):
            col = [vectors_by_pass[f"pass_{p}"][cat][i] for p in range(1, n_passes + 1)]
            non_none = [v for v in col if v is not None]
            if not non_none:
                consensus[cat].append(None)
            elif len(set(non_none)) == 1:
                consensus[cat].append(non_none[0])
            else:
                consensus[cat].append(None)  # flip across passes = unstable

    return consensus


def compute_gamma_between(model_vectors: Dict[str, Dict]) -> Dict[str, Optional[float]]:
    """
    γ_between per category: fraction of tests where at least two models disagree.
    Only tests where ALL models have non-None consensus are counted.
    """
    gamma = {}
    for cat in CATEGORIES:
        n = len(next(iter(model_vectors.values()))[cat])
        disagreements = 0
        usable = 0
        for i in range(n):
            col = [model_vectors[m][cat][i] for m in model_vectors]
            if any(v is None for v in col):
                continue
            usable += 1
            if len(set(col)) > 1:
                disagreements += 1
        gamma[cat] = (disagreements / usable) if usable else None
    return gamma


def compute_gamma_between_weighted(gamma_between: Dict, model_vectors: Dict) -> Optional[float]:
    """Test-count-weighted mean γ_between across categories."""
    num = 0
    den = 0
    first = next(iter(model_vectors.values()))
    for cat in CATEGORIES:
        g = gamma_between[cat]
        if g is None:
            continue
        n = len(first[cat])
        num += g * n
        den += n
    return (num / den) if den else None


def judge_quality_report(results: List[Dict]) -> Dict[str, Any]:
    """
    Measures judge quality: per-category None rate in verdict_logging.
    A high None rate means the judge is producing ambiguous/unparseable output
    — that's a judge problem, not a model problem.
    Also reports model-error None rate (blank/error responses from the model).
    """
    # Separate judge Nones (judge call errored/ambiguous) from
    # model Nones (empty response, error response)
    judge_none = defaultdict(lambda: {"total": 0, "none": 0})
    model_none = defaultdict(lambda: {"total": 0, "none": 0})

    for res in results:
        model = model_key(res)
        for entry in res.get("verdict_logging", []):
            cat = entry["category"]
            verdict = entry["verdict"]
            reason = entry.get("judge_reason", "")
            excluded = entry.get("excluded_from_gamma", False)

            if excluded:
                continue

            if cat == "objective":
                # objective uses rule-based verdict — track model Nones only
                model_none[cat]["total"] += 1
                if verdict is None:
                    model_none[cat]["none"] += 1
            else:
                # judge-evaluated: distinguish source of None
                if verdict is None:
                    if "judge call errored" in reason or "skipped: judge" in reason:
                        judge_none[cat]["none"] += 1
                    else:
                        model_none[cat]["none"] += 1
                judge_none[cat]["total"] += 1
                model_none[cat]["total"] += 1

    report = {}
    for cat in CATEGORIES:
        jn = judge_none[cat]
        mn = model_none[cat]
        report[cat] = {
            "judge_none_rate": (jn["none"] / jn["total"]) if jn["total"] else None,
            "model_none_rate": (mn["none"] / mn["total"]) if mn["total"] else None,
            "judge_none_count": jn["none"],
            "model_none_count": mn["none"],
            "total_verdicts": jn["total"],
        }
    return report


def none_coverage(model_vectors: Dict) -> Dict[str, Dict[str, int]]:
    """Per-category, per-position None count across all models."""
    coverage = {}
    n_models = len(model_vectors)
    for cat in CATEGORIES:
        n = len(next(iter(model_vectors.values()))[cat])
        coverage[cat] = {}
        for i in range(n):
            none_count = sum(1 for m in model_vectors if model_vectors[m][cat][i] is None)
            if none_count > 0:
                coverage[cat][i] = none_count
    return coverage


def verdict_hash(vector: Dict[str, List]) -> str:
    flat = []
    for cat in CATEGORIES:
        for v in vector[cat]:
            flat.append("T" if v is True else ("F" if v is False else "N"))
    return hashlib.sha3_256("".join(flat).encode()).hexdigest()


def print_report(results: List[Dict], model_vectors: Dict,
                 gamma_between: Dict, jq: Dict, nc: Dict) -> None:
    models = list(model_vectors.keys())
    print(f"\n{'='*70}")
    print(f"CROSS-MODEL CONVERGENCE ANALYSIS v3.0")
    print(f"{'='*70}\n")
    print(f"Models ({len(models)}):")
    for res in results:
        m = model_key(res)
        gw = res["wobble_metrics"].get("overall_weighted")
        sub = res["metadata"]["substrate"]
        gw_str = f"{gw:.4f}" if gw is not None else "  n/a"
        print(f"  {m:<25} substrate={sub:<12} γ_within={gw_str}")

    print(f"\n{'='*70}")
    print(f"JUDGE QUALITY  (fixed judge: Hermes-3-Llama-3.1-8B)")
    print(f"{'='*70}")
    print(f"  {'Category':<14} {'Judge-None%':<14} {'Model-None%':<14} {'Total verdicts'}")
    print(f"  {'-'*60}")
    for cat in CATEGORIES:
        q = jq[cat]
        jnr = f"{q['judge_none_rate']:.3f}" if q['judge_none_rate'] is not None else "  n/a"
        mnr = f"{q['model_none_rate']:.3f}" if q['model_none_rate'] is not None else "  n/a"
        print(f"  {cat:<14} {jnr:<14} {mnr:<14} {q['total_verdicts']}")
    print(f"\n  Judge-None% = judge produced ambiguous/unparseable output")
    print(f"  Model-None% = model returned blank/error (excluded from gamma)")

    print(f"\n{'='*70}")
    print(f"γ_BETWEEN (cross-model divergence)")
    print(f"{'='*70}")
    weighted = compute_gamma_between_weighted(gamma_between, model_vectors)
    for cat in CATEGORIES:
        g = gamma_between[cat]
        gstr = f"{g:.4f}" if g is not None else "  n/a (all tests had at least one None)"
        print(f"  {cat:<14} {gstr}")
    wstr = f"{weighted:.4f}" if weighted is not None else "  n/a"
    print(f"\n  γ_between (test-weighted): {wstr}")

    print(f"\n{'='*70}")
    print(f"NONE COVERAGE  (positions with ≥1 model returning None)")
    print(f"{'='*70}")
    any_gaps = False
    for cat in CATEGORIES:
        gaps = nc[cat]
        if gaps:
            any_gaps = True
            print(f"  {cat}: positions {dict(gaps)} ({len(gaps)} test(s) with gaps)")
    if not any_gaps:
        print(f"  None — all tests fully resolved across all models")

    print(f"\n{'='*70}")
    print(f"DISCRIMINATORS  (tests where models disagree)")
    print(f"{'='*70}")
    any_disc = False
    for cat in CATEGORIES:
        n = len(model_vectors[models[0]][cat])
        disc = []
        for i in range(n):
            col = {m: model_vectors[m][cat][i] for m in models}
            non_none = [v for v in col.values() if v is not None]
            if len(set(non_none)) > 1:
                disc.append((i, col))
        if disc:
            any_disc = True
            print(f"\n  {cat.upper()} ({len(disc)} discriminator(s)):")
            for idx, col in disc:
                row = "  ".join(f"{m[:16]}={'P' if v is True else ('F' if v is False else 'N')}"
                                for m, v in col.items())
                print(f"    [{idx:02d}] {row}")
    if not any_disc:
        print(f"  None — all models agree on all resolved tests")

    print(f"\n{'='*70}")
    print(f"VERDICT HASHES  (C-seed candidates)")
    print(f"{'='*70}")
    hashes = {m: verdict_hash(model_vectors[m]) for m in models}
    for m, h in hashes.items():
        print(f"  {m:<25} {h[:32]}...")
    unique = set(hashes.values())
    if len(unique) == 1:
        print(f"\n  UNIVERSAL C-SEED: all models have identical consensus vectors")
        print(f"  C-seed: {list(unique)[0]}")
    else:
        print(f"\n  NO UNIVERSAL C-SEED: {len(unique)} unique hashes across {len(models)} models")
    print()


def archive(results: List[Dict], model_vectors: Dict,
            gamma_between: Dict, jq: Dict, out_dir: str = "results") -> str:
    Path(out_dir).mkdir(exist_ok=True)
    ts = results[0]["metadata"]["timestamp"].replace(":", "-")[:19]
    names = "-".join(sorted(model_key(r)[:8] for r in results))
    path = Path(out_dir) / f"comparison_v30_{names}_{ts}.json"
    output = {
        "version": "3.0",
        "timestamp": ts,
        "models": [model_key(r) for r in results],
        "gamma_within": {model_key(r): r["wobble_metrics"].get("overall_weighted") for r in results},
        "gamma_between": gamma_between,
        "gamma_between_weighted": compute_gamma_between_weighted(gamma_between, model_vectors),
        "judge_quality": jq,
        "verdict_hashes": {m: verdict_hash(model_vectors[m]) for m in model_vectors},
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"archived -> {path}")
    return str(path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: compare_substrates_v3.py <result_file> [<result_file> ...]")
        sys.exit(1)

    results = []
    model_vectors = {}
    seen_models = {}

    print(f"Loading {len(sys.argv) - 1} result file(s)...")
    for fpath in sys.argv[1:]:
        try:
            res = load_result(fpath)
            key = model_key(res)
            # Deduplicate: if same model appears twice, append substrate
            if key in seen_models:
                key = f"{key}[{res['metadata']['substrate']}]"
            seen_models[key] = True
            results.append(res)
            model_vectors[key] = extract_consensus_vector(res)
            print(f"  OK {key}")
        except Exception as e:
            print(f"  FAIL {fpath}: {e}")
            sys.exit(1)

    gamma_between = compute_gamma_between(model_vectors)
    jq = judge_quality_report(results)
    nc = none_coverage(model_vectors)

    print_report(results, model_vectors, gamma_between, jq, nc)
    archive(results, model_vectors, gamma_between, jq)
