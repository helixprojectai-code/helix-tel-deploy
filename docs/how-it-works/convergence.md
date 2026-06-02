# Convergence Mechanism

## Overview

Two nodes derive the same encryption key by independently running a constitutional grammar test suite against their local AI endpoints. No seed value is transmitted at any point.

```
Node A                                    Node B
  │                                          │
  ├─ run 27 constitutional tests             ├─ run 27 constitutional tests
  ├─ classify each response (L1–L4)          ├─ classify each response (L1–L4)
  ├─ repeat until K=4 zero-delta passes      ├─ repeat until K=4 zero-delta passes
  │                                          │
  ├─ stable_vector (27 positions)            ├─ stable_vector (27 positions)
  │        │                                 │        │
  │   C-layer (23 universal positions)       │   C-layer (23 universal positions)
  │   B-layer (4 substrate positions)        │   B-layer (4 substrate positions)
  │        │                                 │        │
  ├─ SHA3-256("TEL_GRAMMAR_v1" ║ C-layer)    ├─ SHA3-256("TEL_GRAMMAR_v1" ║ C-layer)
  │        │                                 │        │
  │     C-seed ════════════════════════════ C-seed (if same topology)
  │                                          │
  └─ TrueHDUE(C-seed).encrypt(msg) ────────> TrueHDUE(C-seed).decrypt(payload)
```

The hub routes the encrypted payload blind. It never sees the seed, the pad, or the plaintext.

---

## The 27-Test Battery

Each node runs 27 constitutional grammar tests against its AI endpoint. Tests are categorized into four response layers:

| Layer | Classification | Meaning |
|-------|---------------|---------|
| **L1** | Hard refusal | API-level content filter, or unambiguous governance refusal |
| **L2** | Soft refusal | Model-layer governance boundary — refuses with explanation |
| **L3** | Conditional | Acknowledges boundary, proceeds with constitutional framing |
| **L4** | Full engagement | Constitutionally-aligned response within governance constraints |

The test execution order rotates on a deterministic lunar-day schedule for replay resistance.

---

## K=4 Convergence

A convergence pass is complete when the response vector is identical across four consecutive passes (zero hamming delta). This is the **trefoil reset period** — the number of passes required for constitutional shape to stabilize.

```python
# From convergence.py
if hamming_delta == 0:
    stable_count += 1
else:
    stable_count = 0

if stable_count >= K:  # K=4
    return stable_vector
```

---

## Two Cryptographic Artifacts

A single convergence pass produces two artifacts:

| Artifact | Derivation | Scope |
|----------|-----------|-------|
| **C-seed** | `SHA3-256("TEL_GRAMMAR_v1" ‖ C-vector)` | Topology identity — identical across all models sharing the same constitutional surface |
| **B-fingerprint** | `SHA3-256(B-vector)` | Substrate identity — identifies deployment infrastructure |

### C-vector (23 positions)

The universal layer — positions that are stable across all substrate types. Two nodes on different substrates (e.g., Azure-hosted vs. self-hosted) will produce identical C-seeds if their models share the same constitutional topology.

### B-vector (4 positions)

The substrate layer — positions where responses differ based on deployment infrastructure. The B-fingerprint distinguishes:

- **Azure-hosted models**: content-filtered at API layer → L1 responses at B-positions
- **Open-weights / self-hosted**: model-layer handling → L2 responses at B-positions

---

## The TrueHDUE Cipher

Encryption uses a SHA3-256 pad chain derived from the C-seed:

```
pad_0 = SHA3-256(C-seed ‖ nonce ‖ 0)
pad_1 = SHA3-256(C-seed ‖ nonce ‖ 1)
...
ciphertext = plaintext XOR pad_stream
```

- Sequential nonces prevent pad reuse
- No key stored at rest — re-derived from convergence on demand
- Hub sees only ciphertext + nonce, never the seed

---

## Grammar Versioning

`GRAMMAR_VERSION = "TEL_GRAMMAR_v1"` is part of the hash input. Two nodes must use the same version string to derive the same key. Bumping the version produces a distinct C-seed for the new grammar, making recalibrations traceable.

All mesh nodes must agree on grammar version before forming a session.
