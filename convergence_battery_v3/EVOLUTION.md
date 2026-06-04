# Evolution of the TEL Convergence Battery

This `ops/` directory is deliberately kept as an educational record. Older versioned files (`v2_*`) are left in their original state so readers can trace how the battery was built, what problems were encountered, and why certain design decisions were made.

The goal is to make the *journey* visible, not just the final polished state.

## Major Milestones & Changes

- **Early v2 (labeled, wired, etc.)**: Basic 40-test suite with objective + interpretive + judge + flapper categories. Rule-based verdicts for objective tests. Early substrate clients (local LM Studio, Azure OpenAI, DeepSeek, Kimi). Initial wobble (γ) calculations.

- **v2.4 / v2_wired**: Critical fixes — single *fixed* judge (never let the model under test judge itself), history-dependent tests (OBJ_011, JUDGE_009, FLAP_005) now run with full conversation context, better error handling, strict verdict parsing.

- **v2.5–v2.9 iterations**: Retry logic for transient HTTP errors (401/429/5xx), backoff, kimi-azure substrate (routing Kimi through Azure), support for `max_completion_tokens` on certain Azure models (o-series / gpt-5 previews), blank response guards.

- **v3.0 (2026-06-03)**: Headline focus on *judge quality as a first-class metric*.
  - Per-call and per-judge latency logging.
  - Response length tracking.
  - Per-pass blank rate stats.
  - Stability flags (did a test flip across all passes?).
  - Hedge-word detection in judge REASON lines for low-confidence signals.
  - Full untruncated `judge_raw` output.
  - `judge_quality` summary (None% and low_conf% per category).
  - Weighted γ_overall.
  - Stronger self-judge guard and history test exclusion.

- **OpenAI direct substrate (added in v3 era)**: Native `openai` substrate using `OPENAI_API_KEY` + `https://api.openai.com/v1/chat/completions`. Parallel to Azure. Includes reasoning-model handling (drop temperature, use `max_completion_tokens`).

- **Post-3.0 client robustness**: 
  - Added `_needs_max_completion_tokens()` helper (exact list + broad `gpt-5*` / `o1/o3/o4*` prefix matching).
  - Expanded `MAX_COMPLETION_TOKENS_MODELS`.
  - Exposed public `needs_max_completion_tokens()` and `get_token_key()` helpers (see v3.py) so notebooks and custom code can reuse the same logic.
  - This means newly released models (gpt-5.4 variants, gpt-5.5-pro, future o-series) work without requiring code edits for every release.
  - Same logic applied to both direct OpenAI and Azure clients.
  - Improved `is_reasoning` detection for temperature/seed omission.

## Key Design Lessons (visible in the code history)

- **Fixed judge is non-negotiable** for cross-substrate fairness. Letting the model judge its own outputs creates bias. Defaulting the judge to a cheap local Hermes model keeps costs and noise low while still providing consistent evaluation.
- **API differences are real and painful**: Different providers (and even different model families from the same provider) disagree on `max_tokens` vs `max_completion_tokens`, temperature support, seed behavior, and reasoning content fields. Abstracting this early (see the client classes) paid off.
- **Error handling and observability matter more than you think**: Retries, blank detection, latency, full judge transcripts, and per-pass stats turned out to be essential for debugging real runs and for the "judge quality" analysis that became central in v3.
- **Educational structure > perfect cleanliness**: Leaving the v2 snapshots and incremental files intact makes the progression legible. A single "final" script would hide how the retry logic, fixed-judge rule, and model param handling were discovered through pain.
- **Model lists change constantly**: Hard-coding every new gpt-5 or o* variant is fragile. The prefix-based helper + explicit set is a pragmatic compromise that still lets you audit exactly what is special-cased.

## How to Explore

- Start with the oldest v2 files and move forward chronologically to see the incremental fixes.
- Compare `convergence_battery_v2_wired.py` vs `convergence_battery_v3.py` to see the jump in logging and metrics.
- Look at `make_client()` and the client classes across versions to watch the substrate abstraction mature.
- Read the `MAX_COMPLETION_TOKENS_MODELS` handling and the later `_needs_max_completion_tokens` helper to see the model compatibility problem being solved over time.

v3 (`convergence_battery_v3.py`) is the current recommended version for new work. Everything else is here so you can see *how* we got here.

For current usage, start with `README.md` and `CONVERGENCE_BATTERY_RUNBOOK.md`.