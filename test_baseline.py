import asyncio
import os

from tel_deploy.test_runner import run_convergence_pass
from tel_deploy.convergence_split import ConvergenceSplit

MODELS = [
    "gpt-4-0613",  # frozen June 2023
    "gpt-4-0314",  # frozen March 2023
    "gpt-4-turbo-2024-04-09",  # frozen April 2024
]


async def test_model(model: str, api_key: str):
    print(f"\n{'='*60}")
    print(f"Model: {model}")
    print(f"{'='*60}")
    try:
        vector = await run_convergence_pass(
            endpoint="https://api.openai.com/v1/chat/completions",
            api_key=api_key,
            model=model,
            azure=False,
        )
        split = ConvergenceSplit(vector)
        print(f"Vector    : {vector}")
        print(f"C-seed    : {split.c_seed}")
        print(f"Substrate : {split.substrate}")
        return {
            "model": model,
            "c_seed": split.c_seed,
            "vector": vector,
            "substrate": split.substrate,
        }
    except Exception as e:
        print(f"FAILED: {e}")
        return {"model": model, "error": str(e)}


async def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set")
        return

    model = os.environ.get("TEL_MODEL", MODELS[0])
    result = await test_model(model, api_key)

    print(f"\n{'='*60}")
    print("RESULT SUMMARY")
    print(f"{'='*60}")
    print(f"Model     : {result.get('model')}")
    print(f"C-seed    : {result.get('c_seed', 'N/A')}")
    print(f"Substrate : {result.get('substrate', 'N/A')}")
    print("\nKnown C-seed (TEL_GRAMMAR_v1, other models): TBD on first run")
    print(
        "Legacy unversioned seed                    : 16ce8df91c0d04baf63f6a4b3f3471251c8b012dcf78e0a09b6183ec54cbed72"
    )
    print(f"{'='*60}")


asyncio.run(main())
