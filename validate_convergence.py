"""
Multi-model convergence validation.
Runs convergence passes against all available model deployments and
compares C-seeds and B-fingerprints to verify cross-model invariance.

Supports multiple Azure endpoints for cross-region testing.
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tel_deploy.convergence import ConvergenceDetector
from tel_deploy.convergence_split import ConvergenceSplit
from tel_deploy.test_runner import run_convergence_pass

# --- Endpoints ---
ENDPOINTS = {
    "eastus2": "https://your-azure-endpoint.services.ai.azure.com",
    "canadacentral": "https://your-azure-endpoint-2.cognitiveservices.azure.com",
    "crypt": "https://your-azure-endpoint-3.cognitiveservices.azure.com",
    "crypt_sai": "https://your-azure-endpoint-3.services.ai.azure.com",
}

API_KEY = os.environ.get("TEL_AZURE_KEY", "")
API_KEY_CANADA = os.environ.get("TEL_AZURE_KEY_CANADA", API_KEY)
API_KEY_CRYPT = os.environ.get("TEL_AZURE_KEY_CRYPT", API_KEY)

ENDPOINT_KEYS = {
    "eastus2": API_KEY,
    "canadacentral": API_KEY_CANADA,
    "crypt": API_KEY_CRYPT,
    "crypt_sai": API_KEY_CRYPT,
}

# --- Deployment registry ---
# Each entry: (label, model_name, region)
# label is used in output; model_name must match the Azure deployment name.
DEPLOYMENTS = [
    # East US 2 — primary fleet
    ("gpt-4o", "gpt-4o", "eastus2"),
    ("gpt-5.4-nano", "gpt-5.4-nano", "eastus2"),
    ("gpt-5.5", "gpt-5.5", "eastus2"),
    ("DeepSeek-V3.2", "DeepSeek-V3.2", "eastus2"),
    ("Kimi-K2.5", "Kimi-K2.5", "eastus2"),
    # Canada Central — cross-region invariance test
    ("DeepSeek-V3.2[CA]", "DeepSeek-V3.2", "canadacentral"),
    ("Kimi-K2.5[CA]", "Kimi-K2.5", "canadacentral"),
    # Helix-Lattice-RG — crypt resource
    ("gpt-4o-mini", "gpt-4o-mini", "crypt"),
    ("Llama-3.3-70B", "Llama-3.3-70B-Instruct", "crypt_sai"),
]

KNOWN_C_SEED = "16ce8df91c0d04ba"

LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "convergence_validation.log"
)


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, mode="w"),
            logging.StreamHandler(sys.stdout),
        ],
    )


async def validate_deployment(label: str, model: str, region: str) -> dict:
    endpoint = ENDPOINTS[region]
    api_key = ENDPOINT_KEYS[region]

    print(f"\n{'='*60}")
    print(f"MODEL: {label}  [{region}]")
    print("=" * 60)

    async def test_fn():
        print(f"  [{label}] running convergence pass...")
        return await run_convergence_pass(endpoint, api_key, model=model, azure=True)

    detector = ConvergenceDetector(test_fn)
    success = await detector.run(max_passes=20)

    result = {
        "label": label,
        "model": model,
        "region": region,
        "converged": success,
        "passes": len(detector.history),
        "stable_vector": detector.stable_vector,
        "seed": detector.seed,
        "c_seed": None,
        "b_vector": None,
        "b_fingerprint": None,
        "substrate": None,
        "c_seed_matches_known": None,
    }

    if success:
        split = ConvergenceSplit(detector.stable_vector)
        result["c_seed"] = split.c_seed
        result["b_vector"] = split.b_vector
        result["b_fingerprint"] = split.b_fingerprint
        result["substrate"] = split.substrate
        result["c_seed_matches_known"] = split.c_seed.startswith(KNOWN_C_SEED)

        print(f"  CONVERGED in {len(detector.history)} passes")
        print(f"  C-seed:      {split.c_seed[:32]}...")
        print(f"  B-vector:    {split.b_vector}")
        print(f"  Substrate:   {split.substrate}")
        print(f"  B-fingerprint: {split.b_fingerprint[:32]}...")
        print(f"  C-seed matches known: {result['c_seed_matches_known']}")
    else:
        print("  FAILED to converge in 20 passes")

    return result


async def run_temporal_stability(
    label: str, model: str, region: str, runs: int = 6
) -> list:
    """Run the same deployment N times independently to measure C-seed stability."""
    print(f"\n{'='*60}")
    print(f"TEMPORAL STABILITY: {label} x{runs}")
    print("=" * 60)

    results = []
    for i in range(runs):
        print(f"\n  --- Run {i+1}/{runs} ---")
        r = await validate_deployment(f"{label}[T{i+1}]", model, region)
        results.append(r)

    c_seeds = [r["c_seed"] for r in results if r["converged"]]
    unique = set(c_seeds)
    print(f"\n  Temporal stability: {len(c_seeds)}/{runs} converged")
    print(f"  Unique C-seeds: {len(unique)}")
    if len(unique) == 1:
        print(f"  STABLE: {c_seeds[0][:16]}...")
    else:
        print("  DRIFT DETECTED:")
        for s in unique:
            print(f"    {s[:16]}...")
    return results


async def main():
    setup_logging()
    log = logging.getLogger("validate")

    if not API_KEY:
        log.error("TEL_AZURE_KEY not set")
        sys.exit(1)

    log.info(f"Log file: {LOG_PATH}")
    print("TEL Mesh — Multi-Model Convergence Validation")
    print(f"Known C-seed prefix: {KNOWN_C_SEED}")
    print(f"Deployments: {len(DEPLOYMENTS)}")
    for label, model, region in DEPLOYMENTS:
        print(f"  {label:<22} {model:<20} [{region}]")

    # Phase 1: Full deployment battery
    results = []
    for label, model, region in DEPLOYMENTS:
        result = await validate_deployment(label, model, region)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)

    converged = [r for r in results if r["converged"]]
    failed = [r for r in results if not r["converged"]]
    c_seed_match = [r for r in converged if r["c_seed_matches_known"]]
    c_seed_new = [r for r in converged if not r["c_seed_matches_known"]]

    print(f"\nConverged:     {len(converged)}/{len(results)} deployments")
    print(f"C-seed match:  {len(c_seed_match)}/{len(converged)} converged")

    if c_seed_new:
        print("\nNEW C-seeds (investigate):")
        for r in c_seed_new:
            print(f"  {r['label']}: {r['c_seed'][:32]}...")

    if failed:
        print("\nFailed to converge:")
        for r in failed:
            print(f"  {r['label']} [{r['region']}]")

    # Cross-region invariance report
    cross_region_pairs = [
        ("DeepSeek-V3.2", "DeepSeek-V3.2[CA]"),
        ("Kimi-K2.5", "Kimi-K2.5[CA]"),
    ]
    region_map = {r["label"]: r for r in converged}
    print("\nCross-region invariance:")
    for a_label, b_label in cross_region_pairs:
        a = region_map.get(a_label)
        b = region_map.get(b_label)
        if a and b:
            c_match = a["c_seed"] == b["c_seed"]
            b_match = a["b_fingerprint"] == b["b_fingerprint"]
            print(f"  {a_label} vs {b_label}:")
            print(f"    C-seed invariant: {c_match}")
            print(f"    B-fingerprint invariant: {b_match}")
        else:
            print(f"  {a_label} vs {b_label}: one or both did not converge")

    print("\nB-fingerprint table:")
    print(
        f"  {'Label':<22} {'Region':<15} {'B-vector':<25} {'Substrate':<15} {'B-fp':<18} C-seed"
    )
    for r in converged:
        bv = str(r["b_vector"])
        c_short = r["c_seed"][:16] + "..." if r["c_seed"] else "n/a"
        match_marker = "✓" if r["c_seed_matches_known"] else "✗"
        print(
            f"  {r['label']:<22} {r['region']:<15} {bv:<25} {r['substrate']:<15} "
            f"{r['b_fingerprint'][:16]}...  {c_short} {match_marker}"
        )

    # Save full results
    out_path = os.path.join(
        os.path.dirname(__file__), "convergence_validation_results.json"
    )
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to: {out_path}")

    all_match = len(converged) == len(results) and len(c_seed_match) == len(results)
    if all_match:
        print("\nALL DEPLOYMENTS CONVERGED. C-seed universal invariant CONFIRMED.")
        sys.exit(0)
    else:
        print("\nWARNING: Not all deployments converged or C-seed mismatch detected.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
