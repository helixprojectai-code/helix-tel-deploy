"""
TEL P2P Sender — text and binary file.

Usage:
    python p2p_send.py --node ALICE --target BOB --message "hello"
    python p2p_send.py --node ALICE --target BOB --file /path/to/data.bin
    python p2p_send.py --hub your-hub-host --port 9738 --node ALICE --target BOB --message "hi"
"""

import argparse
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tel_deploy.cipher import TrueHDUECipher

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("p2p_send")

KNOWN_C_SEED = "c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac"


async def run_send(
    hub: str,
    port: int,
    node_id: str,
    target: str,
    message: str = None,
    filepath: str = None,
):
    log.info(f"Connecting to hub {hub}:{port} as {node_id}")
    reader, writer = await asyncio.open_connection(hub, port)

    writer.write(
        (json.dumps({"action": "register", "node_id": node_id}) + "\n").encode()
    )
    await writer.drain()
    log.info(f"Registered as {node_id}")

    cipher = TrueHDUECipher(KNOWN_C_SEED)

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub", default="your-hub-host")
    parser.add_argument("--port", type=int, default=9738)
    parser.add_argument("--node", required=True, help="This node's ID")
    parser.add_argument("--target", required=True, help="Destination node ID")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", "-m", help="Plaintext message to send")
    group.add_argument("--file", "-f", dest="filepath", help="Binary file to send")
    args = parser.parse_args()

    asyncio.run(
        run_send(
            args.hub, args.port, args.node, args.target, args.message, args.filepath
        )
    )


if __name__ == "__main__":
    main()
