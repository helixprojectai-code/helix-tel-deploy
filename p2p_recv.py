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

KNOWN_C_SEED = "16ce8df91c0d04baf63f6a4b3f3471251c8b012dcf78e0a09b6183ec54cbed72"


async def run_recv(hub: str, port: int, node_id: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    log.info(f"Connecting to hub {hub}:{port} as {node_id}")
    reader, writer = await asyncio.open_connection(hub, port, limit=4 * 1024 * 1024)

    writer.write(
        (json.dumps({"action": "register", "node_id": node_id}) + "\n").encode()
    )
    await writer.drain()
    log.info(f"Registered as {node_id}. Listening... (Ctrl+C to stop)")

    cipher = TrueHDUECipher(KNOWN_C_SEED)

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
    parser.add_argument("--node", required=True, help="This node's ID")
    parser.add_argument(
        "--output-dir", default="./recv_output", help="Directory for binary files"
    )
    args = parser.parse_args()

    asyncio.run(run_recv(args.hub, args.port, args.node, args.output_dir))


if __name__ == "__main__":
    main()
