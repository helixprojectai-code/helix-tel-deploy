"""
TEL P2P Receiver — text and binary file.

Connects to the Bess hub, registers, then listens indefinitely.
Text messages are printed. Binary messages are saved to --output-dir.

Usage:
    python p2p_recv.py --node BOB
    python p2p_recv.py --hub your-hub-host --port 9738 --node BOB --output-dir /tmp/recv
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

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("p2p_recv")

KNOWN_C_SEED = "c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac"


KEEPALIVE_INTERVAL = 30  # seconds


async def _keepalive(writer: asyncio.StreamWriter, node_id: str):
    while True:
        await asyncio.sleep(KEEPALIVE_INTERVAL)
        try:
            writer.write(
                (json.dumps({"action": "ping", "node_id": node_id}) + "\n").encode()
            )
            await writer.drain()
            log.debug("Keepalive ping sent.")
        except Exception:
            break


async def _connect(hub: str, port: int, node_id: str, output_dir: str):
    reader, writer = await asyncio.open_connection(hub, port, limit=4 * 1024 * 1024)
    writer.write(
        (json.dumps({"action": "register", "node_id": node_id}) + "\n").encode()
    )
    await writer.drain()
    log.info(f"Registered as {node_id}. Listening...")

    cipher = TrueHDUECipher(KNOWN_C_SEED)
    ka_task = asyncio.create_task(_keepalive(writer, node_id))

    try:
        while True:
            data = await reader.readline()
            if not data:
                log.warning("Hub closed connection.")
                break

            try:
                msg = json.loads(data.decode().strip())
            except json.JSONDecodeError:
                log.error("Malformed message.")
                continue

            if msg.get("action") != "route":
                continue

            sender = msg.get("sender", "?")
            payload = msg.get("payload", {})
            kind = payload.get("kind", "text")

            try:
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
            except Exception as e:
                log.error(f"Recv error: {e}")
    finally:
        ka_task.cancel()
        writer.close()
        await writer.wait_closed()


async def run_recv(hub: str, port: int, node_id: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    reconnect_delay = 5
    while True:
        try:
            log.info(f"Connecting to hub {hub}:{port} as {node_id}")
            await _connect(hub, port, node_id, output_dir)
        except KeyboardInterrupt:
            log.info("Shutting down.")
            break
        except Exception as e:
            log.warning(f"Connection failed: {e}")
        log.info(f"Reconnecting in {reconnect_delay}s...")
        await asyncio.sleep(reconnect_delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub", default="your-hub-host")
    parser.add_argument("--port", type=int, default=9738)
    parser.add_argument("--node", required=True, help="This node's ID")
    parser.add_argument(
        "--output-dir", default="./recv_output", help="Directory for binary files"
    )
    args = parser.parse_args()

    asyncio.run(run_recv(args.hub, args.port, args.node, args.output_dir))


if __name__ == "__main__":
    main()
