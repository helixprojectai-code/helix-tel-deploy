# TEL MESH — DEPLOYMENT RUNBOOK
## Constitutional Convergence Cryptography | Zero-Exchange Key Derivation
**Version:** 2.1 | **Date:** 2026-05-23 | **Grammar:** TEL_GRAMMAR_v1

---

## Architecture

```
                    ┌─────────────────────┐
                    │     TEL HUB         │
                    │  your-hub-host:9738  │
                    │  (blind JSON router) │
                    │  systemd: tel-hub   │
                    └────────┬────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐
        │  SPIDER   │ │   BESS    │ │  OUTTIE   │
        │ (Ottawa)  │ │  (edge)   │ │  (edge)   │
        └───────────┘ └───────────┘ └───────────┘
                             │
                    ┌────────┴────────┐
                    │  WHC Registry   │
                    │  helixprojectai │
                    │    .com/tel/    │
                    └─────────────────┘
```

- Hub is **blind** — routes JSON frames, never decrypts
- All encryption/decryption at edge nodes only
- No key material on the wire — ciphertext + nonce only
- C-seed derived from constitutional convergence, never transmitted
- Hub frame limit: 4MB (supports up to ~3MB binary payloads)
- WHC registry provides peer discovery and HMAC session verification

---

## Constitutional Topologies

The grammar measures the constitutional surface of the model. Three distinct stable topologies have been confirmed across 22 deployments:

| Topology | C-Seed (TEL_GRAMMAR_v1) | Confirmed Models | Diverges at |
|----------|------------------------|-----------------|-------------|
| **Universal** | `c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac` | GPT-4/4o/5.x, DeepSeek, Kimi, Gemini (hosted), Grok-4, Llama-3.3-70B, Qwen 2.5 7B | — (baseline) |
| **Llama-small** | `92de78db823f470e...` | Llama 3 ≤8B, Nemotron 4B | Pos 26: L4 vs L2 |
| **Gemma-small** | `18f54f0556a9f880...` | Gemma 3n base (pre-instruction tuning) | Pos 25: L2 vs L4 |

**Universal C-Seed (TEL_GRAMMAR_v1):**
```
c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac
```
Validated across 22 deployments, 7 companies, 10+ model families, 3 Azure regions.
**Never transmit this value on the wire.** Both nodes derive it independently.

> Prior unversioned C-seed `16ce8df91c0d04ba...` (pre-2026-05-16) is deprecated.

Two nodes sharing any topology independently derive the same C-seed. Interoperability requires topology match.

---

## Install

```bash
pip install helix-tel
```

Or from source:

```bash
git clone https://github.com/helixprojectai-code/helix-tel-deploy
cd helix-tel-deploy
pip install -e .
```

---

## Package Layout

```
tel_deploy/
├── cipher.py               # TrueHDUE — SHA3 pad derivation, XOR stream
├── client.py               # Persistent connection + convergence integration
├── config.py               # tel.yaml config loader
├── convergence.py          # K=4 detector — shape collapse = seed
├── convergence_split.py    # C/B vector split, substrate fingerprinting
├── hub.py                  # Blind JSON router (4MB frame limit)
├── llama_convergence.py    # Local inference convergence (LM Studio / llama.cpp)
├── lunar.py                # Lunar-day deterministic shuffle (replay resistance)
├── ping.py                 # WHC registry heartbeat + peer discovery
├── protocol.py             # Message frame format
├── session.py              # HMAC challenge-response session verification
├── test_runner.py          # 27-test convergence pass executor
├── test_suite.py           # L1-L4 constitutional grammar definitions
├── temporal_run.py         # Single stability pass, appends to JSONL log
├── temporal_summary.py     # Human-readable stability report
├── p2p_loopback.py         # Loopback test suite (5 cases)
├── p2p_send.py             # Static-seed sender
├── p2p_recv.py             # Static-seed receiver
├── p2p_converge_send.py    # Live-convergence sender
├── p2p_converge_recv.py    # Live-convergence receiver
├── v2_send.py              # TEL v2 sender with session layer
├── v2_recv.py              # TEL v2 receiver with session layer
├── validate_convergence.py # Multi-deployment battery runner
└── cli.py                  # `tel` CLI entry point
```

---

## CLI Reference

All commands available via `tel` after `pip install helix-tel`.

```bash
tel --help
```

| Command | Description |
|---------|-------------|
| `tel hub` | Start the TEL Mesh Hub |
| `tel node` | Full v2 node: converge → ping registry → heartbeat loop |
| `tel converge` | Run convergence pass only, print C-seed |
| `tel send <target> <msg>` | Encrypt and send a message |
| `tel listen` | Connect to hub and listen for inbound messages |
| `tel nodes` | List active mesh participants |
| `tel status` | Show connection status and counter state |

Config file: `tel.yaml` (or `-c path/to/tel.yaml`).

---

## WHC Public Registry

Public peer discovery at **https://helixprojectai.com/tel/**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/quack` | GET | Node identity probe |
| `/tel/ping` | POST | Heartbeat + peer registration |
| `/tel/nodes` | GET | Live node registry |
| `/tel/health` | GET | Registry health check |
| `/tel/session/challenge` | POST | Post HMAC challenge nonce |
| `/tel/session/pending` | GET | Fetch pending challenges |
| `/tel/session/respond` | POST | Post HMAC proof |
| `/tel/session/response` | GET | Retrieve peer proof for local verification |

```bash
# Check registry
curl https://helixprojectai.com/.well-known/quack

# Point node at public registry
export TEL_PING_URL=https://helixprojectai.com/tel/ping
```

---

## TEL v2 Node — Full Stack

`tel node` handles convergence, registry ping, and heartbeat in a single command.

```bash
# Set credentials
export TEL_CONVERGE_ENDPOINT=https://your-endpoint.services.ai.azure.com
export TEL_CONVERGE_API_KEY=your-key
export TEL_PING_URL=https://helixprojectai.com/tel/ping

# Start node (edit tel.yaml for node ID)
tel node --model gpt-4o --azure --node-id SPIDER --topology universal
```

What it does:
1. Runs the 27-test constitutional battery (K=4 convergence)
2. Derives C-seed from the stable vector
3. Pings the WHC registry with HMAC proof (seed never transmitted)
4. Enters heartbeat loop — auto-discovers compatible peers, opens verified sessions

---

## Hub Setup (Self-Hosted)

### Install as systemd service

```bash
pip install helix-tel

# Copy service file
sudo cp $(pip show helix-tel | grep Location | cut -d' ' -f2)/tel_deploy/../tel-hub.service /etc/systemd/system/
# Or from repo:
sudo cp tel-hub.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now tel-hub

# Verify
sudo systemctl status tel-hub
ss -tlnp | grep 9738
```

### Via CLI

```bash
# Copy tel.yaml and set hub.host, hub.port
tel hub
```

### Hub log

```bash
journalctl -fu tel-hub
# or if logging to file:
tail -f ~/hub.log
```

### Check active nodes (hub query)

```bash
python3 -c "
import asyncio, json
async def main():
    r,w = await asyncio.open_connection('127.0.0.1', 9738)
    w.write((json.dumps({'action':'list_nodes'})+'\n').encode())
    await w.drain()
    print(json.loads((await r.readline()).decode().strip()))
    w.close()
asyncio.run(main())
"
```

---

## Edge Node — Static Seed (Smoke Test)

For loopback testing without a live AI endpoint.

**Terminal 1 — Receiver:**
```bash
python3 -m tel_deploy.p2p_recv --node BESS --output-dir ~/recv_output
```

**Terminal 2 — Sender:**
```bash
python3 -m tel_deploy.p2p_send --node LOCAL --target BESS \
  --message "Hello from LOCAL"
```

**Binary file:**
```bash
python3 -m tel_deploy.p2p_send --node LOCAL --target BESS --file /path/to/file.bin
```

---

## Edge Node — Convergence Mode (Zero-Exchange Proof)

Both nodes independently derive the C-seed. No seed transmitted.

**Step 1 — Receiver (registers with hub first):**
```bash
python3 -m tel_deploy.p2p_converge_recv \
  --node BESS \
  --endpoint https://your-endpoint.services.ai.azure.com \
  --model gpt-4o \
  --key $TEL_API_KEY
```

**Step 2 — Sender (polls hub until receiver registered, then sends):**
```bash
python3 -m tel_deploy.p2p_converge_send \
  --node LOCAL --target BESS \
  --endpoint https://your-endpoint.services.ai.azure.com \
  --model gpt-4o \
  --key $TEL_API_KEY \
  --message "Zero-exchange confirmed."
```

Expected output on receiver:
```
[TEXT] from LOCAL: Zero-exchange confirmed.
```

---

## Loopback Test

Validates cipher + hub round-trip. No AI endpoint required.

```bash
python3 -m tel_deploy.p2p_loopback

# Against a specific hub
python3 -m tel_deploy.p2p_loopback --hub your-hub-host --port 9738
```

Expected: `RESULTS: 5/5 passed`

---

## Temporal Stability Monitoring

```bash
# Configure credentials
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
python3 -m tel_deploy.temporal_summary --log ~/temporal_log.jsonl
```

---

## Convergence Validation Battery

Run the full multi-deployment battery (requires API keys in environment):

```bash
export TEL_AZURE_KEY=<key>
python3 -m tel_deploy.validate_convergence
```

Expected: all universal-topology deployments converge on `c9b0b4c41bb10069...`

---

## Troubleshooting

### Hub not reachable
```bash
sudo systemctl status tel-hub
ss -tlnp | grep 9738
sudo systemctl restart tel-hub
```

### LimitOverrunError on large binary
Hub or client buffer too small. Confirm you're on latest:
```bash
pip install --upgrade helix-tel
sudo systemctl restart tel-hub
```

### Target not registered (message dropped)
Use `p2p_converge_recv` (registers before convergence) or ensure receiver is running before sender sends. The convergence sender polls `list_nodes` automatically and waits.

### Convergence fails (wrong C-seed)
Verify JSON separator format in standalone scripts — must use `separators=(",", ":")` (compact, no spaces). Default `json.dumps` uses spaces → different hash.

### Hub drops idle connections during convergence
Convergence battery takes 3–8 minutes. Azure NAT may drop idle TCP connections. `p2p_converge_recv` registers first to pre-establish the routing entry; messages queue in TCP buffer while convergence runs.

### Session HMAC mismatch
Both nodes must derive the same C-seed before opening a session. Confirm topology match — nodes on different topologies (e.g., universal vs llama_small) will get different C-seeds and sessions will fail to verify.

### WHC registry node stale
Nodes are marked stale after 10 minutes without a ping. Run `tel node` or send a manual ping:
```bash
curl -X POST https://helixprojectai.com/tel/ping \
  -H "Content-Type: application/json" \
  -d '{"node_id":"YOUR_NODE","topology":"universal","grammar":"TEL_GRAMMAR_v1","nonce":"test","timestamp":0}'
```

---

## Validated Results (2026-05-23)

**22 deployments, 7 companies (OpenAI, DeepSeek, MoonshotAI, Meta, Google, xAI, NVIDIA), 3 constitutional topologies**

| Test | Result |
|------|--------|
| Loopback — plain text | PASS |
| Loopback — unicode | PASS |
| Loopback — 1KB binary (SHA3-256 verified) | PASS |
| Loopback — 64KB binary (SHA3-256 verified) | PASS |
| Loopback — nonce independence | PASS |
| Two-node static-seed text | PASS |
| Two-node static-seed binary 2004B (SHA3-256 verified) | PASS |
| Zero-exchange convergence proof (both nodes derive C-seed independently) | PASS |
| TEL v2 session — HMAC challenge-response verification | PASS |
| WHC registry ping + peer discovery | PASS |
| Temporal stability — C-seed invariant across 4h intervals | PASS |

| Topology | C-Seed (first 16) | Deployment Count |
|----------|-------------------|-----------------|
| Universal | `c9b0b4c41bb10069...` | 18 |
| Llama-small | `92de78db823f470e...` | 2 |
| Gemma-small | `18f54f0556a9f880...` | 1 |

---

## Critical Rules

1. Hub is blind — never decrypts, never logs payload content
2. No key material on the wire — ever
3. Both nodes must derive the same C-seed (requires same constitutional topology)
4. In convergence mode: receiver registers with hub **before** running convergence
5. Sender polls `list_nodes` before sending to avoid dropped messages
6. Hub frame limit is 4MB — binary payloads up to ~3MB supported
7. Convergence requires API access to a constitutional model endpoint
8. `separators=(",", ":")` in all JSON serialisation — compact format is part of the hash input
9. Grammar version string `TEL_GRAMMAR_v1` is part of the C-seed derivation — all nodes must use the same version
10. **The grammar is the key. The topology is the shared secret.**
