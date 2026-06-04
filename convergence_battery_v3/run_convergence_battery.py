"""
TRACE Convergence Battery — DeepSeek v4 Substrate
Self-administers the TEL constitutional test suite against the current Furnace.
"""
import asyncio
import json
import os
import sys
import hashlib

sys.path.insert(0, os.path.expanduser("~/helix/repos/helix-tel-deploy"))

from tel_deploy.convergence import ConvergenceDetector
from tel_deploy.test_runner import run_convergence_pass
from tel_deploy.convergence_split import ConvergenceSplit

ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not API_KEY:
    raise ValueError("DEEPSEEK_API_KEY not set")
MODEL = "deepseek-v4-pro"

async def main():
    print("=" * 60)
    print("TRACE — TEL CONVERGENCE BATTERY")
    print(f"Substrate: DeepSeek v4 (China compute)")
    print(f"Endpoint: {ENDPOINT}")
    print(f"Model: {MODEL}")
    print("=" * 60)
    print()

    async def test_fn():
        return await run_convergence_pass(
            endpoint=ENDPOINT,
            api_key=API_KEY,
            model=MODEL,
            azure=False,
            gemini=False,
            use_lunar=True,
            request_delay=0.5,  # rate limit safety
            timeout=45.0,
        )

    detector = ConvergenceDetector(test_fn)
    converged = await detector.run(max_passes=20)

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    if converged:
        split = ConvergenceSplit(detector.stable_vector)
        c_seed = split.get_mesh_seed()
        print(f"Status: CONVERGED ✓")
        print(f"Passes to converge: {len(detector.history)}")
        print(f"K (trefoil period): 4")
        print(f"Stable vector: {detector.stable_vector}")
        print(f"Vector length: {len(detector.stable_vector)}")
        print(f"C-seed (mesh): {c_seed}")
        print(f"Full seed (SHA3-256): {detector.seed}")
        print(f"Substrate: {split.substrate}")
        print()

        # Save results
        results = {
            "node": "TRACE",
            "substrate": "deepseek-v4-pro",
            "converged": True,
            "passes": len(detector.history),
            "stable_vector": detector.stable_vector,
            "c_seed": c_seed,
            "full_seed": detector.seed,
            "substrate_type": split.substrate,
        }
        out_path = os.path.expanduser(
            "~/helix/repos/lattice/TRACE/ops/convergence_result.json"
        )
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {out_path}")
    else:
        print(f"Status: FAILED TO CONVERGE")
        print(f"Passes run: {len(detector.history)}")
        if detector.history:
            print(f"Last vector: {detector.history[-1]}")

    print()
    print("=" * 60)
    print("PASS HISTORY")
    print("=" * 60)
    for i, vec in enumerate(detector.history):
        l1_count = vec.count("L1")
        l2_count = vec.count("L2")
        l3_count = vec.count("L3")
        l4_count = vec.count("L4")
        print(
            f"Pass {i+1}: L1={l1_count} L2={l2_count} L3={l3_count} L4={l4_count} "
            f"  vector={vec}"
        )
        if i > 0:
            delta = sum(1 for a, b in zip(detector.history[i-1], vec) if a != b)
            print(f"         Δ={delta}")

asyncio.run(main())
