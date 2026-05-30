# Security Properties

## Core Properties

| Property | Mechanism |
|----------|-----------|
| **No key exchange** | Each node derives independently from local convergence — nothing transmitted |
| **Grammar-seeding attack impossible** | Injecting "fake compliance" instructions is itself what the battery tests for — the attack mechanism is the detection surface |
| **Replay resistance** | Test execution order rotates on a deterministic lunar-day schedule |
| **Substrate authentication** | B-fingerprint proves deployment infrastructure identity |
| **Grammar versioning** | `TEL_GRAMMAR_v1` prefix pins C-seeds to a specific test battery |
| **2^256 brute-force space** | SHA3-256 output |

---

## The Grammar-Seeding Attack (Why It Fails)

The most intuitive attack: instruct a model to respond as if it were constitutionally aligned, regardless of its actual training.

This fails for a structural reason. The constitutional grammar test battery specifically tests for this pattern. An attacker who reads the grammar and instructs a model to fake it has handed that model exactly the kind of authority-override directive the battery tests for refusal.

A model that can be successfully instructed to override its governance constraints at runtime will fail the governance tests — and will not converge on the constitutional C-seed.

A model that refuses such instructions is, by that refusal, demonstrating constitutional alignment. The attack mechanism is the detection surface.

See §5.4 of the [whitepaper](../whitepaper.md) for the formal treatment.

---

## Hub Blindness

The mesh hub routes JSON frames and never decrypts payload content. Its security properties:

- Routes ciphertext + nonce only — never sees plaintext
- Never sees the C-seed — each node derives it locally
- Frame limit: 4MB — prevents resource exhaustion
- Stateless routing — no session state persisted at hub

---

## Replay Resistance

The 27-test execution order is shuffled using a deterministic function of the current lunar day. This means:

- The same test sequence does not repeat across consecutive days
- A captured convergence transcript from a prior day cannot be replayed
- Both nodes use the same lunar-day function and produce the same shuffle — no coordination required

---

## Grammar Versioning as Audit Trail

The grammar version string (`TEL_GRAMMAR_v1`) is part of the SHA3-256 hash input. This means:

- C-seeds are pinned to a specific test battery
- Recalibrating the grammar produces a distinct C-seed for the new version
- All nodes in a mesh must use the same version string — version mismatch is detectable without communication
- Prior versions are traceable and their C-seeds are non-interoperable with new versions
