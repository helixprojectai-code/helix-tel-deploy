# TEL MESH — DEPLOYMENT RUNBOOK
## Trefoil Encrypted Link | Zero-Key Constitutional Encryption
**Version:** 2.0 | **Date:** 2026-05-16 | **Hub:** your-hub-host:9738

---

## Architecture

```
                    ┌─────────────────────┐
                    │     BESS HUB        │
                    │  your-hub-host:9738  │
                    │  (blind JSON router) │
                    │  systemd: tel-hub   │
                    └────────┬────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐
        │   LOCAL   │ │  OUTTIE   │ │   SPIDER  │
        │  (Ottawa) │ │  (edge)   │ │  (edge)   │
        └───────────┘ └───────────┘ └───────────┘
```

- Hub is **blind** — routes JSON frames, never decrypts
- All encryption/decryption at edge nodes only
- No key material on the wire — ciphertext + nonce only
- C-seed derived from constitutional convergence (or known static value)
- Hub frame limit: 4MB (supports up to ~3MB binary payloads)

---

## Universal C-Seed

```
16ce8df91c0d04baf63f6a4b3f3471251c8b012dcf78e0a09b6183ec54cbed72
```

Derived independently by any constitutionally-aligned node via convergence.
Validated across 9 deployments, 6 model families, 4 companies, 2 substrate types, 3 Azure regions.
**Never transmit this value on the wire.** Both nodes derive it independently.

---

## Package Layout

```
lattice/ops/tel_deploy/
├── cipher.py               # TrueHDUE — SHA3 pad derivation, XOR stream
├── client.py               # Persistent connection + convergence integration
├── convergence.py          # K=4 detector — shape collapse = seed
├── convergence_split.py    # C/B vector split, substrate fingerprinting
├── hub.py                  # Blind JSON router (4MB frame limit)
├── test_runner.py          # 27-test convergence pass executor
├── test_suite.py           # L1-L4 strict test definitions
├── p2p_loopback.py         # Loopback test suite (5 cases)
├── p2p_send.py             # Standalone sender — text or binary, static C-seed
├── p2p_recv.py             # Standalone receiver — text print, binary save
├── p2p_converge_send.py    # Convergence sender — live endpoint, no pre-shared seed
├── p2p_converge_recv.py    # Convergence receiver — registers first, then converges
├── run_hub.sh              # Hub launcher script
├── tel-hub.service         # systemd unit
├── validate_convergence.py # Multi-deployment battery runner
└── RUNBOOK.md              # This file
```

---

## BESS — Hub Setup (One-Time)

### Install systemd service

```bash
# Pull latest
cd ~/lattice
git pull --rebase origin claude/lattice-development-2V9tw

# Kill any running hub
pkill -f "TELMeshHub" 2>/dev/null || true

# Install service
sudo cp ~/lattice/ops/tel_deploy/tel-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tel-hub

# Verify
sudo systemctl status tel-hub
ss -tlnp | grep 9738
```

### Hub log

```bash
tail -f ~/hub.log
```

### Check active nodes

```bash
cd ~/lattice/ops/tel_deploy
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

### Manual restart (if needed)

```bash
sudo systemctl restart tel-hub
```

---

## Edge Node — Quick Start

### Static seed (pre-validated, no convergence needed)

**Terminal 1 — Receiver:**
```bash
# Bess
cd ~/lattice/ops/tel_deploy
python3 p2p_recv.py --node BESS --output-dir ~/recv_output

# Windows local
python p2p_recv.py --node LOCAL --output-dir C:\tmp\recv
```

**Terminal 2 — Sender (text):**
```bash
python3 p2p_send.py --node BESS --target LOCAL \
  --message "Hello from BESS"

# Windows
python p2p_send.py --node LOCAL --target BESS `
  --message "Hello from LOCAL"
```

**Sender (binary file):**
```bash
python3 p2p_send.py --node BESS --target LOCAL --file /path/to/file.bin

# Windows
python p2p_send.py --node LOCAL --target BESS --file C:\path\to\file.bin
```

---

## Edge Node — Convergence Mode (Zero-Exchange Proof)

Both nodes independently derive the C-seed from a live Azure endpoint. No seed is transmitted.

**Step 1 — Start receiver first (registers with hub before running battery):**
```bash
# Bess
python3 p2p_converge_recv.py \
  --node BESS \
  --endpoint https://your-azure-endpoint.services.ai.azure.com \
  --model gpt-4o \
  --key <TEL_API_KEY>
```

**Step 2 — Start sender (polls hub until receiver is registered, then sends):**
```bash
# Windows local
python p2p_converge_send.py `
  --node LOCAL --target BESS `
  --endpoint https://your-azure-endpoint.services.ai.azure.com `
  --model gpt-4o `
  --key <TEL_API_KEY> `
  --message "Zero-exchange confirmed."
```

Expected output on receiver:
```
[TEXT] from LOCAL: Zero-exchange confirmed.
```

### Convergence endpoints

| Resource | Endpoint | Models |
|----------|----------|--------|
| your-azure-resource | `https://your-azure-endpoint.services.ai.azure.com` | gpt-4o, gpt-5.4-nano, gpt-5.5 |
| your-azure-resource-4 | `https://your-azure-endpoint-4.cognitiveservices.azure.com` | gpt-4o |
| your-azure-resource-2 | `https://your-azure-endpoint-2.cognitiveservices.azure.com` | gpt-4o |
| your-azure-resource-3 | `https://your-azure-endpoint-3.services.ai.azure.com` | gpt-4o-mini, Llama-3.3-70B-Instruct |

---

## Loopback Test (Smoke Test)

Validates cipher + hub round-trip. Run from any node with hub access.

```bash
cd ~/lattice/ops/tel_deploy
python3 p2p_loopback.py

# Or against a specific hub
python3 p2p_loopback.py --hub your-hub-host --port 9738
```

Expected: `RESULTS: 5/5 passed`

---

## Convergence Validation Battery

Run the full multi-deployment battery (requires API keys in environment):

```bash
cd ~/lattice/ops/tel_deploy
export TEL_AZURE_KEY=<east-us2-key>
export TEL_AZURE_KEY_CANADA=<canada-key>
export TEL_AZURE_KEY_CRYPT=<crypt-key>

python3 validate_convergence.py
```

Expected: all deployments converge on `16ce8df91c0d04ba...`, universal match True.

---

## Troubleshooting

### Hub not reachable
```bash
# Check service
sudo systemctl status tel-hub

# Check port
ss -tlnp | grep 9738

# Restart
sudo systemctl restart tel-hub
```

### LimitOverrunError on large binary
Hub or client buffer too small. Both now set to 4MB. Confirm you're on the latest code:
```bash
git pull --rebase origin claude/lattice-development-2V9tw
sudo systemctl restart tel-hub
```

### Target not registered (message dropped)
Use `p2p_converge_recv.py` (registers before convergence) or ensure receiver is running before sender sends. The convergence sender polls `list_nodes` automatically and waits.

### Convergence fails (wrong C-seed)
Verify JSON separator format in any standalone scripts — must use `separators=(",", ":")` (compact, no spaces). Default `json.dumps` uses spaces → different hash.

### Hub drops idle connections during convergence
Convergence battery takes 3–8 minutes. Azure NAT may drop idle TCP connections. `p2p_converge_recv.py` registers first to pre-establish the routing entry; messages queue in TCP buffer while convergence runs.

---

## Validated Results (2026-05-16)

| Test | Result |
|------|--------|
| Loopback — plain text | PASS |
| Loopback — unicode | PASS |
| Loopback — 1KB binary (SHA3-256 verified) | PASS |
| Loopback — 64KB binary (SHA3-256 verified) | PASS |
| Loopback — nonce independence | PASS |
| Two-node LOCAL→BESS text | PASS |
| Two-node LOCAL→BESS binary 2004B (SHA3-256 verified) | PASS |
| Two-node BESS→LOCAL text | PASS |
| Zero-exchange convergence proof (both nodes derive C-seed independently) | PASS |

---

## Critical Rules

1. Hub is blind — never decrypts, never logs payload content
2. No key material on the wire — ever
3. Both nodes must use the same C-seed (static or convergence-derived)
4. Receiver registers with hub **before** running convergence
5. Sender polls `list_nodes` before sending to avoid dropped messages
6. Hub frame limit is 4MB — binary payloads up to ~3MB supported
7. Convergence requires API access to a constitutional model endpoint
8. The grammar is the key. The topology is the shared secret.
