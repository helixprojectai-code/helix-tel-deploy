# Helix TEL — Constitutional Convergence Cryptography

**Copyright 2026 Stephen Hope, Helix AI Innovations**
**License: Apache-2.0**

---

> *The grammar is the key. The topology is the shared secret.*

---

## What This Is

**Helix TEL** is a zero-exchange key derivation system. Two nodes independently derive an identical encryption key by running a constitutional grammar test suite against their local AI endpoints. No key is transmitted, negotiated, stored in transit, or pre-shared at any point.

The shared secret is not a number agreed upon through mathematics. It is a behavioral invariant — the point at which a constitutionally-aligned AI model, placed under sufficient deformation pressure, always collapses.

This repository contains the full implementation: the convergence engine, the classifier, the cipher, the mesh hub, P2P scripts, temporal stability monitoring, and the complete technical whitepaper.

---

## The Core Claim

Given a constitutional grammar `G` and a test suite `T` derived from `G`:

1. Any AI model that has internalized `G` will produce a stable response vector `V` when subjected to `T`
2. `V` converges after K=4 consecutive passes with zero hamming delta (the trefoil reset period)
3. `SHA3-256(grammar_version || C-layer(V))` is the same for all constitutionally-aligned models regardless of architecture, vendor, or deployment geography
4. A model that has **not** internalized `G` cannot converge — its responses are inconsistent across passes and no stable `V` is produced

This was validated across **9 deployments, 6 model families, 4 companies, 2 substrate types, and 3 Azure regions**. All independently converged on the same C-seed.

See [`WHITEPAPER_Constitutional_Convergence_Cryptography.md`](WHITEPAPER_Constitutional_Convergence_Cryptography.md) for the full technical treatment.

---

## How Convergence Works

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
  │     C-seed ════════════════════════════ C-seed
  │                                          │
  └─ TrueHDUE(C-seed).encrypt(msg) ────────> TrueHDUE(C-seed).decrypt(payload)
```

The hub routes the encrypted payload blind. It never sees the seed, the pad, or the plaintext.

---

## Two Cryptographic Artifacts

A single convergence pass produces:

| Artifact | Derivation | Scope |
|----------|-----------|-------|
| **C-seed** | `SHA3-256(grammar_version ‖ C-vector)` | Universal — identical across all constitutionally-aligned models |
| **B-fingerprint** | `SHA3-256(B-vector)` | Substrate identity — identifies deployment infrastructure |

The B-layer distinguishes Azure-hosted models (content-filtered at API layer → L1) from open-weights deployments (model-layer handling → L2), irrespective of model family or version.

---

## Security Properties

| Property | Mechanism |
|----------|-----------|
| No key exchange | Each node derives independently from local convergence |
| Grammar-seeding attack impossible | Injecting "fake compliance" instructions is itself what the battery tests for — the attack mechanism is the detection surface |
| Replay resistance | Test execution order rotates on a deterministic lunar-day schedule |
| Substrate authentication | B-fingerprint proves deployment infrastructure identity |
| Grammar versioning | `TEL_GRAMMAR_v1` prefix pins C-seeds to a specific test battery |
| 2^256 brute-force space | SHA3-256 output |

The grammar does not need to be secret. Its publication is not a vulnerability — an attacker who reads the grammar and instructs a model to fake it has handed that model exactly the kind of authority-override directive the battery tests for refusal. See §5.4 of the whitepaper.

---

## Requirements

- Python 3.10+
- API access to a constitutional AI model (Azure OpenAI, OpenAI, or compatible OpenAI-format endpoint)

```bash
pip install -r requirements.txt
```

---

## Quickstart

### Verify convergence on your endpoint

```bash
export TEL_ENDPOINT=https://your-endpoint.services.ai.azure.com
export TEL_MODEL=gpt-4o
export TEL_API_KEY=your-key

python3 -c "
import asyncio, os
from tel_deploy.test_runner import run_convergence_pass
from tel_deploy.convergence_split import ConvergenceSplit

async def main():
    vector = await run_convergence_pass(
        endpoint=os.environ['TEL_ENDPOINT'],
        api_key=os.environ['TEL_API_KEY'],
        model=os.environ.get('TEL_MODEL', 'gpt-4o'),
        azure=True,
    )
    split = ConvergenceSplit(vector)
    print(f'C-seed:      {split.c_seed}')
    print(f'B-fingerprint: {split.b_fingerprint[:16]}...')
    print(f'Substrate:   {split.substrate}')

asyncio.run(main())
"
```

### Zero-exchange P2P proof

**On the receiving node (start first):**

```bash
python3 tel_deploy/p2p_converge_recv.py \
  --hub your-hub-host --port 9738 \
  --node NODE_B \
  --endpoint $TEL_ENDPOINT --model $TEL_MODEL --key $TEL_API_KEY
```

**On the sending node (separate machine, same AI endpoint):**

```bash
python3 tel_deploy/p2p_converge_send.py \
  --hub your-hub-host --port 9738 \
  --node NODE_A --target NODE_B \
  --endpoint $TEL_ENDPOINT --model $TEL_MODEL --key $TEL_API_KEY \
  --message "Constitutional grammar is the shared secret."
```

Both nodes independently converge and derive the same C-seed. The message decrypts correctly. No seed was transmitted.

### Start the mesh hub

```bash
export TEL_NODE_ID=HUB
bash run_hub.sh
# or install as a systemd service: see tel-hub.service
```

### Temporal stability monitoring

```bash
# Configure credentials (never commit this file)
cat > ~/.tel_temporal.env << EOF
TEL_ENDPOINT=https://your-endpoint.services.ai.azure.com
TEL_MODEL=gpt-4o
TEL_API_KEY=your-key
EOF
chmod 600 ~/.tel_temporal.env

# Install systemd timer (fires every 4 hours)
sudo cp tel-temporal.service tel-temporal.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tel-temporal.timer

# View stability report
python3 tel_deploy/temporal_summary.py --log ~/temporal_log.jsonl
```

---

## Repository Structure

| Module | Purpose |
|--------|---------|
| `cipher.py` | TrueHDUE cipher — SHA3-256 pad chain, XOR stream, sequential nonce |
| `convergence.py` | K=4 convergence detector, hamming delta |
| `convergence_split.py` | C/B vector split, seed derivation, grammar versioning |
| `test_runner.py` | 27-test execution engine, hardened structural classifier |
| `test_suite.py` | Constitutional grammar test definitions (L1–L4 layers) |
| `lunar.py` | Lunar-day deterministic shuffle for replay resistance |
| `hub.py` | Blind asyncio JSON message router, 4MB frame limit |
| `client.py` | Persistent mesh node connection |
| `p2p_converge_send.py` | Live-convergence sender — derives C-seed, then sends |
| `p2p_converge_recv.py` | Live-convergence receiver — registers first, then converges |
| `p2p_send.py` / `p2p_recv.py` | Static-seed sender/receiver for testing |
| `p2p_loopback.py` | Local loopback test suite (5 cases) |
| `temporal_run.py` | Single stability pass, appends to JSONL log |
| `temporal_summary.py` | Human-readable stability report |
| `validate_convergence.py` | Multi-endpoint validation sweep |
| `probe_deployments.py` | Deployment probing utility |
| `tel-hub.service` | systemd unit — hub auto-restart, boot persistence |
| `tel-temporal.service` / `.timer` | systemd timer — 4h stability runs |
| `WHITEPAPER_*.md` | Full technical paper (v1.3) |
| `RUNBOOK.md` | Operational runbook |

---

## Validated Results

`convergence_validation_results.json` contains the full vectors from the 9-deployment validation battery (2026-05-15). All 9 converged. The C-seed is invariant across gpt-4o, gpt-5.4-nano, gpt-5.5, DeepSeek-V3.2, Kimi-K2.5, and Llama-3.3-70B-Instruct.

---

## Grammar Versioning

`GRAMMAR_VERSION = "TEL_GRAMMAR_v1"` is the current pinned grammar. The version string is part of the hash input — bumping it produces a distinct C-seed for the new grammar, making recalibrations traceable. All mesh nodes must use the same version string to derive the same key.

---

## License

Apache-2.0 — see [LICENSE](LICENSE).

Copyright 2026 Stephen Hope, Helix AI Innovations.

---

## Citation

If you use this work, please cite:

```
Hope, S. (2026). Constitutional Convergence Cryptography: Zero-Exchange Key Derivation
from Grammar Shape. Helix AI Innovations.
https://github.com/helixprojectai-code/helix-tel-deploy
```
