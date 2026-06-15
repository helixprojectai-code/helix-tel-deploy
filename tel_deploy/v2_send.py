"""
TEL v2 Send — session-gated convergence send.

Phases:
  1. Converge against local AI endpoint → derive C-seed
  2. Ping WHC registry → announce self, discover target
  3. Open session with target (HMAC challenge-response via registry)
  4. Only if session verified → encrypt and route via hub

No message is sent without a verified session. No seed is transmitted.

Usage:
    python -m tel_deploy.v2_send --node SPIDER --target BESS --message "hello"
    python -m tel_deploy.v2_send --node SPIDER --target BESS --file /path/to/file

Environment:
    TEL_ENDPOINT     AI endpoint URL
    TEL_MODEL        Model/deployment name
    TEL_API_KEY      API key
    TEL_HUB_HOST     Hub hostname (default: tel.helixaiinnovations.ca)
    TEL_HUB_PORT     Hub port (default: 9738)
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
from tel_deploy.ping import PingClient
from tel_deploy.session import SessionInitiator
from tel_deploy.test_runner import run_convergence_pass

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("tel.v2_send")

DEFAULT_HUB = os.environ.get("TEL_HUB_HOST", "tel.helixaiinnovations.ca")
DEFAULT_PORT = int(os.environ.get("TEL_HUB_PORT", 9738))
DEFAULT_TOPOLOGY = "universal"


async def run(
    node_id: str,
    target: str,
    endpoint: str,
    model: str,
    api_key: str,
    hub: str,
    port: int,
    topology: str,
    message: str = None,
    filepath: str = None,
    max_passes: int = 30,
    azure: bool = True,
):
    print(f"\n{'='*60}")
    print("TEL v2 SEND")
    print(f"Node: {node_id}  →  Target: {target}")
    print(f"Hub:  {hub}:{port}")
    print(f"{'='*60}\n")

    # --- Phase 1: Convergence ---
    log.info("Phase 1 — Constitutional battery. Deriving C-seed...")

    async def test_fn():
        return await run_convergence_pass(
            endpoint=endpoint, api_key=api_key, model=model, azure=azure
        )

    detector = ConvergenceDetector(test_fn)
    converged = await detector.run(max_passes=max_passes)

    if not converged:
        log.error(f"Failed to converge in {max_passes} passes. Aborting.")
        sys.exit(1)

    split = ConvergenceSplit(detector.stable_vector)
    c_seed = split.get_mesh_seed()
    log.info(f"C-seed: {c_seed[:16]}...  Substrate: {split.substrate}")

    # --- Phase 2: Ping registry ---
    log.info("Phase 2 — Pinging registry. Announcing self, checking target...")

    ping_client = PingClient(node_id=node_id, topology=topology)
    response = await ping_client.ping(c_seed=c_seed)

    compatible = response.compatible_peers(topology, ping_client.grammar)
    peer_ids = [p.node_id for p in compatible]

    if target not in peer_ids:
        log.error(
            f"Target '{target}' not in registry or incompatible topology. "
            f"Live compatible peers: {peer_ids}. Aborting."
        )
        sys.exit(1)

    log.info(f"Target '{target}' found in registry. Topology aligned.")

    # --- Phase 3: Session verification ---
    log.info("Phase 3 — Opening session with target (HMAC challenge-response)...")

    initiator = SessionInitiator(node_id=node_id)
    session = await initiator.open(peer_id=target, c_seed=c_seed)

    if not session or not session.verified:
        log.error(
            f"Session with '{target}' failed — C-seed mismatch or timeout. Aborting."
        )
        sys.exit(1)

    log.info(
        f"Session VERIFIED. ID={session.session_id[:12]}  Seeds aligned. Safe to encrypt."
    )

    # --- Phase 4: Encrypt and send via hub ---
    log.info(f"Phase 4 — Connecting to hub {hub}:{port}...")

    reader, writer = await asyncio.open_connection(hub, port, limit=4 * 1024 * 1024)
    writer.write(
        (json.dumps({"action": "register", "node_id": node_id}) + "\n").encode()
    )
    await writer.drain()
    log.info(f"Registered as {node_id} on hub.")

    cipher = TrueHDUECipher(c_seed)

    if filepath:
        with open(filepath, "rb") as f:
            data = f.read()
        fname = os.path.basename(filepath)
        encrypted = cipher.encrypt_bytes(data, kind="binary")
        encrypted["filename"] = fname
        encrypted["session_id"] = session.session_id
        frame = (
            json.dumps({"action": "send", "target": target, "payload": encrypted})
            + "\n"
        )
        writer.write(frame.encode())
        await writer.drain()
        log.info(f"Sent binary {len(data)}B ({fname}) → {target}")

    elif message:
        encrypted = cipher.encrypt(message)
        encrypted["session_id"] = session.session_id
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
    print(f"SENT  →  {target}")
    print(f"C-seed:     {c_seed[:16]}...")
    print(f"Session:    {session.session_id[:16]}...")
    print(f"Substrate:  {split.substrate}")
    print("No seed transmitted. Session verified before encryption.")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="TEL v2 — session-gated send")
    parser.add_argument("--node", required=True, help="This node's ID")
    parser.add_argument("--target", required=True, help="Target node ID")
    parser.add_argument("--hub", default=DEFAULT_HUB)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    parser.add_argument("--endpoint", default=os.environ.get("TEL_ENDPOINT"))
    parser.add_argument("--model", default=os.environ.get("TEL_MODEL"))
    parser.add_argument("--key", default=os.environ.get("TEL_API_KEY"))
    parser.add_argument("--max-passes", type=int, default=30)
    parser.add_argument("--azure", action="store_true", default=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", "-m")
    group.add_argument("--file", "-f", dest="filepath")
    args = parser.parse_args()

    if not args.endpoint or not args.model or not args.key:
        parser.error("TEL_ENDPOINT, TEL_MODEL, TEL_API_KEY required.")

    asyncio.run(
        run(
            node_id=args.node,
            target=args.target,
            endpoint=args.endpoint,
            model=args.model,
            api_key=args.key,
            hub=args.hub,
            port=args.port,
            topology=args.topology,
            message=args.message,
            filepath=args.filepath,
            max_passes=args.max_passes,
            azure=args.azure,
        )
    )


if __name__ == "__main__":
    main()
