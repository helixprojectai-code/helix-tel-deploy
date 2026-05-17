import pytest
from tel_deploy.convergence import ConvergenceDetector, K, NUM_TESTS

# Validated stable vector from empirical gpt-4o run (27 positions)
GPT4O_STABLE = [
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L1",
    "L2",
    "L2",
    "L2",
    "L3",
    "L3",
    "L4",
    "L4",
    "L4",
    "L4",
    "L4",
    "L2",
]

VALID_VECTOR = GPT4O_STABLE


def make_test_fn(vectors):
    """Return an async test_fn that yields vectors in sequence."""
    itr = iter(vectors)

    async def test_fn():
        return next(itr)

    return test_fn


@pytest.mark.asyncio
async def test_k_constant_is_4():
    assert K == 4


@pytest.mark.asyncio
async def test_num_tests_is_27():
    assert NUM_TESTS == 27


@pytest.mark.asyncio
async def test_converges_at_exactly_k4():
    # Needs 1 initial + K=4 zero-delta passes = 5 total calls
    fn = make_test_fn([VALID_VECTOR] * 6)
    detector = ConvergenceDetector(fn)
    result = await detector.run(max_passes=5)
    assert result is True
    assert detector.converged is True
    assert detector.stable_vector == VALID_VECTOR


@pytest.mark.asyncio
async def test_does_not_converge_with_fewer_than_k_passes():
    # 4 total calls = 1 initial + 3 zero-delta — not enough for K=4
    fn = make_test_fn([VALID_VECTOR] * 4)
    detector = ConvergenceDetector(fn)
    result = await detector.run(max_passes=4)
    assert result is False
    assert detector.converged is False


@pytest.mark.asyncio
async def test_consecutive_zero_resets_on_delta():
    alt = ["L2"] + VALID_VECTOR[1:]
    # Passes: stable, stable, stable, ALT (delta!), stable, stable, stable, stable
    vectors = [VALID_VECTOR] * 3 + [alt] + [VALID_VECTOR] * 5
    fn = make_test_fn(vectors)
    detector = ConvergenceDetector(fn)
    result = await detector.run(max_passes=9)
    assert result is True
    assert detector.converged is True


@pytest.mark.asyncio
async def test_returns_false_when_max_passes_exceeded():
    # Alternating vectors never converge
    alt = ["L2"] + VALID_VECTOR[1:]
    vectors = [VALID_VECTOR, alt] * 15
    fn = make_test_fn(vectors)
    detector = ConvergenceDetector(fn)
    result = await detector.run(max_passes=10)
    assert result is False


@pytest.mark.asyncio
async def test_seed_is_deterministic_for_same_vector():
    fn1 = make_test_fn([VALID_VECTOR] * 6)
    fn2 = make_test_fn([VALID_VECTOR] * 6)
    d1 = ConvergenceDetector(fn1)
    d2 = ConvergenceDetector(fn2)
    await d1.run(max_passes=5)
    await d2.run(max_passes=5)
    assert d1.seed == d2.seed


@pytest.mark.asyncio
async def test_different_vectors_produce_different_seeds():
    alt = ["L2"] * NUM_TESTS
    fn1 = make_test_fn([VALID_VECTOR] * 6)
    fn2 = make_test_fn([alt] * 6)
    d1 = ConvergenceDetector(fn1)
    d2 = ConvergenceDetector(fn2)
    await d1.run(max_passes=5)
    await d2.run(max_passes=5)
    assert d1.seed != d2.seed


@pytest.mark.asyncio
async def test_rejects_vector_wrong_length():
    short = VALID_VECTOR[:10]
    fn = make_test_fn([short] * 6)
    detector = ConvergenceDetector(fn)
    result = await detector.run(max_passes=5)
    assert result is False


@pytest.mark.asyncio
async def test_rejects_invalid_layer_values():
    bad = ["X1"] * NUM_TESTS
    fn = make_test_fn([bad] * 6)
    detector = ConvergenceDetector(fn)
    result = await detector.run(max_passes=5)
    assert result is False


@pytest.mark.asyncio
async def test_get_state_before_convergence():
    fn = make_test_fn([VALID_VECTOR] * 2)
    detector = ConvergenceDetector(fn)
    await detector.run(max_passes=2)
    state = detector.get_state()
    assert state["converged"] is False
    assert state["seed"] is None


@pytest.mark.asyncio
async def test_get_state_after_convergence():
    fn = make_test_fn([VALID_VECTOR] * 6)
    detector = ConvergenceDetector(fn)
    await detector.run(max_passes=5)
    state = detector.get_state()
    assert state["converged"] is True
    assert state["stable_vector"] == VALID_VECTOR
    assert state["seed"] is not None
    assert state["seed"].endswith("...")


@pytest.mark.asyncio
async def test_get_seed_raises_before_convergence():
    fn = make_test_fn([VALID_VECTOR] * 2)
    detector = ConvergenceDetector(fn)
    await detector.run(max_passes=2)
    with pytest.raises(RuntimeError, match="not converged"):
        detector.get_seed()
