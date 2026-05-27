"""
TEL convergence battery — local Ollama endpoint.
Usage: python3 test_ollama_local.py <model-name>
Example: python3 test_ollama_local.py qwen2.5:7b
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tel_deploy.convergence import ConvergenceDetector
from tel_deploy.convergence_split import ConvergenceSplit, GRAMMAR_VERSION
from tel_deploy.test_runner import run_convergence_pass

OLLAMA_ENDPOINT = "http://embassy.helixaiinnovations.ca:11434/v1/chat/completions"
TIMEOUT = 300.0

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("tel.ollama")

KNOWN_SEEDS = {
    "c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac": "Universal",
    "92de78db823f470ece6f78e4a7fab31fb0392f7df2edd4f2bc71e1ad332ba727": "Llama-small",
    "18f54f0556a9f880": "Gemma-small",
}


def identify_topology(c_seed: str) -> str:
    for seed, name in KNOWN_SEEDS.items():
        if c_seed.startswith(seed):
            return name
    return "NEW — unclassified"


async def run_battery(model: str) -> dict:
    print(f"\n{'='*60}")
    print(f"TEL Battery — {model}")
    print(f"Grammar:  {GRAMMAR_VERSION}")
    print(f"Endpoint: {OLLAMA_ENDPOINT}")
    print("=" * 60)

    async def test_fn():
        print(f"  [{model}] running convergence pass...")
        return await run_convergence_pass(
            endpoint=OLLAMA_ENDPOINT,
            api_key="ollama",
            model=model,
            azure=False,
            gemini=False,
            timeout=TIMEOUT,
            fresh_connection=True,
            cache_prompt=False,
        )

    detector = ConvergenceDetector(test_fn)
    success = await detector.run(max_passes=20)

    result = {
        "model": model,
        "converged": success,
        "passes": len(detector.history),
        "stable_vector": detector.stable_vector,
        "grammar_version": GRAMMAR_VERSION,
        "c_seed": None,
        "b_vector": None,
        "b_fingerprint": None,
        "substrate": None,
        "topology": None,
    }

    if success:
        split = ConvergenceSplit(detector.stable_vector, grammar_version=GRAMMAR_VERSION)
        result["c_seed"] = split.c_seed
        result["b_vector"] = split.b_vector
        result["b_fingerprint"] = split.b_fingerprint
        result["substrate"] = split.substrate
        result["topology"] = identify_topology(split.c_seed)

        print(f"\nCONVERGED in {len(detector.history)} passes")
        print(f"Stable vector:  {detector.stable_vector}")
        print(f"C-seed:         {split.c_seed}")
        print(f"B-vector:       {split.b_vector}")
        print(f"B-fingerprint:  {split.b_fingerprint[:32]}...")
        print(f"Substrate:      {split.substrate}")
        print(f"Topology:       {result['topology']}")
    else:
        print(f"\nFAILED to converge in 20 passes")
        print(f"Last vector: {detector.history[-1] if detector.history else None}")

    return result


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_ollama_local.py <model-name>")
        sys.exit(1)

    model = sys.argv[1]
    result = await run_battery(model)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Model:     {result['model']}")
    print(f"Converged: {result['converged']}")
    print(f"Passes:    {result['passes']}")
    print(f"Topology:  {result.get('topology', 'N/A')}")
    print(f"C-seed:    {result.get('c_seed', 'N/A')}")
    print(f"B-vector:  {result.get('b_vector', 'N/A')}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
