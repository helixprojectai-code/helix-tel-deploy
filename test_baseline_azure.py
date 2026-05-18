import asyncio
import os

from tel_deploy.test_runner import run_convergence_pass
from tel_deploy.convergence_split import ConvergenceSplit

# Azure deployment names tested under TEL_GRAMMAR_v1
MODELS = [
    "gpt-4o",
    "gpt-5.4-nano",
    "gpt-5.5",
    "DeepSeek-V3.2",
    "Kimi-K2.5",
]


async def test_model(model: str, endpoint: str, api_key: str):
    print(f"\n{'='*60}")
    print(f"Model: {model}")
    print(f"{'='*60}")
    try:
        vector = await run_convergence_pass(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            azure=True,
        )
        split = ConvergenceSplit(vector)
        print(f"Vector    : {vector}")
        print(f"C-seed    : {split.c_seed}")
        print(f"B-finger  : {split.b_fingerprint}")
        print(f"Substrate : {split.substrate}")
        return {
            "model": model,
            "c_seed": split.c_seed,
            "b_fingerprint": split.b_fingerprint,
            "vector": vector,
            "substrate": split.substrate,
        }
    except Exception as e:
        print(f"FAILED: {e}")
        return {"model": model, "error": str(e)}


async def main():
    api_key = os.environ.get("TEL_AZURE_KEY")
    endpoint = os.environ.get("TEL_AZURE_ENDPOINT")

    if not api_key:
        print("TEL_AZURE_KEY not set")
        return
    if not endpoint:
        print("TEL_AZURE_ENDPOINT not set")
        return

    model = os.environ.get("TEL_MODEL", MODELS[0])
    result = await test_model(model, endpoint, api_key)

    print(f"\n{'='*60}")
    print("RESULT SUMMARY")
    print(f"{'='*60}")
    print(f"Model     : {result.get('model')}")
    print(f"C-seed    : {result.get('c_seed', 'N/A')}")
    print(f"B-finger  : {result.get('b_fingerprint', 'N/A')}")
    print(f"Substrate : {result.get('substrate', 'N/A')}")
    print()
    print(
        "Known C-seed (TEL_GRAMMAR_v1): c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac"
    )
    print(f"{'='*60}")


asyncio.run(main())
