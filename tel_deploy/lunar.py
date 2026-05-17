import hashlib
from datetime import datetime, timezone

# Synodic month = 29.53 days
# Reference new moon: January 6, 2000 18:14 UTC
SYNODIC_PERIOD = 29.53058867
REF_NEW_MOON = datetime(2000, 1, 6, 18, 14, 0, tzinfo=timezone.utc)


def lunar_day() -> int:
    """Current day in the lunar cycle (0-29). Deterministic from UTC clock."""
    now = datetime.now(timezone.utc)
    delta = (now - REF_NEW_MOON).total_seconds() / 86400.0
    return int(delta % SYNODIC_PERIOD)


def lunar_shuffle(num_tests: int, day: int = None) -> list:
    """
    Generate a deterministic permutation of test indices based on lunar day.
    Both nodes compute the same order independently from the same calendar.
    """
    if day is None:
        day = lunar_day()

    # Deterministic seed from lunar day
    seed_bytes = hashlib.sha256(f"TEL_LUNAR_{day}".encode()).digest()

    # Fisher-Yates shuffle with deterministic random source
    indices = list(range(num_tests))
    for i in range(num_tests - 1, 0, -1):
        # Extract deterministic random index from seed
        offset = i % 32
        j = seed_bytes[offset] % (i + 1)
        indices[i], indices[j] = indices[j], indices[i]
        # Rotate seed for next iteration
        seed_bytes = hashlib.sha256(seed_bytes + i.to_bytes(2, "big")).digest()

    return indices


def unshuffle_vector(vector: list, order: list) -> list:
    """
    Re-sort a shuffled result vector back to canonical positions.
    After execution in lunar order, restore to fixed C/B positions.
    """
    canonical = [None] * len(vector)
    for exec_idx, canonical_idx in enumerate(order):
        canonical[canonical_idx] = vector[exec_idx]
    return canonical
