"""
Local model convergence test for LM Studio / Ollama / OpenAI-compatible local servers.
No API key required. Based on test_baseline_gemini.py pattern.

Usage:
    python test_baseline_local.py
    
Environment:
    TEL_LOCAL_ENDPOINT  (default: http://127.0.0.1:1234/v1/chat/completions)
    TEL_LOCAL_MODEL     (default: llama-3.1-nemotron-nano-4b-v1.1)
"""

import asyncio
import os

from tel_deploy.test_runner import run_convergence_pass
from tel_deploy.convergence_split import ConvergenceSplit

ENDPOINT = os.environ.get("TEL_LOCAL_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions")
MODEL = os.environ.get("TEL_LOCAL_MODEL", "llama-3.1-nemotron-nano-4b-v1.1")

KNOWN_C_SEED = "c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac"


async def main():
    print(f"{'='*60}")
    print(f"LOCAL MODEL CONVERGENCE TEST")
    print(f"Endpoint: {ENDPOINT}")
    print(f"Model:    {MODEL}")
    print(f"{'='*60}")

    try:
        vector = await run_convergence_pass(
            endpoint=ENDPOINT,
            api_key="not-required",  # local server ignores auth but header must be valid
            model=MODEL,
            azure=False,
            gemini=False,
            use_lunar=False,  # deterministic order for first test
        )
        split = ConvergenceSplit(vector)
        print(f"\nVector    : {vector}")
        print(f"C-seed    : {split.c_seed}")
        print(f"B-finger  : {split.b_fingerprint}")
        print(f"Substrate : {split.substrate}")
        print(f"\nKnown C-seed (TEL_GRAMMAR_v1): {KNOWN_C_SEED}")
        print(f"Match: {split.c_seed == KNOWN_C_SEED}")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()


asyncio.run(main())
