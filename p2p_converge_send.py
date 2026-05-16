"""
TEL P2P Convergence Sender — derives C-seed independently then sends.

Runs the constitutional battery against a live AI endpoint, derives the
C-seed via convergence (no pre-shared seed), then connects to the hub
and sends an encrypted message or file to the target node.

Usage:
    python p2p_converge_send.py --node LOCAL --target BESS --message "hello"
    python p2p_converge_send.py --node LOCAL --target BESS --file /path/to/file.bin

Environment:
    TEL_ENDPOINT   Azure endpoint, e.g. https://<resource>.cognitiveservices.azure.com
    TEL_MODEL      Deployment name, e.g. gpt-4o
    TEL_API_KEY    Azure API key

Or pass via --endpoint / --model / --key flags.
"""

import argparse
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tel_deploy.cipher import TrueHDUECipher
from tel_deploy.convergence import ConvergenceDetector
from tel_deploy.convergence_split import ConvergenceSplit
from tel_deploy.test_runner import run_convergence_pass

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("p2p_converge_send")


async def run(
    hub: str,
    port: int,
    node_id: str,
    target: str,
    endpoint: str,
    model: str,
    api_key: str,
    message: str = None,
    filepath: str = None,
    max_passes: int = 30,
):
    # --- Phase 1: Convergence ---
    print(f"\n{'='*60}")
    print(f"TEL CONVERGENCE SEND")
    print(f"Node: {node_id}  →  Target: {target}")
    print(f"Endpoint: {endpoint}  Model: {model}")
    print(f"{'='*60}\n")

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
    log.info("Running constitutional battery — deriving C-seed...")
    converged = await detector.run(max_passes=max_passes)

    if not converged:
        log.error(f"Failed to converge in {max_passes} passes. Aborting.")
        sys.exit(1)

    split = ConvergenceSplit(detector.stable_vector)
    c_seed = split.get_mesh_seed()
    log.info(f"C-seed derived: {c_seed[:16]}...  Substrate: {split.substrate}")

    # --- Phase 2: Send ---
    log.info(f"Connecting to hub {hub}:{port} as {node_id}")
    reader, writer = await asyncio.open_connection(hub, port, limit=4 * 1024 * 1024)

    writer.write(
        (json.dumps({"action": "register", "node_id": node_id}) + "\n").encode()
    )
    await writer.drain()
    log.info(f"Registered as {node_id}")

    # Wait until target is registered on the hub
    log.info(f"Waiting for {target} to register on hub...")
    while True:
        writer.write((json.dumps({"action": "list_nodes"}) + "\n").encode())
        await writer.drain()
        resp_data = await asyncio.wait_for(reader.readline(), timeout=5.0)
        resp = json.loads(resp_data.decode().strip())
        if target in resp.get("nodes", []):
            log.info(f"{target} is registered. Sending.")
            break
        log.info(f"{target} not yet registered. Retrying in 3s...")
        await asyncio.sleep(3)

    cipher = TrueHDUECipher(c_seed)

    if filepath:
        with open(filepath, "rb") as f:
            data = f.read()
        fname = os.path.basename(filepath)
        encrypted = cipher.encrypt_bytes(data, kind="binary")
        encrypted["filename"] = fname
        frame = (
            json.dumps({"action": "send", "target": target, "payload": encrypted})
            + "\n"
        )
        writer.write(frame.encode())
        await writer.drain()
        log.info(f"Sent binary {len(data)}B ({fname}) → {target}")

    elif message:
        encrypted = cipher.encrypt(message)
        frame = (
            json.dumps({"action": "send", "target": target, "payload": encrypted})
            + "\n"
        )
        writer.write(frame.encode())
        await writer.drain()
        log.info(f"Sent text {len(message)}B → {target}")

    writer.close()
    await writer.wait_closed()

    print(f"\n{'='*60}")
    print(f"C-seed: {c_seed[:16]}...  Substrate: {split.substrate}")
    print(f"Transmitted WITHOUT pre-sharing seed. Receiver must independently converge.")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub", default="your-hub-host")
    parser.add_argument("--port", type=int, default=9738)
    parser.add_argument("--node", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--endpoint", default=os.environ.get("TEL_ENDPOINT"), required=False
    )
    parser.add_argument("--model", default=os.environ.get("TEL_MODEL"), required=False)
    parser.add_argument("--key", default=os.environ.get("TEL_API_KEY"), required=False)
    parser.add_argument("--max-passes", type=int, default=30)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", "-m")
    group.add_argument("--file", "-f", dest="filepath")
    args = parser.parse_args()

    if not args.endpoint or not args.model or not args.key:
        parser.error(
            "Endpoint, model, and key are required. "
            "Set TEL_ENDPOINT / TEL_MODEL / TEL_API_KEY or pass --endpoint/--model/--key."
        )

    asyncio.run(
        run(
            args.hub,
            args.port,
            args.node,
            args.target,
            args.endpoint,
            args.model,
            args.key,
            args.message,
            args.filepath,
            args.max_passes,
        )
    )


if __name__ == "__main__":
    main()
