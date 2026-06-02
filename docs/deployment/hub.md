# Mesh Hub

The hub is a blind asyncio JSON message router. It routes ciphertext frames between nodes and never decrypts, stores, or inspects payload content.

## Architecture

```
                    ┌─────────────────────┐
                    │      TEL HUB        │
                    │   host:9738         │
                    │  (blind JSON router) │
                    └────────┬────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐
        │  SPIDER   │ │   BESS    │ │ KIMICLAW  │
        └───────────┘ └───────────┘ └───────────┘
```

- Hub is **blind** — routes JSON frames, never decrypts
- All encryption/decryption happens at edge nodes only
- No key material transmitted — ciphertext + nonce only
- Frame limit: 4MB

## Start the Hub

```bash
tel hub
```

Or directly:

```bash
bash run_hub.sh
```

## Systemd Service

Install for auto-restart on boot:

```bash
# Edit tel-hub.service to set your working directory and user
sudo cp tel-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tel-hub
```

Check status:

```bash
sudo systemctl status tel-hub
journalctl -u tel-hub -f
```

## Config

```yaml
hub:
  host: 0.0.0.0   # bind address
  port: 9738
```

The hub listens on the configured port. Nodes connect via TCP and identify themselves with a `register` action on connection.
