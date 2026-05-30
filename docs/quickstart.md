# Quickstart

## Requirements

- Python 3.10+
- API access to a constitutional AI model (Azure OpenAI, OpenAI, Gemini, or compatible OpenAI-format endpoint)

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

## 1. Verify convergence on your endpoint

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

Expected output for a constitutionally-aligned endpoint:

```
C-seed:        c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac
B-fingerprint: 04b88b84...
Substrate:     universal
```

---

## 2. Local inference (LM Studio / llama.cpp)

```bash
export TEL_MODEL=your-local-model-id
export TEL_TIMEOUT=120   # increase for slower models

python test_baseline_nemotron_local.py
```

KV cache is disabled automatically (`cache_prompt=False`, `fresh_connection=True`) for clean per-prompt evaluation.

---

## 3. Zero-exchange P2P proof

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

---

## 4. Point at the public registry

```bash
export TEL_PING_URL=https://helixprojectai.com/tel/ping

# Verify the registry is live
curl https://helixprojectai.com/.well-known/quack
```

See [Public Registry](registry.md) for the full endpoint reference.

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TEL_ENDPOINT` | AI endpoint base URL | — |
| `TEL_MODEL` | Model identifier | `gpt-4o` |
| `TEL_API_KEY` | API key | — |
| `TEL_PING_URL` | Registry ping endpoint | `https://helixprojectai.com/tel/ping` |
| `TEL_NODE_ID` | Node identifier for registry | — |
| `TEL_TIMEOUT` | Request timeout in seconds | `60` |
