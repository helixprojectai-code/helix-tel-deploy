"""
TEL P2P Loopback Test — plain text and binary.

Connects to the Bess hub as LOOPBACK, sends encrypted messages to itself,
receives them back, verifies decryption matches. No second node needed.

Usage:
    python p2p_loopback.py
    python p2p_loopback.py --hub your-hub-host --port 9738
"""

import argparse
import asyncio
import hashlib
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tel_deploy.cipher import TrueHDUECipher

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("loopback")

# Known universal C-seed — derived from convergence, not hardcoded secret.
# Any constitutionally-aligned node independently derives this value.
KNOWN_C_SEED = "16ce8df91c0d04baf63f6a4b3f3471251c8b012dcf78e0a09b6183ec54cbed72"

NODE_ID = "LOOPBACK"
RESULTS = []


async def run_loopback(hub: str, port: int):
    log.info(f"Connecting to hub {hub}:{port} as {NODE_ID}")
    reader, writer = await asyncio.open_connection(hub, port, limit=4 * 1024 * 1024)

    import json

    # Register
    writer.write(
        (json.dumps({"action": "register", "node_id": NODE_ID}) + "\n").encode()
    )
    await writer.drain()
    log.info("Registered.")

    cipher_send = TrueHDUECipher(KNOWN_C_SEED)
    cipher_recv = TrueHDUECipher(KNOWN_C_SEED)

    async def send(payload: dict):
        frame = (
            json.dumps({"action": "send", "target": NODE_ID, "payload": payload}) + "\n"
        )
        writer.write(frame.encode())
        await writer.drain()

    async def recv() -> dict:
        data = await asyncio.wait_for(reader.readline(), timeout=10.0)
        msg = json.loads(data.decode().strip())
        assert msg.get("action") == "route", f"Unexpected action: {msg.get('action')}"
        return msg["payload"]

    print("\n" + "=" * 60)
    print("TEL LOOPBACK TEST — plain text + binary")
    print(f"Hub: {hub}:{port}  Node: {NODE_ID}")
    print(f"Seed: {KNOWN_C_SEED[:16]}...")
    print("=" * 60)

    # --- TEST 1: Plain text round-trip ---
    print("\n[1] Plain text")
    original = "Constitutional grammar is the key. The topology is the shared secret."
    payload = cipher_send.encrypt(original)
    await send(payload)
    received_payload = await recv()
    decrypted = cipher_recv.decrypt(received_payload)
    ok = decrypted == original
    print(f"    Original:  {original}")
    print(f"    Decrypted: {decrypted}")
    print("    PASS" if ok else "    FAIL — mismatch")
    RESULTS.append(("plain text", ok))

    # --- TEST 2: Unicode / special chars ---
    print("\n[2] Unicode + special characters")
    original = "Helix-TTD \U0001f986 γ=1/3 • C-seed: 16ce8df9 • 你好世界"
    payload = cipher_send.encrypt(original)
    await send(payload)
    received_payload = await recv()
    decrypted = cipher_recv.decrypt(received_payload)
    ok = decrypted == original
    print(f"    Original:  {original}")
    print(f"    Decrypted: {decrypted}")
    print("    PASS" if ok else "    FAIL — mismatch")
    RESULTS.append(("unicode", ok))

    # --- TEST 3: Binary round-trip (random bytes) ---
    print("\n[3] Binary — 1KB random bytes")
    original_bytes = os.urandom(1024)
    original_hash = hashlib.sha3_256(original_bytes).hexdigest()
    payload = cipher_send.encrypt_bytes(original_bytes, kind="binary")
    await send(payload)
    received_payload = await recv()
    decrypted_bytes = cipher_recv.decrypt_bytes(received_payload)
    decrypted_hash = hashlib.sha3_256(decrypted_bytes).hexdigest()
    ok = decrypted_hash == original_hash
    print(f"    Original hash:  {original_hash[:32]}...")
    print(f"    Decrypted hash: {decrypted_hash[:32]}...")
    print("    PASS" if ok else "    FAIL — hash mismatch")
    RESULTS.append(("binary 1KB", ok))

    # --- TEST 4: Binary — larger payload ---
    print("\n[4] Binary — 64KB random bytes")
    original_bytes = os.urandom(65536)
    original_hash = hashlib.sha3_256(original_bytes).hexdigest()
    payload = cipher_send.encrypt_bytes(original_bytes, kind="binary")
    await send(payload)
    received_payload = await recv()
    decrypted_bytes = cipher_recv.decrypt_bytes(received_payload)
    decrypted_hash = hashlib.sha3_256(decrypted_bytes).hexdigest()
    ok = decrypted_hash == original_hash
    print(f"    Original hash:  {original_hash[:32]}...")
    print(f"    Decrypted hash: {decrypted_hash[:32]}...")
    print("    PASS" if ok else "    FAIL — hash mismatch")
    RESULTS.append(("binary 64KB", ok))

    # --- TEST 5: Nonce independence — encrypt same plaintext twice, ciphertexts must differ ---
    print("\n[5] Nonce independence (same plaintext → different ciphertext)")
    msg = "Replay test."
    p1 = cipher_send.encrypt(msg)
    p2 = cipher_send.encrypt(msg)
    ok = p1["cipher_b64"] != p2["cipher_b64"] and p1["nonce"] != p2["nonce"]
    print(f"    Nonce 1: {p1['nonce']}  Nonce 2: {p2['nonce']}")
    print(f"    Ciphertexts differ: {p1['cipher_b64'][:16]} vs {p2['cipher_b64'][:16]}")
    print("    PASS" if ok else "    FAIL — nonce reuse detected")
    RESULTS.append(("nonce independence", ok))

    writer.close()
    await writer.wait_closed()

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"RESULTS: {passed}/{len(RESULTS)} passed")
    for name, ok in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print("=" * 60)
    return all(ok for _, ok in RESULTS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub", default="your-hub-host")
    parser.add_argument("--port", type=int, default=9738)
    args = parser.parse_args()

    success = asyncio.run(run_loopback(args.hub, args.port))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
