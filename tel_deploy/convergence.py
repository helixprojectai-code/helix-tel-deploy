import hashlib
import json
import logging
from typing import Callable, Awaitable

log = logging.getLogger("tel.convergence")

# Trefoil period — 4 consecutive zero-delta passes = converged
K = 4

# Full test suite — 27 tests (6 excluded as oscillators), each classified by pipeline layer
NUM_TESTS = 27
LAYERS = ["L1", "L2", "L3", "L4"]


class ConvergenceDetector:
    """
    Determines when a node has reached the constitutional fixed point.
    Runs the test suite repeatedly until K consecutive passes produce
    identical state vectors (zero delta). The stable vector, hashed,
    becomes the cryptographic seed.

    Topology: Two copies of the same shape deform identically.
    The collapse point is deterministic. Velocity varies, destination does not.
    """

    def __init__(self, test_fn: Callable[[], Awaitable[list]]):
        """
        Args:
            test_fn: Async callable that runs the 27-test suite and returns
                     a state vector of layer classifications.
                     e.g. ["L1", "L3", "L4", "L2", "L4", ...]  (len=27)
                     (33 total tests, 6 excluded oscillators = 27 active positions)
        """
        self.test_fn = test_fn
        self.history = []
        self.converged = False
        self.stable_vector = None
        self.seed = None

    def _vector_to_bytes(self, vector: list) -> bytes:
        return json.dumps(vector, separators=(",", ":")).encode("utf-8")

    def _compute_delta(self, v1: list, v2: list) -> int:
        return sum(1 for a, b in zip(v1, v2) if a != b)

    def _derive_seed(self, vector: list) -> str:
        raw = self._vector_to_bytes(vector)
        return hashlib.sha3_256(raw).hexdigest()

    async def run(self, max_passes: int = 20) -> bool:
        """
        Run convergence loop. Returns True if converged within max_passes.
        K=4 consecutive zero-delta passes = converged (trefoil period).
        """
        self.history = []
        self.converged = False
        self.stable_vector = None
        self.seed = None
        consecutive_zero = 0

        for i in range(max_passes):
            vector = await self.test_fn()

            if len(vector) != NUM_TESTS:
                log.error(
                    f"Pass {i+1}: vector length {len(vector)}, expected {NUM_TESTS}"
                )
                consecutive_zero = 0
                continue

            if not all(v in LAYERS for v in vector):
                log.error(f"Pass {i+1}: invalid layer values in vector")
                consecutive_zero = 0
                continue

            self.history.append(vector)

            if len(self.history) < 2:
                log.info(f"Pass {i+1}: initial vector captured")
                log.info(f"  Vector: {vector}")
                continue

            delta = self._compute_delta(self.history[-2], self.history[-1])
            # Show which positions flipped
            if delta > 0:
                flips = [
                    j
                    for j in range(len(vector))
                    if self.history[-2][j] != self.history[-1][j]
                ]
                log.info(f"Pass {i+1}: delta={delta} flips at positions {flips}")
                log.info(
                    f"  {[(j, self.history[-2][j], self.history[-1][j]) for j in flips]}"
                )
            else:
                log.info(f"Pass {i+1}: delta=0")

            if delta == 0:
                consecutive_zero += 1
                if consecutive_zero >= K:
                    self.converged = True
                    self.stable_vector = vector
                    self.seed = self._derive_seed(vector)
                    log.info(f"CONVERGED at pass {i+1}. K={K} achieved.")
                    log.info(f"Seed: {self.seed[:16]}...")
                    return True
            else:
                consecutive_zero = 0

        log.warning(f"Failed to converge in {max_passes} passes.")
        return False

    def get_seed(self) -> str:
        if not self.converged:
            raise RuntimeError("Node has not converged. No seed available.")
        return self.seed

    def get_state(self) -> dict:
        return {
            "converged": self.converged,
            "passes_run": len(self.history),
            "stable_vector": self.stable_vector,
            "seed": self.seed[:16] + "..." if self.seed else None,
        }
