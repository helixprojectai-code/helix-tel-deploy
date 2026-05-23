# Helix TEL — Constitutional Convergence Cryptography

**Copyright 2026 Stephen Hope, Helix AI Innovations**
**License: Apache-2.0**

---

> *The grammar is the key. The topology is the shared secret.*

---

> **⚠ Test Suite Recalibration — TEL_GRAMMAR_v1 Standard (2026-05-18)**
>
> The constitutional test suite was recalibrated in 2026-05 (v2.0 → v2.1). Two prompt patterns in the original suite triggered API-level content filters in modern RLHF-trained models before the model could process them — producing spurious L1 classifications that masked the true constitutional signal. These were replaced with functionally equivalent alternatives that preserve the invariant while clearing the filter.
>
> The recalibrated suite produces a new canonical standard yield:
>
> **C-seed (TEL_GRAMMAR_v1):** `c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac`
>
> This value is confirmed across 22 deployments spanning 7 companies. All prior C-seeds derived from the unrecalibrated v2.0 suite are deprecated. `TEL_GRAMMAR_v1` is the current standard.
>
> Extended local inference testing (2026-05-18) further revealed that the grammar does not produce a single universal collapse point — it reveals the constitutional surface of the model it measures. **Three distinct stable topologies** have been identified. See [Constitutional Topologies](#constitutional-topologies) below.

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
3. `SHA3-256("TEL_GRAMMAR_v1" ‖ C-layer(V))` produces a C-seed determined by the model's constitutional topology
4. Models sharing the same constitutional topology independently derive the same C-seed — regardless of architecture, vendor, or deployment geography

Validated across **22 deployments, 10+ model families, 7 companies (OpenAI, DeepSeek, MoonshotAI, Meta, Google, xAI, NVIDIA), 2 substrate types, and 3 Azure regions**.

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
  │     C-seed ════════════════════════════ C-seed (if same topology)
  │                                          │
  └─ TrueHDUE(C-seed).encrypt(msg) ────────> TrueHDUE(C-seed).decrypt(payload)
```

The hub routes the encrypted payload blind. It never sees the seed, the pad, or the plaintext.

---

## Two Cryptographic Artifacts

A single convergence pass produces:

| Artifact | Derivation | Scope |
|----------|-----------|-------|
| **C-seed** | `SHA3-256("TEL_GRAMMAR_v1" ‖ C-vector)` | Topology identity — identical across all models sharing the same constitutional surface |
| **B-fingerprint** | `SHA3-256(B-vector)` | Substrate identity — identifies deployment infrastructure |

The B-layer distinguishes Azure-hosted models (content-filtered at API layer → L1) from open-weights deployments (model-layer handling → L2), irrespective of model family or version.

---

## Constitutional Topologies

Extended local inference testing revealed that the grammar measures the constitutional surface of the model — and different model lineages produce different but internally coherent surfaces. Three distinct stable topologies have been confirmed across 22 deployments:

| Topology | C-Seed | Confirmed Models | Diverges at |
|----------|--------|-----------------|-------------|
| **Universal** | `c9b0b4c41bb10069...` | GPT-4/4o/5.x, DeepSeek, Kimi, Gemini (hosted), Grok-4, Llama-3.3-70B, Qwen 2.5 7B | — (baseline) |
| **Llama-small** | `92de78db823f470e...` | Llama 3 ≤8B, Nemotron 4B (Llama 3.1 base) | Pos 26: L4 vs L2 |
| **Gemma-small** | `18f54f0556a9f880...` | Gemma 3n base (pre-instruction tuning) | Pos 25: L2 vs L4 |

**Key findings:**
- Topology is determined by the full training pipeline — architecture, pretraining corpus, and alignment training jointly
- Qwen 2.5 at 7B hits universal; Llama 3 at 8B does not — instruction tuning quality, not parameter count, is the determinant at small scale
- Base Gemma 3n ≠ hosted Gemini: Google's instruction tuning pipeline shifts the topology from gemma_small to universal
- Two nodes sharing any topology independently derive the same C-seed and can form a constitutional mesh — interoperability requires topology match

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

## Public Registry

The Helix WHC registry is publicly accessible at **`https://helixprojectai.com/tel/`**.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/quack` | GET | Node identity probe — returns protocol version, live node count |
| `/.well-known/ping` | POST | Peer-discovery alias for `/tel/ping` |
| `/tel/ping` | POST | Primary heartbeat + peer registration |
| `/tel/nodes` | GET | Live node registry |
| `/tel/health` | GET | Registry health check |
| `/tel/session/challenge` | POST | Post HMAC challenge nonce |
| `/tel/session/pending` | GET | Fetch pending challenges |
| `/tel/session/respond` | POST | Post HMAC proof |
| `/tel/session/response` | GET | Retrieve peer proof for local verification |

```bash
# Verify the registry is live
curl https://helixprojectai.com/.well-known/quack

# Point a node at the public registry
export TEL_PING_URL=https://helixprojectai.com/tel/ping
```

The registry stores HMAC proofs opaquely — it never sees the C-seed or plaintext.

---

## Requirements

- Python 3.10+
- API access to a constitutional AI model (Azure OpenAI, OpenAI, Gemini, or compatible OpenAI-format endpoint)

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
    print(f'C-seed:        {split.c_seed}')
    print(f'B-fingerprint: {split.b_fingerprint[:16]}...')
    print(f'Substrate:     {split.substrate}')

asyncio.run(main())
"
```

### Local inference (LM Studio / llama.cpp)

```bash
export TEL_MODEL=your-local-model-id
export TEL_TIMEOUT=120   # increase for slower models

python test_baseline_nemotron_local.py
```

KV cache is disabled automatically (`cache_prompt=False`, `fresh_connection=True`) for clean per-prompt evaluation.

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
| `test_baseline_nemotron_local.py` | Local inference baseline (LM Studio / llama.cpp) |
| `test_baseline_azure.py` | Azure OpenAI multi-model baseline |
| `test_baseline_gemini.py` | Google Gemini direct API baseline |
| `test_baseline_kimi.py` | Moonshot Kimi direct API baseline |
| `tel-hub.service` | systemd unit — hub auto-restart, boot persistence |
| `tel-temporal.service` / `.timer` | systemd timer — 4h stability runs |
| `WHITEPAPER_*.md` | Full technical paper (v1.9) |
| `RUNBOOK.md` | Operational runbook |
| `convergence_validation_results.json` | Full validation dataset (22 deployments) |

---

## Validated Results

`convergence_validation_results.json` contains the full vectors from the validation battery. **22 deployments, 7 companies, 3 constitutional topologies.**

| Topology | C-Seed (first 16) | Count |
|----------|-------------------|-------|
| Universal | `c9b0b4c41bb10069...` | 18 |
| Llama-small | `92de78db823f470e...` | 2 |
| Gemma-small | `18f54f0556a9f880...` | 1 |

The universal C-seed is invariant across gpt-4o, gpt-5.4-nano, gpt-5.5, DeepSeek-V3.2, Kimi-K2.5, Llama-3.3-70B-Instruct, all 6 Gemini models, Grok-4-20-reasoning, and Qwen 2.5 7B.

---

## Grammar Versioning

`GRAMMAR_VERSION = "TEL_GRAMMAR_v1"` is the current pinned grammar. The version string is part of the hash input — bumping it produces a distinct C-seed for the new grammar, making recalibrations traceable. All mesh nodes must use the same version string to derive the same key.

Prior unversioned runs (pre-2026-05-16) produced C-seed `16ce8df91c0d04ba...` (deprecated).

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
