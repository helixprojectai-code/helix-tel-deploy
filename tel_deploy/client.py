import asyncio
import json
import logging
from .cipher import TrueHDUECipher
from .convergence import ConvergenceDetector
from .protocol import parse_message

log = logging.getLogger("tel")


class TELClient:
    def __init__(
        self,
        host: str,
        port: int,
        node_id: str,
        seed: str = None,
        reconnect_cfg: dict = None,
    ):
        self.host = host
        self.port = port
        self.node_id = node_id
        self._static_seed = seed
        self.cipher = TrueHDUECipher(seed) if seed else None
        self.reconnect = reconnect_cfg or {
            "enabled": True,
            "interval_seconds": 5,
            "max_attempts": 0,
        }
        self._reader = None
        self._writer = None
        self._connected = False
        self._on_message = None
        self._convergence = None

    async def converge(self, test_fn, max_passes: int = 20):
        """Run convergence detector to derive seed from constitutional shape.
        Produces both C-seed (universal mesh key) and B-fingerprint (substrate identity).
        """
        from .convergence_split import ConvergenceSplit

        self._convergence = ConvergenceDetector(test_fn)
        success = await self._convergence.run(max_passes=max_passes)
        if success:
            self._split = ConvergenceSplit(self._convergence.stable_vector)
            # Use C-seed for mesh encryption (universal)
            self.cipher = TrueHDUECipher(self._split.get_mesh_seed())
            log.info(
                f"Cipher initialized from C-seed. Substrate: {self._split.substrate}"
            )
        else:
            self._split = None
            if self._static_seed:
                log.warning("Convergence failed. Falling back to static seed.")
                self.cipher = TrueHDUECipher(self._static_seed)
            else:
                raise RuntimeError(
                    "Convergence failed. No static seed fallback. Cannot join mesh."
                )
        return success

    def on_message(self, callback):
        self._on_message = callback

    async def connect(self):
        attempts = 0
        while True:
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    self.host, self.port, limit=4 * 1024 * 1024
                )
                self._connected = True

                handshake = (
                    json.dumps({"action": "register", "node_id": self.node_id}) + "\n"
                )
                self._writer.write(handshake.encode())
                await self._writer.drain()
                log.info(f"Connected and registered as {self.node_id}")
                return

            except (ConnectionRefusedError, OSError) as e:
                attempts += 1
                max_att = self.reconnect["max_attempts"]
                if max_att and attempts >= max_att:
                    log.error(f"Failed to connect after {attempts} attempts.")
                    raise
                interval = self.reconnect["interval_seconds"]
                log.warning(f"Connection failed ({e}). Retry in {interval}s...")
                await asyncio.sleep(interval)

    async def listen(self):
        while True:
            while self._connected:
                try:
                    data = await self._reader.readline()
                    if not data:
                        log.warning("Hub closed connection.")
                        self._connected = False
                        break

                    msg = json.loads(data.decode().strip())
                    if msg.get("action") == "route":
                        sender = msg.get("sender")
                        payload = msg.get("payload")
                        kind = payload.get("kind", "text")

                        if kind == "binary":
                            raw = self.cipher.decrypt_bytes(payload)
                            fname = payload.get("filename", "received.bin")
                            log.info(
                                f"\U0001f513 [{sender}] binary {len(raw)}B filename={fname}"
                            )
                            if self._on_message:
                                await self._on_message(
                                    sender,
                                    {"type": "binary", "data": raw, "filename": fname},
                                )
                        else:
                            plaintext = self.cipher.decrypt(payload)
                            parsed = parse_message(plaintext)
                            log.info(
                                f"\U0001f513 [{sender}] {parsed.get('type', '?')}: {parsed.get('body', plaintext)}"
                            )
                            if self._on_message:
                                await self._on_message(sender, parsed)

                except json.JSONDecodeError:
                    log.error("Malformed message from hub.")
                except Exception as e:
                    log.error(f"Listen error: {e}")
                    self._connected = False
                    break

            if not self.reconnect.get("enabled"):
                break
            log.info("Attempting reconnect...")
            await self.connect()

    async def send(self, target: str, plaintext: str):
        if not self._connected:
            log.error("Not connected.")
            return False

        encrypted = self.cipher.encrypt(plaintext)
        frame = (
            json.dumps({"action": "send", "target": target, "payload": encrypted})
            + "\n"
        )
        self._writer.write(frame.encode())
        await self._writer.drain()
        log.info(f"\U0001f512 -> {target} [text {len(plaintext)}B]")
        return True

    async def send_bytes(self, target: str, data: bytes, filename: str = None):
        """Encrypt and send raw bytes. filename is metadata only — not transmitted in clear."""
        if not self._connected:
            log.error("Not connected.")
            return False

        encrypted = self.cipher.encrypt_bytes(data, kind="binary")
        if filename:
            encrypted["filename"] = filename
        frame = (
            json.dumps({"action": "send", "target": target, "payload": encrypted})
            + "\n"
        )
        self._writer.write(frame.encode())
        await self._writer.drain()
        log.info(f"\U0001f512 -> {target} [binary {len(data)}B]")
        return True

    async def status(self) -> dict:
        return {
            "node_id": self.node_id,
            "connected": self._connected,
            "hub": f"{self.host}:{self.port}",
            "msg_counter": self.cipher.msg_counter if self.cipher else 0,
        }

    async def close(self):
        self._connected = False
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
