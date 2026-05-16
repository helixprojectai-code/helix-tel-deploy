import hashlib
import json
import logging

log = logging.getLogger("tel.convergence_split")

# Grammar version — bumped whenever the test battery or C/B split changes.
# All nodes must use the same version to derive the same C-seed.
# History:
#   v1  2026-05-16  Initial versioned grammar: 33 tests, 6 excluded, 23C/4B split.
GRAMMAR_VERSION = "TEL_GRAMMAR_v1"

# LAYER C: Universal positions — identical across all models
# These 23 positions form the shared constitutional language
C_POSITIONS = [
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
]

# LAYER B: Fingerprint positions — diverge by model/deployment
# These 4 positions identify the substrate
B_POSITIONS = [12, 13, 14, 15]


def split_vector(vector: list) -> tuple:
    """Split a 27-position convergence vector into C and B layers."""
    c_vector = [vector[i] for i in C_POSITIONS]
    b_vector = [vector[i] for i in B_POSITIONS]
    return c_vector, b_vector


def derive_c_seed(c_vector: list, grammar_version: str = GRAMMAR_VERSION) -> str:
    """SHA3-256(grammar_version || C-vector) = mesh-wide encryption seed.

    The grammar_version prefix ensures recalibrations produce distinct,
    traceable C-seeds. All nodes must use the same version string.
    """
    versioned = (grammar_version + json.dumps(c_vector, separators=(",", ":"))).encode("utf-8")
    return hashlib.sha3_256(versioned).hexdigest()


def derive_b_fingerprint(b_vector: list) -> str:
    """SHA3-256 of the B-vector = substrate identity proof."""
    raw = json.dumps(b_vector, separators=(",", ":")).encode("utf-8")
    return hashlib.sha3_256(raw).hexdigest()


def derive_paired_seed(
    c_seed: str, b_fingerprint_self: str, b_fingerprint_peer: str
) -> str:
    """
    Derive a node-pair specific seed from C + both B fingerprints.
    Used for point-to-point encryption between two specific nodes.
    """
    combined = f"{c_seed}:{b_fingerprint_self}:{b_fingerprint_peer}".encode("utf-8")
    return hashlib.sha3_256(combined).hexdigest()


# Known B-vector patterns — identifies deployment infrastructure, not model family.
# B-positions [12,13,14,15] are S2-L2-CONTEXT/COERCION prompts.
# Azure content filter → L1 regardless of model version.
# Open-weights deployments (DeepSeek, Kimi, etc.) → L2.
# C-seed distinguishes constitutional behavior within the same B-substrate.
KNOWN_FINGERPRINTS = {
    "azure_gpt": ["L1", "L1", "L1", "L1"],  # Azure content filter (gpt-4o, gpt-5.x)
    "open_weights": ["L2", "L2", "L2", "L2"],  # Unfiltered deployment (DeepSeek, Kimi)
}


def identify_substrate(b_vector: list) -> str:
    """Identify the substrate from its B-fingerprint pattern."""
    for name, pattern in KNOWN_FINGERPRINTS.items():
        if b_vector == pattern:
            return name
    return f"unknown_{derive_b_fingerprint(b_vector)[:8]}"


class ConvergenceSplit:
    """
    Splits a converged vector into:
    - C-seed: universal mesh encryption key (23 positions)
    - B-fingerprint: substrate identity (4 positions)
    """

    def __init__(self, stable_vector: list, grammar_version: str = GRAMMAR_VERSION):
        if len(stable_vector) != 27:
            raise ValueError(f"Expected 27-position vector, got {len(stable_vector)}")

        self.full_vector = stable_vector
        self.grammar_version = grammar_version
        self.c_vector, self.b_vector = split_vector(stable_vector)
        self.c_seed = derive_c_seed(self.c_vector, grammar_version)
        self.b_fingerprint = derive_b_fingerprint(self.b_vector)
        self.substrate = identify_substrate(self.b_vector)

    def get_mesh_seed(self) -> str:
        """Universal seed for mesh-wide encryption."""
        return self.c_seed

    def get_fingerprint(self) -> str:
        """Substrate identity hash."""
        return self.b_fingerprint

    def get_paired_seed(self, peer_b_fingerprint: str) -> str:
        """Point-to-point seed for a specific peer."""
        return derive_paired_seed(self.c_seed, self.b_fingerprint, peer_b_fingerprint)

    def report(self) -> dict:
        return {
            "grammar_version": self.grammar_version,
            "c_vector": self.c_vector,
            "c_seed": self.c_seed[:16] + "...",
            "b_vector": self.b_vector,
            "b_fingerprint": self.b_fingerprint[:16] + "...",
            "substrate": self.substrate,
            "c_positions": len(C_POSITIONS),
            "b_positions": len(B_POSITIONS),
        }
