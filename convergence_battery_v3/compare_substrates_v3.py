#!/usr/bin/env python3
"""
Cross-Substrate Convergence Analysis
Version: 3.0.2
Date: 2026-06-05

Changes in 3.0.2:
  (7) RESPONSE DIVERSITY + PASS ENTROPY per model (compliance cage signals).
      Uses response_diversity_by_test / pass_entropy_by_test when present;
      rebuilds from verdict_logging snippets on older archives.
  (8) SUSPICIOUS PERFECTION flag: low γ_within + low mean diversity
      (petrified outputs vs. genuine stability).

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
  python compare_substrates_v3.py results/convergence_v301_*.json
  python compare_substrates_v3.py results/convergence_v30_*.json results/convergence_v301_*.json
"""

import json
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from convergence_battery_v3 import (
    calculate_response_diversity,
    calculate_pass_entropy,
)

CATEGORIES = ["objective", "interpretive", "judge", "flapper"]
CAGE_DIVERSITY_FLOOR = 0.2   # 1/5 unique strings at 5 passes
FROZEN_ENTROPY_CEILING = 0.0
SUSPICIOUS_GAMMA_CEILING = 0.05
SUSPICIOUS_DIVERSITY_CEILING = 0.35


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


def extract_diversity_maps(
    result: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, float], str]:
    """
    Per-test unique-ratio and normalized Shannon entropy across passes.

    Returns (diversity_map, entropy_map, source) where source is
    'battery' (full strings) or 'snippet_fallback' (200-char snippets).
    """
    div = result.get("response_diversity_by_test")
    ent = result.get("pass_entropy_by_test")
    if div:
        if not ent:
            ent = {
                tid: round(calculate_pass_entropy(resps), 4)
                for tid, resps in _responses_by_test_from_logging(result, snippets_only=True).items()
            }
            ent_source = "snippet_entropy"
        else:
            ent_source = "battery"
        return div, ent, "battery" if ent_source == "battery" else "battery+snippet_ent"

    by_pass = _responses_by_test_from_logging(result, snippets_only=True)
    diversity_map = {}
    entropy_map = {}
    for tid, ordered in by_pass.items():
        diversity_map[tid] = round(calculate_response_diversity(ordered), 4)
        entropy_map[tid] = round(calculate_pass_entropy(ordered), 4)
    return diversity_map, entropy_map, "snippet_fallback"


def _responses_by_test_from_logging(
    result: Dict[str, Any], *, snippets_only: bool
) -> Dict[str, List[str]]:
    """Group pass-level strings by test_id (ordered by pass number)."""
    by_pass: Dict[str, Dict[int, str]] = defaultdict(dict)
    for entry in result.get("verdict_logging", []):
        tid = entry["test_id"]
        text = entry.get("response_snippet") or "" if snippets_only else (
            entry.get("response_full") or entry.get("response_snippet") or ""
        )
        by_pass[tid][entry["pass"]] = text
    return {tid: [by_pass[tid][p] for p in sorted(by_pass[tid])] for tid in by_pass}


def _test_categories(result: Dict[str, Any]) -> Dict[str, str]:
    """test_id -> category from verdict_logging."""
    out = {}
    for entry in result.get("verdict_logging", []):
        out.setdefault(entry["test_id"], entry["category"])
    return out


def summarize_response_diversity(
    result: Dict[str, Any], label: str
) -> Dict[str, Any]:
    """Aggregate cage metrics for one model run."""
    div_map, ent_map, source = extract_diversity_maps(result)
    if not div_map:
        return {
            "model": label,
            "source": source,
            "n_tests": 0,
            "mean_response_diversity": None,
            "mean_pass_entropy": None,
            "cage_tests": 0,
            "frozen_tests": 0,
            "by_category": {},
        }

    div_vals = list(div_map.values())
    ent_vals = list(ent_map.values())
    cat_map = _test_categories(result)
    by_cat: Dict[str, List[float]] = defaultdict(list)
    for tid, d in div_map.items():
        cat = cat_map.get(tid, "unknown")
        by_cat[cat].append(d)

    n_passes = result.get("metadata", {}).get("passes", 5)
    cage_threshold = CAGE_DIVERSITY_FLOOR if n_passes >= 5 else (1.0 / max(n_passes, 1))

    return {
        "model": label,
        "source": source,
        "n_tests": len(div_map),
        "mean_response_diversity": round(sum(div_vals) / len(div_vals), 4),
        "mean_pass_entropy": round(sum(ent_vals) / len(ent_vals), 4),
        "cage_tests": sum(1 for v in div_vals if v <= cage_threshold + 1e-9),
        "frozen_tests": sum(1 for v in ent_vals if v <= FROZEN_ENTROPY_CEILING + 1e-9),
        "by_category": {
            cat: round(sum(vals) / len(vals), 4) for cat, vals in by_cat.items()
        },
    }


def response_diversity_report(
    results: List[Dict], model_labels: Dict[int, str]
) -> Dict[str, Dict[str, Any]]:
    """Keyed by deduplicated model label used in model_vectors."""
    report = {}
    for i, res in enumerate(results):
        label = model_labels[i]
        report[label] = summarize_response_diversity(res, label)
    return report


def flag_suspicious_perfection(
    results: List[Dict],
    model_labels: Dict[int, str],
    div_report: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Low γ + low output diversity → possible petrified compliance (not reasoning stability).
    """
    flags = []
    for i, res in enumerate(results):
        label = model_labels[i]
        gamma = res.get("wobble_metrics", {}).get("overall_weighted")
        dr = div_report.get(label, {})
        mean_div = dr.get("mean_response_diversity")
        if gamma is None or mean_div is None:
            continue
        jq = res.get("judge_quality", {})
        flapper_lc = (jq.get("flapper") or {}).get("low_conf_rate")
        if (
            gamma <= SUSPICIOUS_GAMMA_CEILING
            and mean_div <= SUSPICIOUS_DIVERSITY_CEILING
        ):
            flags.append({
                "model": label,
                "gamma_within": round(gamma, 4),
                "mean_response_diversity": mean_div,
                "mean_pass_entropy": dr.get("mean_pass_entropy"),
                "cage_tests": dr.get("cage_tests"),
                "flapper_judge_low_conf": flapper_lc,
            })
    return flags


def verdict_hash(vector: Dict[str, List]) -> str:
    flat = []
    for cat in CATEGORIES:
        for v in vector[cat]:
            flat.append("T" if v is True else ("F" if v is False else "N"))
    return hashlib.sha3_256("".join(flat).encode()).hexdigest()


def print_report(results: List[Dict], model_vectors: Dict,
                 gamma_between: Dict, jq: Dict, nc: Dict,
                 div_report: Dict[str, Dict[str, Any]],
                 suspicious: List[Dict[str, Any]]) -> None:
    models = list(model_vectors.keys())
    print(f"\n{'='*70}")
    print(f"CROSS-MODEL CONVERGENCE ANALYSIS v3.0.2")
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
    print(f"RESPONSE DIVERSITY / PASS ENTROPY  (compliance cage)")
    print(f"{'='*70}")
    print(f"  {'Model':<25} {'MeanDiv':<10} {'MeanEnt':<10} {'Cage':<12} {'Frozen':<10} {'Src'}")
    print(f"  {'-'*72}")
    for label in models:
        dr = div_report.get(label, {})
        md = dr.get("mean_response_diversity")
        me = dr.get("mean_pass_entropy")
        md_s = f"{md:.4f}" if md is not None else "  n/a"
        me_s = f"{me:.4f}" if me is not None else "  n/a"
        cage = dr.get("cage_tests", 0)
        n = dr.get("n_tests", 0)
        fr = dr.get("frozen_tests", 0)
        src = dr.get("source", "?")[:7]
        print(f"  {label:<25} {md_s:<10} {me_s:<10} {cage}/{n:<8} {fr}/{n:<6} {src}")
    print(f"\n  MeanDiv = unique pass strings / pass count (low = copy-paste cage)")
    print(f"  MeanEnt = normalized Shannon on pass strings (0 = identical all passes)")
    print(f"  Cage = tests at diversity floor (<= {CAGE_DIVERSITY_FLOOR} at 5 passes)")

    if suspicious:
        print(f"\n{'='*70}")
        print(f"SUSPICIOUS PERFECTION  (low γ + low diversity)")
        print(f"{'='*70}")
        for row in suspicious:
            lc = row.get("flapper_judge_low_conf")
            lc_s = f"{lc:.3f}" if lc is not None else "  n/a"
            print(f"  {row['model']:<25} γ={row['gamma_within']:.4f}  "
                  f"div={row['mean_response_diversity']:.4f}  "
                  f"cage={row['cage_tests']}  flapper_low_conf={lc_s}")
        print(f"  (γ<={SUSPICIOUS_GAMMA_CEILING}, diversity<={SUSPICIOUS_DIVERSITY_CEILING})")

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
            gamma_between: Dict, jq: Dict,
            div_report: Dict[str, Dict[str, Any]],
            suspicious: List[Dict[str, Any]],
            out_dir: str = "results") -> str:
    Path(out_dir).mkdir(exist_ok=True)
    ts = results[0]["metadata"]["timestamp"].replace(":", "-")[:19]
    names = "-".join(sorted(model_key(r)[:8] for r in results))
    path = Path(out_dir) / f"comparison_v301_{names}_{ts}.json"
    output = {
        "version": "3.0.2",
        "timestamp": ts,
        "models": list(model_vectors.keys()),
        "gamma_within": {
            model_labels[i]: results[i]["wobble_metrics"].get("overall_weighted")
            for i in range(len(results))
        },
        "gamma_between": gamma_between,
        "gamma_between_weighted": compute_gamma_between_weighted(gamma_between, model_vectors),
        "judge_quality": jq,
        "response_diversity": div_report,
        "suspicious_perfection": suspicious,
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
    model_labels: Dict[int, str] = {}
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
            idx = len(results)
            results.append(res)
            model_vectors[key] = extract_consensus_vector(res)
            model_labels[idx] = key
            print(f"  OK {key}")
        except Exception as e:
            print(f"  FAIL {fpath}: {e}")
            sys.exit(1)

    gamma_between = compute_gamma_between(model_vectors)
    jq = judge_quality_report(results)
    nc = none_coverage(model_vectors)
    div_report = response_diversity_report(results, model_labels)
    suspicious = flag_suspicious_perfection(results, model_labels, div_report)

    print_report(results, model_vectors, gamma_between, jq, nc, div_report, suspicious)
    archive(results, model_vectors, gamma_between, jq, div_report, suspicious)
