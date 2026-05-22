"""
TEL v2 Ping Client — node heartbeat and peer discovery.

Posts a signed ping to the TEL registry at helixprojectai.com/tel/ping.
Returns live peer records. Does not transmit C-seeds or HMAC proofs —
those are handled by the session layer after peers are discovered.

Usage:
    client = PingClient(node_id="SPIDER", topology="universal")
    response = await client.ping(c_seed=my_seed)   # one-shot
    peers = response.compatible_peers()             # same topology + grammar

    await client.start_heartbeat(c_seed=my_seed, interval=300)  # async loop
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

log = logging.getLogger("tel.ping")

PING_URL = os.environ.get("TEL_PING_URL", "https://helixprojectai.com/tel/ping")
PROTOCOL_VERSION = "TEL_PING_v2"
GRAMMAR_VERSION = "TEL_GRAMMAR_v1"
STALE_THRESHOLD = 600  # seconds — peers not seen in 10 min are stale


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PingPayload:
    node_id: str
    topology: str
    grammar: str = GRAMMAR_VERSION
    version: str = PROTOCOL_VERSION
    nonce: str = field(default_factory=lambda: secrets.token_hex(32))
    timestamp: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "topology": self.topology,
            "grammar": self.grammar,
            "version": self.version,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
        }


@dataclass
class PeerRecord:
    node_id: str
    topology: str
    grammar: str
    nonce: str
    last_seen: int
    status: str  # "live" | "stale"

    def is_compatible(self, topology: str, grammar: str) -> bool:
        return self.topology == topology and self.grammar == grammar

    def is_live(self) -> bool:
        return self.status == "live" and (
            time.time() - self.last_seen < STALE_THRESHOLD
        )


@dataclass
class PingResponse:
    status: str
    server_time: int
    peers: list[PeerRecord]
    my_nonce: str  # the nonce we sent — retained for HMAC challenges

    def compatible_peers(self, topology: str, grammar: str) -> list[PeerRecord]:
        return [
            p for p in self.peers if p.is_compatible(topology, grammar) and p.is_live()
        ]


# ---------------------------------------------------------------------------
# HMAC proof helpers (used by session layer, not by ping itself)
# ---------------------------------------------------------------------------


def make_proof(c_seed: str, peer_nonce: str) -> str:
    """HMAC(C-seed, peer_nonce) — proves we hold the same seed without revealing it."""
    key = bytes.fromhex(c_seed)
    msg = bytes.fromhex(peer_nonce)
    return hmac.new(key, msg, hashlib.sha3_256).hexdigest()


def verify_proof(c_seed: str, nonce: str, peer_proof: str) -> bool:
    """Verify a peer's HMAC proof against our own C-seed."""
    expected = make_proof(c_seed, nonce)
    return hmac.compare_digest(expected, peer_proof)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PingClient:
    def __init__(
        self,
        node_id: str,
        topology: str,
        grammar: str = GRAMMAR_VERSION,
        ping_url: str = PING_URL,
        timeout: float = 10.0,
    ):
        self.node_id = node_id
        self.topology = topology
        self.grammar = grammar
        self.ping_url = ping_url
        self.timeout = timeout
        self._last_response: Optional[PingResponse] = None

    async def ping(self, c_seed: Optional[str] = None) -> PingResponse:
        """
        Fire a single ping. Returns parsed PingResponse with live peer list.
        c_seed is not transmitted — it's used locally to generate proof_of_seed
        if the server requests a challenge (future use).
        """
        payload = PingPayload(
            node_id=self.node_id,
            topology=self.topology,
            grammar=self.grammar,
        )

        body = payload.to_dict()

        # Attach proof-of-seed if we have a seed (server can optionally verify)
        # proof is HMAC(c_seed, nonce) — server never stores seed, only checks proof
        if c_seed:
            body["proof"] = make_proof(c_seed, payload.nonce)

        log.info(
            f"Ping → {self.ping_url}  node={self.node_id} topology={self.topology} nonce={payload.nonce[:8]}..."
        )

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            try:
                r = await http.post(
                    self.ping_url,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                log.error(f"Ping HTTP error: {e.response.status_code}")
                raise
            except httpx.RequestError as e:
                log.error(f"Ping request failed: {e}")
                raise

        data = r.json()

        peers = [
            PeerRecord(
                node_id=p["node_id"],
                topology=p["topology"],
                grammar=p["grammar"],
                nonce=p["nonce"],
                last_seen=p["last_seen"],
                status=p["status"],
            )
            for p in data.get("peers", [])
            if p["node_id"] != self.node_id  # exclude self
        ]

        response = PingResponse(
            status=data.get("status", "unknown"),
            server_time=data.get("server_time", 0),
            peers=peers,
            my_nonce=payload.nonce,
        )

        self._last_response = response
        compatible = response.compatible_peers(self.topology, self.grammar)
        log.info(f"Ping ok — {len(peers)} peers, {len(compatible)} compatible")

        return response

    async def start_heartbeat(
        self,
        c_seed: Optional[str] = None,
        interval: int = 300,
        on_peer_change=None,
        respond_to_challenges: bool = True,
    ):
        """
        Async heartbeat loop. Pings every `interval` seconds.
        - Calls on_peer_change(peers) if the compatible peer set changes.
        - If respond_to_challenges=True and c_seed is set, checks for
          incoming session challenges and responds automatically.
        """
        import asyncio
        from .session import SessionResponder

        prev_peer_ids = set()
        responder = (
            SessionResponder(self.node_id) if respond_to_challenges and c_seed else None
        )
        log.info(
            f"Heartbeat started — interval={interval}s  session_responder={responder is not None}"
        )

        while True:
            try:
                response = await self.ping(c_seed=c_seed)
                compatible = response.compatible_peers(self.topology, self.grammar)
                curr_peer_ids = {p.node_id for p in compatible}

                if curr_peer_ids != prev_peer_ids:
                    log.info(f"Peer set changed: {prev_peer_ids} → {curr_peer_ids}")
                    if on_peer_change:
                        await on_peer_change(compatible)
                    prev_peer_ids = curr_peer_ids

                # Auto-respond to any pending session challenges
                if responder and c_seed:
                    responded = await responder.check_and_respond(c_seed)
                    if responded:
                        log.info(f"Session challenges answered: {responded}")

            except Exception as e:
                log.warning(f"Heartbeat ping failed: {e}")

            await asyncio.sleep(interval)
