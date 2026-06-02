# P2P Exchange

Two modes of peer-to-peer exchange are supported: **live convergence** (each node derives the C-seed independently at runtime) and **static seed** (for testing with a known seed).

---

## Live Convergence (Zero Pre-Shared Secret)

Both nodes independently run the constitutional battery and derive the same C-seed. No seed is transmitted.

**On the receiving node (start first):**

```bash
python3 tel_deploy/p2p_converge_recv.py \
  --hub your-hub-host --port 9738 \
  --node NODE_B \
  --endpoint $TEL_ENDPOINT --model $TEL_MODEL --key $TEL_API_KEY
```

**On the sending node (separate machine, same AI topology):**

```bash
python3 tel_deploy/p2p_converge_send.py \
  --hub your-hub-host --port 9738 \
  --node NODE_A --target NODE_B \
  --endpoint $TEL_ENDPOINT --model $TEL_MODEL --key $TEL_API_KEY \
  --message "Constitutional grammar is the shared secret."
```

Both nodes converge independently. If they share the same constitutional topology, the C-seeds match and the message decrypts correctly.

---

## Static Seed (Testing)

For testing with a known C-seed value:

```bash
# Receiver
python3 tel_deploy/p2p_recv.py \
  --hub your-hub-host --port 9738 \
  --node NODE_B \
  --seed c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac

# Sender
python3 tel_deploy/p2p_send.py \
  --hub your-hub-host --port 9738 \
  --node NODE_A --target NODE_B \
  --seed c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac \
  --message "Test message."
```

---

## Loopback Test

Run the full 5-case loopback test suite locally (no hub required):

```bash
python3 tel_deploy/p2p_loopback.py
```

Tests: text round-trip, binary payload, multi-message sequence, large payload, nonce exhaustion guard.

---

## TEL v2 CLI (Recommended)

For production nodes, `tel node` handles convergence + registry ping + session establishment automatically. See [CLI Reference](../cli.md#tel-node-tel-v2-full-node).
