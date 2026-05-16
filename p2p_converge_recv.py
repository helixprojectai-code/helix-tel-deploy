"""
TEL P2P Convergence Receiver — derives C-seed independently then listens.

Runs the constitutional battery against a live AI endpoint, derives the
C-seed via convergence (no pre-shared seed), then connects to the hub
and listens for encrypted messages. Text is printed; binary is saved to
--output-dir with SHA3-256 hash.

Usage:
    python p2p_converge_recv.py --node BESS

Environment:
    TEL_ENDPOINT   Azure endpoint, e.g. https://<resource>.cognitiveservices.azure.com
    TEL_MODEL      Deployment name, e.g. gpt-4o
    TEL_API_KEY    Azure API key

Or pass via --endpoint / --model / --key flags.
"""

import argparse
import asyncio
import hashlib
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
log = logging.getLogger("p2p_converge_recv")


async def run(
    hub: str,
    port: int,
    node_id: str,
    endpoint: str,
    model: str,
    api_key: str,
    output_dir: str,
    max_passes: int = 30,
):
    print(f"\n{'='*60}")
    print("TEL CONVERGENCE RECV")
    print(f"Node: {node_id}")
    print(f"Endpoint: {endpoint}  Model: {model}")
    print(f"{'='*60}\n")

    # --- Phase 1: Register with hub first so sender can route to us ---
    os.makedirs(output_dir, exist_ok=True)
    log.info(f"Connecting to hub {hub}:{port} as {node_id}")
    reader, writer = await asyncio.open_connection(hub, port, limit=4 * 1024 * 1024)
    writer.write(
        (json.dumps({"action": "register", "node_id": node_id}) + "\n").encode()
    )
    await writer.drain()
    log.info(f"Registered as {node_id}. Starting convergence battery...")

    # --- Phase 2: Convergence (messages queue in TCP buffer while we run) ---
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
        log.error(f"Failed to converge in {max_passes} passes. Aborting.")
        writer.close()
        await writer.wait_closed()
        sys.exit(1)

    split = ConvergenceSplit(detector.stable_vector)
    c_seed = split.get_mesh_seed()

    print(f"\n{'='*60}")
    print(f"C-seed: {c_seed[:16]}...  Substrate: {split.substrate}")
    print(f"Listening as {node_id}. Waiting for messages...")
    print(f"{'='*60}\n")

    cipher = TrueHDUECipher(c_seed)

    while True:
        try:
            data = await reader.readline()
            if not data:
                log.warning("Hub closed connection.")
                break

            msg = json.loads(data.decode().strip())
            if msg.get("action") != "route":
                continue

            sender = msg.get("sender", "?")
            payload = msg.get("payload", {})
            kind = payload.get("kind", "text")

            if kind == "binary":
                raw = cipher.decrypt_bytes(payload)
                fname = payload.get("filename", "received.bin")
                out_path = os.path.join(output_dir, fname)
                with open(out_path, "wb") as f:
                    f.write(raw)
                sha = hashlib.sha3_256(raw).hexdigest()
                print(f"\n[BINARY] from {sender}: {len(raw)}B → {out_path}")
                print(f"         SHA3-256: {sha}")
            else:
                plaintext = cipher.decrypt(payload)
                print(f"\n[TEXT] from {sender}: {plaintext}")

        except KeyboardInterrupt:
            break
        except json.JSONDecodeError:
            log.error("Malformed message.")
        except Exception as e:
            log.error(f"Recv error: {e}")
            break

    writer.close()
    await writer.wait_closed()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub", default="your-hub-host")
    parser.add_argument("--port", type=int, default=9738)
    parser.add_argument("--node", required=True)
    parser.add_argument(
        "--endpoint", default=os.environ.get("TEL_ENDPOINT"), required=False
    )
    parser.add_argument("--model", default=os.environ.get("TEL_MODEL"), required=False)
    parser.add_argument("--key", default=os.environ.get("TEL_API_KEY"), required=False)
    parser.add_argument("--output-dir", default="./recv_output")
    parser.add_argument("--max-passes", type=int, default=30)
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
            args.endpoint,
            args.model,
            args.key,
            args.output_dir,
            args.max_passes,
        )
    )


if __name__ == "__main__":
    main()
