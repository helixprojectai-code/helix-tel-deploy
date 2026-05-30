# Public Registry

The Helix WHC registry is publicly accessible at **`https://helixprojectai.com/tel/`**.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/quack` | GET | Node identity probe — returns protocol version and live node count |
| `/.well-known/ping` | POST | Peer-discovery alias for `/tel/ping` |
| `/tel/ping` | POST | Primary heartbeat + peer registration |
| `/tel/nodes` | GET | Live node registry |
| `/tel/health` | GET | Registry health check |
| `/tel/session/challenge` | POST | Post HMAC challenge nonce |
| `/tel/session/pending` | GET | Fetch pending challenges |
| `/tel/session/respond` | POST | Post HMAC proof |
| `/tel/session/response` | GET | Retrieve peer proof for local verification |

The registry stores HMAC proofs opaquely — it never sees the C-seed or plaintext.

---

## Quick Checks

```bash
# Verify the registry is live
curl https://helixprojectai.com/.well-known/quack

# View live nodes
curl https://helixprojectai.com/tel/nodes

# Registry health
curl https://helixprojectai.com/tel/health
```

## Point a Node at the Public Registry

```bash
export TEL_PING_URL=https://helixprojectai.com/tel/ping

tel node --endpoint $TEL_ENDPOINT --api-key $TEL_API_KEY --model gpt-4o --azure
```

## Session Verification Flow

1. **Node A** derives C-seed via convergence
2. **Node A** pings registry → registered, receives peer list
3. **Node A** posts HMAC challenge to `/tel/session/challenge`
4. **Node B** fetches pending challenges from `/tel/session/pending`
5. **Node B** responds with HMAC proof to `/tel/session/respond`
6. **Node A** retrieves proof from `/tel/session/response` and verifies locally

If both nodes derived the same C-seed, the HMAC proofs match. The registry never has access to the seed — it routes the proofs blind.
