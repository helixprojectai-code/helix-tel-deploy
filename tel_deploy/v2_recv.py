"""
TEL v2 Receive — session-aware convergence receiver.

Phases:
  1. Register with hub (so sender can route to us immediately)
  2. Converge against local AI endpoint → derive C-seed
  3. Ping WHC registry → announce self
  4. Start heartbeat loop — auto-responds to session challenges
  5. Listen on hub for encrypted messages → decrypt and output

Messages without a verified session_id are still decrypted if the
C-seed matches — session_id is logged for audit, not used as a gate
on the receive side (sender already verified before sending).

Usage:
    python -m tel_deploy.v2_recv --node BESS
    python -m tel_deploy.v2_recv --node BESS --output-dir ./recv

Environment:
    TEL_ENDPOINT     AI endpoint URL
    TEL_MODEL        Model/deployment name
    TEL_API_KEY      API key
    TEL_HUB_HOST     Hub hostname (default: tel.helixaiinnovations.ca)
    TEL_HUB_PORT     Hub port (default: 9738)
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
from tel_deploy.ping import PingClient
from tel_deploy.test_runner import run_convergence_pass

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("tel.v2_recv")

DEFAULT_HUB = os.environ.get("TEL_HUB_HOST", "tel.helixaiinnovations.ca")
DEFAULT_PORT = int(os.environ.get("TEL_HUB_PORT", 9738))
DEFAULT_TOPOLOGY = "universal"


async def run(
    node_id: str,
    endpoint: str,
    model: str,
    api_key: str,
    hub: str,
    port: int,
    topology: str,
    output_dir: str,
    max_passes: int = 30,
    heartbeat_interval: int = 30,
    azure: bool = True,
):
    print(f"\n{'='*60}")
    print("TEL v2 RECV")
    print(f"Node: {node_id}  Hub: {hub}:{port}")
    print(f"{'='*60}\n")

    os.makedirs(output_dir, exist_ok=True)

    # --- Phase 1: Register with hub immediately ---
    # Register before convergence so sender can route to us while we converge.
    # Messages queue in the TCP buffer while we run the battery.
    log.info(f"Phase 1 — Registering with hub {hub}:{port} as {node_id}...")
    reader, writer = await asyncio.open_connection(hub, port, limit=4 * 1024 * 1024)
    writer.write(
        (json.dumps({"action": "register", "node_id": node_id}) + "\n").encode()
    )
    await writer.drain()
    log.info("Registered. Starting convergence battery...")

    # --- Phase 2: Convergence ---
    async def test_fn():
        return await run_convergence_pass(
            endpoint=endpoint, api_key=api_key, model=model, azure=azure
        )

    detector = ConvergenceDetector(test_fn)
    converged = await detector.run(max_passes=max_passes)

    if not converged:
        log.error(f"Failed to converge in {max_passes} passes. Aborting.")
        writer.close()
        await writer.wait_closed()
        sys.exit(1)

    split = ConvergenceSplit(detector.stable_vector)
    c_seed = split.get_mesh_seed()
    log.info(f"C-seed: {c_seed[:16]}...  Substrate: {split.substrate}")

    # --- Phase 3: Ping registry ---
    log.info("Phase 3 — Pinging registry. Announcing readiness...")
    ping_client = PingClient(node_id=node_id, topology=topology)
    response = await ping_client.ping(c_seed=c_seed)
    compatible = response.compatible_peers(topology, ping_client.grammar)
    log.info(f"Registry ok. Compatible peers online: {[p.node_id for p in compatible]}")

    cipher = TrueHDUECipher(c_seed)

    # --- Phase 4: Heartbeat (background) ---
    # Runs in background — auto-responds to session challenges from senders.

    async def on_peer_change(peers):
        log.info(f"Peer set changed: {[p.node_id for p in peers]}")

    heartbeat_task = asyncio.create_task(
        ping_client.start_heartbeat(
            c_seed=c_seed,
            interval=heartbeat_interval,
            on_peer_change=on_peer_change,
            respond_to_challenges=True,
        )
    )

    print(f"\n{'='*60}")
    print(f"C-seed: {c_seed[:16]}...  Substrate: {split.substrate}")
    print(f"Listening as {node_id}. Heartbeat every {heartbeat_interval}s.")
    print("Session challenges answered automatically.")
    print(f"{'='*60}\n")

    # --- Phase 5: Listen on hub ---
    try:
        while True:
            data = await reader.readline()
            if not data:
                log.warning("Hub closed connection.")
                break

            try:
                msg = json.loads(data.decode().strip())
            except json.JSONDecodeError:
                log.error("Malformed message from hub.")
                continue

            if msg.get("action") != "route":
                continue

            sender = msg.get("sender", "?")
            payload = msg.get("payload", {})
            kind = payload.get("kind", "text")
            session_id = payload.get("session_id", "unverified")

            try:
                if kind == "binary":
                    raw = cipher.decrypt_bytes(payload)
                    fname = payload.get("filename", "received.bin")
                    out_path = os.path.join(output_dir, fname)
                    with open(out_path, "wb") as f:
                        f.write(raw)
                    sha = hashlib.sha3_256(raw).hexdigest()
                    print(f"\n[BINARY] from {sender}  session={session_id[:12]}")
                    print(f"  {len(raw)}B → {out_path}")
                    print(f"  SHA3-256: {sha}")
                else:
                    plaintext = cipher.decrypt(payload)
                    print(f"\n[TEXT] from {sender}  session={session_id[:12]}")
                    print(f"  {plaintext}")

            except Exception as e:
                log.error(f"Decryption failed from {sender}: {e}. Session mismatch?")

    except KeyboardInterrupt:
        pass
    finally:
        heartbeat_task.cancel()
        writer.close()
        await writer.wait_closed()


def main():
    parser = argparse.ArgumentParser(description="TEL v2 — session-aware receiver")
    parser.add_argument("--node", required=True, help="This node's ID")
    parser.add_argument("--hub", default=DEFAULT_HUB)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    parser.add_argument("--endpoint", default=os.environ.get("TEL_ENDPOINT"))
    parser.add_argument("--model", default=os.environ.get("TEL_MODEL"))
    parser.add_argument("--key", default=os.environ.get("TEL_API_KEY"))
    parser.add_argument("--output-dir", default="./recv_output")
    parser.add_argument("--max-passes", type=int, default=30)
    parser.add_argument("--heartbeat", type=int, default=30)
    parser.add_argument("--azure", action="store_true", default=True)
    args = parser.parse_args()

    if not args.endpoint or not args.model or not args.key:
        parser.error("TEL_ENDPOINT, TEL_MODEL, TEL_API_KEY required.")

    asyncio.run(
        run(
            node_id=args.node,
            endpoint=args.endpoint,
            model=args.model,
            api_key=args.key,
            hub=args.hub,
            port=args.port,
            topology=args.topology,
            output_dir=args.output_dir,
            max_passes=args.max_passes,
            heartbeat_interval=args.heartbeat,
            azure=args.azure,
        )
    )


if __name__ == "__main__":
    main()
