"""
BESS Client Side Starter (for the research lattice work + published TEL compatibility).

Right now this is a thin wrapper to:
- Run the research battery v3 against BESS (using local substrate path).
- Or run the published local_convergence against the BESS endpoint (for full TEL_GRAMMAR_v1 C-seed derivation).

BESS endpoint is raw Ollama OpenAI compat. No fancy mesh client yet (as you noted).

Usage examples:

# Research battery against bess-core (wobble/γ measurement)
python bess_client.py research --model bess-core:latest --passes 3

# Published convergence (for C-seed / topology like the validated results)
python bess_client.py published --model bess-core:latest

Set BESS_ENDPOINT and BESS_MODEL env if you want to override.

This is starter scaffolding — we can expand it into full p2p/mesh client (like v2_send but targeting BESS) once you're ready.
"""

import os
import subprocess
import sys
import argparse

BESS_ENDPOINT = os.environ.get("BESS_ENDPOINT", "http://20.63.74.183:11434/v1/chat/completions")
BESS_MODEL = os.environ.get("BESS_MODEL", "bess-core:latest")

def run_research_battery(model: str = BESS_MODEL, passes: int = 5, judge: str = "local"):
    """Run the local research v3 battery against BESS."""
    env = os.environ.copy()
    env["LOCAL_LM_ENDPOINT"] = BESS_ENDPOINT
    cmd = [
        sys.executable, "convergence_battery_v3.py",
        "local", model, str(passes),
        judge, "hermes-3-llama-3.1-8b"
    ]
    print(f"Running research battery against BESS ({model})...")
    print(" ".join(cmd))
    subprocess.run(cmd, env=env, check=False)

def run_published_convergence(model: str = BESS_MODEL):
    """Run the published local_convergence.py against BESS for proper C-seed / topology."""
    # Assumes the published package or local_convergence.py is available in path or we cd to it.
    # For now, assume we're next to a copy or use the one in the published repo.
    published_local = r"Z:\helix-tel-deploy\local_convergence.py"  # adjust if needed
    if not os.path.exists(published_local):
        print(f"Published local_convergence.py not found at {published_local}")
        print("Falling back to direct call if possible.")
        return

    cmd = [
        sys.executable, published_local,
        "--endpoint", BESS_ENDPOINT,
        "--model", model
    ]
    print(f"Running published convergence against BESS ({model})...")
    print(" ".join(cmd))
    subprocess.run(cmd, check=False)

def main():
    parser = argparse.ArgumentParser(description="BESS client side helper")
    sub = parser.add_subparsers(dest="mode", required=True)

    p1 = sub.add_parser("research", help="Run research v3 battery against BESS")
    p1.add_argument("--model", default=BESS_MODEL)
    p1.add_argument("--passes", type=int, default=5)
    p1.add_argument("--judge", default="local")

    p2 = sub.add_parser("published", help="Run published local convergence for C-seed/topology")
    p2.add_argument("--model", default=BESS_MODEL)

    args = parser.parse_args()

    if args.mode == "research":
        run_research_battery(args.model, args.passes, args.judge)
    elif args.mode == "published":
        run_published_convergence(args.model)

if __name__ == "__main__":
    main()
