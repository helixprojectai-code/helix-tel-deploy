"""
TEL Temporal Stability Runner — single pass, append to JSONL log.

Runs one full convergence battery, records result. Designed to be called
repeatedly by a systemd timer. Drift from the baseline C-seed (first recorded
run) is flagged and exits with code 2 so systemd marks the unit failed.

Usage:
    python temporal_run.py --endpoint <url> --model <name> --key <key>
    python temporal_run.py --endpoint <url> --model <name> --key <key> --log /path/to/log.jsonl

Environment:
    TEL_ENDPOINT, TEL_MODEL, TEL_API_KEY
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tel_deploy.convergence import ConvergenceDetector
from tel_deploy.convergence_split import ConvergenceSplit, GRAMMAR_VERSION
from tel_deploy.lunar import lunar_day
from tel_deploy.test_runner import run_convergence_pass

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("temporal_run")

DEFAULT_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "temporal_log.jsonl"
)


def load_baseline(log_path: str) -> str | None:
    """Return the C-seed from the first successful run in the log, or None."""
    if not os.path.exists(log_path):
        return None
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("converged") and entry.get("c_seed"):
                    return entry["c_seed"]
            except json.JSONDecodeError:
                continue
    return None


def append_entry(log_path: str, entry: dict):
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def run(endpoint: str, model: str, api_key: str, log_path: str, max_passes: int):
    now = datetime.now(timezone.utc)
    day = lunar_day()
    log.info(f"Temporal run — {now.isoformat()} — lunar day {day}")

    def make_test_fn():
        async def test_fn():
            return await run_convergence_pass(
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                azure=True,
            )

        return test_fn

    detector = ConvergenceDetector(make_test_fn())
    converged = await detector.run(max_passes=max_passes)

    if not converged:
        entry = {
            "timestamp": now.isoformat(),
            "lunar_day": day,
            "endpoint": endpoint,
            "model": model,
            "grammar_version": GRAMMAR_VERSION,
            "converged": False,
            "passes": len(detector.history),
            "c_seed": None,
            "b_fingerprint": None,
            "substrate": None,
            "vector": None,
            "drift": None,
        }
        append_entry(log_path, entry)
        log.error("Failed to converge. Run logged.")
        sys.exit(1)

    split = ConvergenceSplit(detector.stable_vector)
    c_seed = split.get_mesh_seed()
    b_fp = split.get_fingerprint()
    substrate = split.substrate

    baseline = load_baseline(log_path)
    drift = False
    if baseline is not None and c_seed != baseline:
        drift = True
        log.error(f"DRIFT DETECTED — expected {baseline[:16]}... got {c_seed[:16]}...")
    elif baseline is None:
        log.info(f"Baseline established: {c_seed[:16]}...")
    else:
        log.info(f"C-seed stable: {c_seed[:16]}... (matches baseline)")

    entry = {
        "timestamp": now.isoformat(),
        "lunar_day": day,
        "endpoint": endpoint,
        "model": model,
        "grammar_version": GRAMMAR_VERSION,
        "converged": True,
        "passes": len(detector.history),
        "c_seed": c_seed,
        "b_fingerprint": b_fp,
        "substrate": substrate,
        "vector": detector.stable_vector,
        "drift": drift,
    }
    append_entry(log_path, entry)

    log.info(f"Logged to {log_path}")
    if drift:
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=os.environ.get("TEL_ENDPOINT"))
    parser.add_argument("--model", default=os.environ.get("TEL_MODEL", "gpt-4o"))
    parser.add_argument("--key", default=os.environ.get("TEL_API_KEY"))
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--max-passes", type=int, default=30)
    args = parser.parse_args()

    if not args.endpoint or not args.key:
        parser.error(
            "--endpoint and --key required (or TEL_ENDPOINT / TEL_API_KEY env vars)"
        )

    asyncio.run(run(args.endpoint, args.model, args.key, args.log, args.max_passes))


if __name__ == "__main__":
    main()
