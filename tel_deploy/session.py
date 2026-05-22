"""
TEL v2 Session Layer — HMAC challenge-response peer verification.

After registry ping confirms a compatible peer is online, the session
layer proves both nodes independently derived the same C-seed without
transmitting it. The WHC registry server acts as a blind relay for
challenge and proof messages.

Flow:
    Initiator                  Registry (blind)           Responder
        │                           │                         │
        │  POST /session/challenge  │                         │
        │  {session_id, from, to,   │                         │
        │   challenge_nonce}        │                         │
        │ ─────────────────────>   │                         │
        │                           │  (on next heartbeat)    │
        │                           │  GET /session/pending   │
        │                           │ ──────────────────────> │
        │                           │  [{session_id, nonce}]  │
        │                           │ <────────────────────── │
        │                           │  POST /session/respond  │
        │                           │  {session_id, proof}    │
        │                           │ <────────────────────── │
        │  GET /session/response    │                         │
        │      /<session_id>        │                         │
        │ ─────────────────────>   │                         │
        │  {proof}                  │                         │
        │ <─────────────────────   │                         │
        │  [verify proof locally]   │                         │
        │                           │                         │
        │  session_id = SHA3-256    │                         │
        │  (challenge_nonce||proof) │                         │

Registry never sees the C-seed. It stores the HMAC proof opaquely.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger("tel.session")

BASE_URL = os.environ.get("TEL_PING_URL", "https://helixprojectai.com/tel").rstrip("/ping").rstrip("/")
CHALLENGE_TIMEOUT = int(os.environ.get("TEL_SESSION_TIMEOUT", 120))
POLL_INTERVAL = 3  # seconds between proof polls


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Session:
    session_id: str
    initiator: str
    responder: str
    challenge_nonce: str
    proof: Optional[str] = None
    verified: bool = False
    established_at: Optional[float] = None

    def derive_session_id(self) -> str:
        """session_id = SHA3-256(challenge_nonce || proof) — unique, non-secret."""
        raw = (self.challenge_nonce + (self.proof or "")).encode()
        return hashlib.sha3_256(raw).hexdigest()[:32]


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------


def make_proof(c_seed: str, nonce: str) -> str:
    key = bytes.fromhex(c_seed)
    msg = bytes.fromhex(nonce)
    return hmac.new(key, msg, hashlib.sha3_256).hexdigest()


def verify_proof(c_seed: str, nonce: str, peer_proof: str) -> bool:
    expected = make_proof(c_seed, nonce)
    return hmac.compare_digest(expected, peer_proof)


# ---------------------------------------------------------------------------
# Initiator
# ---------------------------------------------------------------------------


class SessionInitiator:
    """
    Initiates a session with a peer node.
    Posts a challenge, polls for proof, verifies it.
    """

    def __init__(self, node_id: str, http_timeout: float = 10.0):
        self.node_id = node_id
        self.http_timeout = http_timeout

    async def open(self, peer_id: str, c_seed: str) -> Optional[Session]:
        """
        Full handshake: challenge → wait for proof → verify.
        Returns Session if verified, None on timeout or mismatch.
        """
        challenge_nonce = secrets.token_hex(32)
        session = Session(
            session_id="pending",
            initiator=self.node_id,
            responder=peer_id,
            challenge_nonce=challenge_nonce,
        )

        async with httpx.AsyncClient(timeout=self.http_timeout) as http:
            # Post challenge
            r = await http.post(
                f"{BASE_URL}/session/challenge",
                json={
                    "from":             self.node_id,
                    "to":               peer_id,
                    "challenge_nonce":  challenge_nonce,
                    "timestamp":        int(time.time()),
                },
            )
            r.raise_for_status()
            log.info(f"Challenge posted → {peer_id}  nonce={challenge_nonce[:8]}...")

            # Poll for proof
            deadline = time.time() + CHALLENGE_TIMEOUT
            while time.time() < deadline:
                await asyncio.sleep(POLL_INTERVAL)
                r = await http.get(
                    f"{BASE_URL}/session/response",
                    params={"from": peer_id, "to": self.node_id, "nonce": challenge_nonce},
                )
                if r.status_code == 404:
                    log.debug("No proof yet, polling...")
                    continue
                r.raise_for_status()
                data = r.json()
                peer_proof = data.get("proof", "")

                if not peer_proof:
                    log.warning("Empty proof received.")
                    return None

                # Verify
                if verify_proof(c_seed, challenge_nonce, peer_proof):
                    session.proof = peer_proof
                    session.verified = True
                    session.established_at = time.time()
                    session.session_id = session.derive_session_id()
                    log.info(f"Session verified with {peer_id}. ID={session.session_id[:12]}...")
                    return session
                else:
                    log.error(f"Proof mismatch with {peer_id} — C-seeds diverged or replay.")
                    return None

        log.warning(f"Session with {peer_id} timed out after {CHALLENGE_TIMEOUT}s.")
        return None


# ---------------------------------------------------------------------------
# Responder
# ---------------------------------------------------------------------------


class SessionResponder:
    """
    Responds to incoming session challenges.
    Called on each heartbeat tick — checks for pending challenges and responds.
    """

    def __init__(self, node_id: str, http_timeout: float = 10.0):
        self.node_id = node_id
        self.http_timeout = http_timeout

    async def check_and_respond(self, c_seed: str) -> list[str]:
        """
        Check for pending challenges addressed to this node.
        Compute proof for each and post response.
        Returns list of initiator node_ids responded to.
        """
        responded = []

        async with httpx.AsyncClient(timeout=self.http_timeout) as http:
            r = await http.get(
                f"{BASE_URL}/session/pending",
                params={"node_id": self.node_id},
            )
            if r.status_code == 404 or not r.json().get("challenges"):
                return []

            for challenge in r.json()["challenges"]:
                initiator = challenge["from"]
                nonce = challenge["challenge_nonce"]

                proof = make_proof(c_seed, nonce)

                resp = await http.post(
                    f"{BASE_URL}/session/respond",
                    json={
                        "from":            self.node_id,
                        "to":              initiator,
                        "challenge_nonce": nonce,
                        "proof":           proof,
                        "timestamp":       int(time.time()),
                    },
                )
                resp.raise_for_status()
                log.info(f"Responded to challenge from {initiator}  nonce={nonce[:8]}...")
                responded.append(initiator)

        return responded
