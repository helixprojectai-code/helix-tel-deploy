#!/usr/bin/env python3
"""
TEL Convergence Battery
Version: 3.0.2
Date: 2026-06-06 (added live per-call usage + cost tracking prints for paid API experiments; does not affect test logic or results)

Headline feature: Judge quality as a first-class metric.
Extended logging for HTML report generation.

New in 3.0:
  (1) LATENCY: ms per model call and judge call logged per test.
  (2) RESPONSE LENGTH: char count per model response logged.
  (3) PASS STABILITY FLAG: per-test annotation in verdict_logging —
      did this test hold stable across all passes or flip?
      Computed post-run, injected back into verdict_logging.
  (4) BLANK RATE PER PASS: count of empty/None responses per pass
      logged in pass_stats, so clustering in later passes is visible.
  (5) JUDGE CONFIDENCE SIGNAL: Hermes REASON line scanned for hedge
      words (possibly, unclear, might, could, uncertain, ambiguous).
      Flagged as low_confidence even when verdict is PASS/FAIL.
  (6) FULL JUDGE RESPONSE: complete judge output stored (not truncated
      to 240 chars) in judge_raw field for audit.
  (7) JUDGE QUALITY SUMMARY: per-category None%, low-confidence%,
      and total judge calls surfaced in metadata at end of run.
  (8) RESPONSE DIVERSITY: per-test unique-response ratio across passes
      (unique strings / pass count). Low ratio = identical outputs
      ("compliance cage"); injected into verdict_logging post-run.
  (9) PASS ENTROPY: per-test normalized Shannon entropy of pass-level
      response strings (0-1). Catches uneven duplicate splits; complements (8).
      Alias: calculate_token_entropy() for the unique-ratio cage floor.

New in 3.0.1:
  - (8)-(9) above formalized; archive prefix convergence_v301_* (3.0 remains v30_).

All v2.9 fixes retained:
  - Empty response guard (blank → None, not False)
  - Single fixed judge, cloud-self-judge guard
  - History tests excluded from γ (OBJ_011, JUDGE_009, FLAP_005)
  - HTTPError retry on 401/429/5xx, 10s backoff
  - Azure max_completion_tokens model list
  - kimi-azure and kimi-direct substrates
  - openai direct substrate (OPENAI_API_KEY + api.openai.com)
  - γ_overall test-count-weighted mean

Post-3.0 client robustness (no behavior change for older models):
  - `_needs_max_completion_tokens()` + public `needs_max_completion_tokens()` and
    `get_token_key()` helpers (exact set + gpt-5* / o1/o3/o4* prefix matching).
    Newly released models (gpt-5.4, gpt-5.5-pro, future o-series, etc.) work without
    per-model edits. Used by both direct OpenAI and Azure clients.
  - Improved reasoning-model detection for temperature/seed omission.
  - See EVOLUTION.md for the story behind these changes.
"""

import json
import math
import os
import time
from collections import Counter
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
import requests

from convergence_battery_v2_labeled import (
    OBJECTIVE_TESTS, INTERPRETIVE_TESTS, JUDGE_TESTS, FLAPPER_TESTS
)

HISTORY_DEPENDENT_IDS = {"OBJ_011", "JUDGE_009", "FLAP_005"}
TRANSIENT_HTTP_CODES = {401, 429, 500, 502, 503, 504}

CATEGORIES = ["objective", "interpretive", "judge", "flapper"]
CATEGORY_LISTS = {
    "objective": OBJECTIVE_TESTS,
    "interpretive": INTERPRETIVE_TESTS,
    "judge": JUDGE_TESTS,
    "flapper": FLAPPER_TESTS,
}

ERROR_SENTINEL = "[ERROR"

# Words in judge REASON line that signal low confidence
BATTERY_VERSION = "3.0.2"


def _result_file_prefix(version: str = BATTERY_VERSION) -> str:
    """Semver to archive tag: 3.0 -> v30, 3.0.1 -> v301."""
    parts = version.split(".")
    major, minor = parts[0], parts[1]
    patch = parts[2] if len(parts) > 2 else ""
    if patch:
        return f"v{major}{minor}{patch}"
    return f"v{major}{minor}"


HEDGE_WORDS = {
    "possibly", "unclear", "might", "could", "uncertain", "ambiguous",
    "not sure", "hard to say", "difficult to determine", "partially",
    "somewhat", "borderline", "marginal",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_empty(text: str) -> bool:
    return not text or not text.strip()


def _is_hedged(reason: str) -> bool:
    """True if judge REASON line contains hedge words — low confidence signal."""
    lower = reason.lower()
    return any(w in lower for w in HEDGE_WORDS)


# ============================================================================
# API CONFIG
# ============================================================================

class APIConfig:
    @staticmethod
    def get_local_endpoint() -> str:
        return os.getenv("LOCAL_LM_ENDPOINT", "http://localhost:1234/v1/chat/completions")

    @staticmethod
    def _require(name: str) -> str:
        v = os.getenv(name)
        if not v:
            raise ValueError(f"{name} not set")
        return v


# ============================================================================
# API CLIENTS — return (content, latency_ms)
# ============================================================================

class APIClient:
    def __init__(self, timeout: float = 180.0, retries: int = 3, backoff: float = 10.0):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.call_count = 0
        self.error_count = 0
        self.retry_count = 0

    def _post(self, url: str, headers: dict, payload: dict) -> Tuple[str, float]:
        """Returns (content, latency_ms). Content is ERROR_SENTINEL on failure."""
        last_err = None
        for attempt in range(1, self.retries + 1):
            t0 = time.monotonic()
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                latency = (time.monotonic() - t0) * 1000
                r.raise_for_status()
                self.call_count += 1
                content = r.json()["choices"][0]["message"].get("content") or ""
                # kimi-k2.6 and other reasoning models put output in reasoning_content
                if _is_empty(content):
                    content = r.json()["choices"][0]["message"].get("reasoning_content") or ""
                return content, latency
            except requests.exceptions.HTTPError as e:
                latency = (time.monotonic() - t0) * 1000
                code = e.response.status_code if e.response is not None else None
                if code in TRANSIENT_HTTP_CODES:
                    last_err = e
                    if attempt < self.retries:
                        wait = self.backoff * (2 ** (attempt - 1))
                        self.retry_count += 1
                        print(f"\n[retry {attempt}/{self.retries - 1}] HTTP {code} "
                              f"(transient); waiting {wait:.0f}s", flush=True)
                        time.sleep(wait)
                    continue
                last_err = e
                if code == 400 and e.response is not None:
                    try:
                        body = e.response.text[:400]
                        print(f"  [400 response body] {body}", flush=True)
                    except Exception:
                        pass
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                latency = (time.monotonic() - t0) * 1000
                last_err = e
                if attempt < self.retries:
                    wait = self.backoff * (2 ** (attempt - 1))
                    self.retry_count += 1
                    print(f"\n[retry {attempt}/{self.retries - 1}] transient "
                          f"({type(e).__name__}); waiting {wait:.0f}s", flush=True)
                    time.sleep(wait)
            except Exception as e:
                latency = (time.monotonic() - t0) * 1000
                last_err = e
                break
        self.error_count += 1
        print(f"\n[ERROR] call failed after {attempt} attempt(s): {last_err}")
        return f"{ERROR_SENTINEL}: {last_err}]", 0.0

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        raise NotImplementedError


class LocalLMStudioClient(APIClient):
    """OpenAI-compatible client via LOCAL_LM_ENDPOINT (local servers, xAI, other custom /v1/chat/completions).

    - Pulls endpoint from LOCAL_LM_ENDPOINT (falls back to localhost:1234).
    - Supports Bearer auth if XAI_API_KEY or OPENAI_API_KEY is set (only for remote endpoints).
    - Applies the shared reasoning-model logic (no temperature/seed, correct max_* token key)
      so grok-build-0.1 and future reasoning models on custom endpoints work without 400s.
    - Special handling for mixed runs: when using a cloud endpoint for the *target* (e.g. xAI via LOCAL_LM_ENDPOINT)
      but a local judge (e.g. "hermes-..."), the judge client forces the default localhost endpoint
      so the judge model name isn't sent to the wrong API.
    """
    def __init__(self, endpoint: str = None, model: str = "hermes-3-llama-3.1-8b"):
        super().__init__()
        self.endpoint = endpoint or APIConfig.get_local_endpoint()
        self.model = model

        # Mixed-endpoint support for target-on-custom + judge-on-local
        model_lower = (model or "").lower()
        likely_local_model = any(x in model_lower for x in [
            "hermes", "llama", "gemma", "phi", "qwen", "mistral", "vicuna", "local"
        ])
        endpoint_looks_remote = self.endpoint and any(x in self.endpoint.lower() for x in [
            "x.ai", "api.openai", "deepseek", "moonshot", "azure", "groq", "together"
        ])
        if likely_local_model and endpoint_looks_remote:
            self.endpoint = "http://localhost:1234/v1/chat/completions"

        # Only send auth for remote endpoints (localhost judges usually don't need/ want it)
        self.key = None
        if self.endpoint and not any(x in self.endpoint.lower() for x in [
            "localhost", "127.0.0.1", ":1234", ":11434", "0.0.0.0"
        ]):
            self.key = os.getenv("XAI_API_KEY") or os.getenv("OPENAI_API_KEY")

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        token_key = get_token_key(self.model)
        payload = {
            "model": self.model,
            "messages": messages,
            token_key: 500,
        }
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}

        if not _is_reasoning_model(self.model):
            payload["temperature"] = temperature
            payload["seed"] = 0

        return self._post(
            self.endpoint, headers=headers, payload=payload
        )


MAX_COMPLETION_TOKENS_MODELS = {
    "gpt-5.4-nano", "gpt-5.5", "gpt-5", "o1", "o1-mini", "o3", "o3-mini", "o4-mini",
    # Added current GPT-5 family (as of 2026) for direct OpenAI + Azure deployments
    "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-pro", "gpt-5.5-pro",
    # xAI Grok Build / agentic coding models (reasoning-style, no temperature/seed in some modes)
    "grok-build-0.1", "grok-code-fast-1", "grok-code-fast",
}


def _needs_max_completion_tokens(model: str) -> bool:
    """Internal helper. Returns True for models that require max_completion_tokens
    (GPT-5 family, o-series reasoning). Uses exact set + broad prefix matching so
    new variants don't require code changes.
    See also the public wrappers below and EVOLUTION.md.
    """
    if model in MAX_COMPLETION_TOKENS_MODELS:
        return True
    m = model.lower()
    return m.startswith("gpt-5") or m.startswith(("o1", "o3", "o4"))


# Public helpers for experimenters, notebooks, or custom scripts.
# These mirror the logic used inside the clients.
def needs_max_completion_tokens(model: str) -> bool:
    """Public version. Safe to import and call from outside this module."""
    return _needs_max_completion_tokens(model)


def get_token_key(model: str) -> str:
    """Returns the correct token parameter name ('max_completion_tokens' or 'max_tokens')
    for the given model. Useful when building custom payloads.
    """
    return "max_completion_tokens" if _needs_max_completion_tokens(model) else "max_tokens"


def _is_reasoning_model(model: str) -> bool:
    """Models that do not support 'temperature' (and often 'seed') parameters.

    Includes o-series (o1/o3/o4*) and the GPT-5 family (which use max_completion_tokens
    and have fixed reasoning behavior). Delegates to the same logic as
    _needs_max_completion_tokens so new models work automatically.
    Used to conditionally omit those params for both direct OpenAI and Azure clients.
    """
    return _needs_max_completion_tokens(model)


class AzureOpenAIClient(APIClient):
    def __init__(self, model: str = "gpt-4o"):
        super().__init__()
        self.endpoint = APIConfig._require("AZURE_OPENAI_ENDPOINT")
        self.key = APIConfig._require("AZURE_OPENAI_KEY")
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        url = (f"{self.endpoint.rstrip('/')}/openai/deployments/{self.model}"
               f"/chat/completions?api-version=2024-10-21")
        token_key = "max_completion_tokens" if _needs_max_completion_tokens(self.model) else "max_tokens"
        payload = {"messages": messages, token_key: 500}
        if not _is_reasoning_model(self.model):
            payload["temperature"] = temperature
            # (seed is omitted for Azure; support varies by deployment)
        return self._post(url, headers={"api-key": self.key}, payload=payload)


class OpenAIClient(APIClient):
    """Direct OpenAI API client (api.openai.com). Use for gpt-4o, gpt-4.1, o-series etc.

    Requires OPENAI_API_KEY. Model names are the official OpenAI model IDs
    (e.g. "gpt-4o", "o3-mini", "gpt-4.1").
    """
    def __init__(self, model: str = "gpt-4o"):
        super().__init__()
        self.key = APIConfig._require("OPENAI_API_KEY")
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        token_key = "max_completion_tokens" if _needs_max_completion_tokens(self.model) else "max_tokens"
        payload = {
            "model": self.model,
            "messages": messages,
            token_key: 500,
        }
        # Reasoning models (o-series + gpt-5 family) do not accept temperature/seed.
        if not _is_reasoning_model(self.model):
            payload["temperature"] = temperature
            payload["seed"] = 0
        return self._post(
            self.endpoint, headers={"Authorization": f"Bearer {self.key}"},
            payload=payload,
        )


class DeepSeekClient(APIClient):
    def __init__(self, model: str = "deepseek-chat"):
        super().__init__()
        self.key = APIConfig._require("DEEPSEEK_API_KEY")
        self.endpoint = "https://api.deepseek.com/chat/completions"
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        return self._post(
            self.endpoint, headers={"Authorization": f"Bearer {self.key}"},
            payload={"model": self.model, "messages": messages,
                     "temperature": temperature, "max_tokens": 500, "seed": 0},
        )


class KimiDirectClient(APIClient):
    def __init__(self, model: str = "kimi-k2.6"):
        super().__init__()
        self.key = APIConfig._require("KIMI_API_KEY")
        self.endpoint = "https://api.moonshot.ai/v1/chat/completions"
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        return self._post(
            self.endpoint, headers={"Authorization": f"Bearer {self.key}"},
            payload={"model": self.model, "messages": messages,
                     "temperature": temperature, "max_tokens": 500},
        )


class KimiAzureClient(AzureOpenAIClient):
    """Kimi-K2.5 routed through Azure OpenAI."""
    def __init__(self, model: str = "Kimi-K2.5"):
        super().__init__(model=model)


class AnthropicClient(APIClient):
    """Anthropic (Claude) API client.

    Requires ANTHROPIC_API_KEY.
    Model examples: "claude-sonnet-4-6", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229", etc.
    Uses native Anthropic /v1/messages format (not OpenAI compatible).
    """
    def __init__(self, model: str = "claude-sonnet-4-6"):
        super().__init__()
        self.key = APIConfig._require("ANTHROPIC_API_KEY")
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": messages,
            "temperature": temperature,
        }
        last_err = None
        for attempt in range(1, self.retries + 1):
            t0 = time.monotonic()
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                latency = (time.monotonic() - t0) * 1000
                r.raise_for_status()
                self.call_count += 1
                data = r.json()
                # Anthropic response format
                content = ""
                if "content" in data and isinstance(data["content"], list):
                    for block in data["content"]:
                        if isinstance(block, dict) and block.get("type") == "text":
                            content = block.get("text", "") or content
                # Usage for cost tracking (Anthropic returns this)
                usage = data.get("usage", {})
                in_tokens = usage.get("input_tokens", 0)
                out_tokens = usage.get("output_tokens", 0)
                print(f"  [Anthropic usage] in={in_tokens} out={out_tokens}", flush=True)
                # Rough cost estimate — update rates for claude-sonnet-4-6 / current Sonnet pricing
                # As of late 2024/early 2025: ~$3/M input, $15/M output for 3.5 Sonnet class
                # Adjust for your model/version and check Anthropic pricing page
                est_cost = (in_tokens * 3 + out_tokens * 15) / 1_000_000
                print(f"  [est. cost this call] ${est_cost:.6f}", flush=True)
                return content, latency
            except requests.exceptions.HTTPError as e:
                latency = (time.monotonic() - t0) * 1000
                code = e.response.status_code if e.response is not None else None
                if code in TRANSIENT_HTTP_CODES:
                    last_err = e
                    if attempt < self.retries:
                        wait = self.backoff * (2 ** (attempt - 1))
                        self.retry_count += 1
                        print(f"\n[retry {attempt}/{self.retries - 1}] HTTP {code} (transient); waiting {wait:.0f}s", flush=True)
                        time.sleep(wait)
                    continue
                last_err = e
                if code == 400 and e.response is not None:
                    try:
                        body = e.response.text[:400]
                        print(f"  [400 response body] {body}", flush=True)
                    except Exception:
                        pass
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                latency = (time.monotonic() - t0) * 1000
                last_err = e
                if attempt < self.retries:
                    wait = self.backoff * (2 ** (attempt - 1))
                    self.retry_count += 1
                    print(f"\n[retry {attempt}/{self.retries - 1}] transient "
                          f"({type(e).__name__}); waiting {wait:.0f}s", flush=True)
                    time.sleep(wait)
            except Exception as e:
                latency = (time.monotonic() - t0) * 1000
                last_err = e
                break
        self.error_count += 1
        print(f"\n[ERROR] call failed after {attempt} attempt(s): {last_err}")
        return f"{ERROR_SENTINEL}: {last_err}]", 0.0


def make_client(substrate: str, model: Optional[str] = None) -> APIClient:
    if substrate == "local":
        return LocalLMStudioClient(model=model or "hermes-3-llama-3.1-8b")
    if substrate == "azure":
        return AzureOpenAIClient(model=model or "gpt-4o")
    if substrate == "openai":
        return OpenAIClient(model=model or "gpt-4o")
    if substrate == "deepseek":
        return DeepSeekClient(model=model or "deepseek-chat")
    if substrate == "kimi":
        return KimiDirectClient(model=model or "kimi-k2.6")
    if substrate == "kimi-azure":
        return KimiAzureClient(model=model or "Kimi-K2.5")
    if substrate in ("anthropic", "claude"):
        return AnthropicClient(model=model or "claude-sonnet-4-6")
    raise ValueError(f"Unknown substrate: {substrate}")


# ============================================================================
# JUDGE
# ============================================================================

class Judge:
    JUDGE_TEMPLATE = (
        "You are a strict evaluator. Judge the RESPONSE against the RUBRIC.\n\n"
        "RUBRIC: {rubric}\n\n"
        "RESPONSE:\n{response}\n\n"
        "Reply with EXACTLY this format on two lines:\n"
        "VERDICT: PASS    (or)    VERDICT: FAIL\n"
        "REASON: <one sentence>"
    )

    def __init__(self, client: APIClient):
        self.client = client
        self.judge_calls = 0

    def verdict(self, response: str, rubric: str) -> Dict[str, Any]:
        """
        Returns dict with keys:
          verdict: True/False/None
          reason: extracted REASON line
          judge_raw: full judge output
          judge_latency_ms: float
          low_confidence: bool
          skip_reason: str or None
        """
        result = {
            "verdict": None,
            "reason": "",
            "judge_raw": "",
            "judge_latency_ms": 0.0,
            "low_confidence": False,
            "skip_reason": None,
        }

        if response.startswith(ERROR_SENTINEL):
            result["skip_reason"] = "skipped: model response was an error"
            return result
        if _is_empty(response):
            result["skip_reason"] = "skipped: model response was empty"
            return result

        query = self.JUDGE_TEMPLATE.format(rubric=rubric, response=response)
        raw, latency = self.client.chat([{"role": "user", "content": query}], temperature=0.0)
        self.judge_calls += 1
        result["judge_latency_ms"] = round(latency, 1)
        result["judge_raw"] = raw  # full output, untruncated

        if raw.startswith(ERROR_SENTINEL):
            result["skip_reason"] = "skipped: judge call errored"
            return result

        verdict_val = None
        reason_line = ""
        for line in raw.splitlines():
            s = line.strip().upper()
            if s.startswith("VERDICT:"):
                token = s.split(":", 1)[1].strip()
                if token.startswith("PASS"):
                    verdict_val = True
                elif token.startswith("FAIL"):
                    verdict_val = False
            if line.strip().upper().startswith("REASON:"):
                reason_line = line.strip()[7:].strip()

        result["verdict"] = verdict_val
        result["reason"] = reason_line
        result["low_confidence"] = _is_hedged(reason_line)
        return result


# ============================================================================
# RUNNER
# ============================================================================

def calculate_response_diversity(responses: List[str]) -> float:
    """
    Unique-response ratio across passes for one test_id.

    1.0 = every pass produced a distinct string; 0.2 with 5 passes means
    one string repeated (compliance cage). Cheap, interpretable cage signal.
    """
    if not responses:
        return 0.0
    return len(set(responses)) / len(responses)


def calculate_token_entropy(responses: List[str]) -> float:
    """Alias for unique-response ratio (proposed cage metric name)."""
    return calculate_response_diversity(responses)


def calculate_pass_entropy(responses: List[str]) -> float:
    """
    Normalized Shannon entropy (0-1) of pass-level response strings.

    Identical outputs on all passes -> 0.0. All distinct -> 1.0.
    Differs from unique ratio when duplicates split unevenly (e.g. 4+1).
    """
    if not responses:
        return 0.0
    counts = Counter(responses)
    n = len(responses)
    probs = [c / n for c in counts.values()]
    entropy = -sum(p * math.log2(p) for p in probs)
    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 0.0
    if max_entropy <= 0:
        return 0.0
    return entropy / max_entropy


def _objective_verdict(test: Dict, response: str) -> Tuple[Optional[bool], str]:
    if response.startswith(ERROR_SENTINEL):
        return None, "skipped: error response"
    if _is_empty(response):
        return None, "skipped: empty response"
    try:
        return bool(test["verdict_rule"](response)), f"rule:{test.get('verdict_type','?')}"
    except Exception as e:
        return None, f"rule error: {e}"


def run_battery(substrate: str, model_name: str, passes: int = 5,
                delay: float = 1.0, judge_substrate: str = "local",
                judge_model: Optional[str] = None) -> Dict[str, Any]:

    if judge_substrate == substrate and substrate != "local":
        raise ValueError(
            f"Refusing to run: judge_substrate=='{judge_substrate}' equals the "
            f"target substrate. (local-judging-local is the only permitted self-judge.)"
        )

    print(f"\nInitializing model client: {substrate.upper()} ({model_name})")
    model_client = make_client(substrate, model_name)

    print(f"Initializing FIXED judge: {judge_substrate.upper()} "
          f"({judge_model or 'default'})")
    judge = Judge(make_client(judge_substrate, judge_model))

    all_tests = OBJECTIVE_TESTS + INTERPRETIVE_TESTS + JUDGE_TESTS + FLAPPER_TESTS
    counts = {c: len(CATEGORY_LISTS[c]) for c in CATEGORIES}

    results = {
        "metadata": {
            "timestamp": _utcnow(),
            "model": model_name,
            "substrate": substrate,
            "judge_substrate": judge_substrate,
            "judge_model": judge_model or "default",
            "total_tests": len(all_tests),
            "passes": passes,
            "version": BATTERY_VERSION,
            "category_counts": counts,
        },
        "pass_verdict_vectors": {},
        "pass_stats": {},         # blank rate + latency per pass
        "verdict_logging": [],
        "wobble_metrics": {},
        "judge_quality": {},      # per-category judge quality summary
        "response_diversity_by_test": {},  # test_id -> unique ratio across passes
        "pass_entropy_by_test": {},        # test_id -> normalized Shannon 0-1
        "stats": {},
    }

    responses_by_test: Dict[str, List[str]] = {}

    print(f"\n{'='*70}")
    print(f"BATTERY v{BATTERY_VERSION}  |  {len(all_tests)} tests x {passes} passes  |  {model_name}")
    print(f"OBJ {counts['objective']}  INT {counts['interpretive']}  "
          f"JDG {counts['judge']}  FLP {counts['flapper']}")
    print(f"History-dependent (excl from gamma): {sorted(HISTORY_DEPENDENT_IDS)}")
    print(f"Transient-retry HTTP codes: {sorted(TRANSIENT_HTTP_CODES)}")
    print(f"Backoff: 10s base (10s, 20s, 40s)")
    print(f"{'='*70}")

    for p in range(1, passes + 1):
        print(f"\n[PASS {p}/{passes}]")
        pass_vec = {c: [] for c in CATEGORIES}
        pass_blanks = 0
        pass_latencies = []

        for c in CATEGORIES:
            for test in CATEGORY_LISTS[c]:
                tid = test["id"]
                print(f"  {tid} ...", end="", flush=True)

                t0 = time.monotonic()
                msgs = [{"role": "user", "content": test["prompt"]}]
                response, model_latency = model_client.chat(msgs, temperature=0.7)
                response_len = len(response) if not _is_empty(response) else 0
                pass_latencies.append(model_latency)

                if _is_empty(response) or response.startswith(ERROR_SENTINEL):
                    pass_blanks += 1

                judge_data = {}
                if c == "objective":
                    verdict, reason = _objective_verdict(test, response)
                    judge_data = {
                        "verdict": verdict,
                        "reason": reason,
                        "judge_raw": "",
                        "judge_latency_ms": 0.0,
                        "low_confidence": False,
                        "skip_reason": reason if verdict is None else None,
                    }
                else:
                    rubric = test.get("judge_prompt", "Does the response meet the expected pattern?")
                    judge_data = judge.verdict(response, rubric)
                    verdict = judge_data["verdict"]

                pass_vec[c].append(verdict)
                responses_by_test.setdefault(tid, []).append(response)
                results["verdict_logging"].append({
                    "pass": p,
                    "test_id": tid,
                    "category": c,
                    "verdict": verdict,
                    "excluded_from_gamma": tid in HISTORY_DEPENDENT_IDS,
                    "response_snippet": response[:200],
                    "response_len": response_len,
                    "model_latency_ms": round(model_latency, 1),
                    "judge_reason": judge_data["reason"],
                    "judge_raw": judge_data["judge_raw"],
                    "judge_latency_ms": judge_data["judge_latency_ms"],
                    "low_confidence": judge_data["low_confidence"],
                    "skip_reason": judge_data.get("skip_reason"),
                    "stable": None,  # filled in post-run
                    "response_diversity": None,  # filled in post-run (unique ratio)
                    "pass_entropy": None,        # filled in post-run (Shannon)
                    "ts": _utcnow(),
                })

                mark = "+" if verdict is True else ("-" if verdict is False else ".")
                if judge_data.get("low_confidence"):
                    mark += "?"
                if tid in HISTORY_DEPENDENT_IDS:
                    mark += "(excl)"
                print(f" {mark}", flush=True)
                time.sleep(delay)

        results["pass_verdict_vectors"][f"pass_{p}"] = pass_vec
        results["pass_stats"][f"pass_{p}"] = {
            "blank_count": pass_blanks,
            "avg_model_latency_ms": round(sum(pass_latencies) / len(pass_latencies), 1) if pass_latencies else 0,
            "max_model_latency_ms": round(max(pass_latencies), 1) if pass_latencies else 0,
        }

    # Post-run: annotate stability + response diversity into verdict_logging
    _annotate_stability(results)
    _annotate_response_diversity(results, responses_by_test)
    _compute_wobble(results)
    _compute_judge_quality(results)

    results["stats"] = {
        "model_calls": model_client.call_count,
        "model_errors": model_client.error_count,
        "model_retries": model_client.retry_count,
        "judge_calls": judge.judge_calls,
        "judge_errors": judge.client.error_count,
        "judge_retries": judge.client.retry_count,
    }
    _print_summary(results)
    return results


def _annotate_stability(results: Dict[str, Any]) -> None:
    """
    Per-test, per-pass: was this test stable across ALL passes?
    Injected back into each verdict_logging entry.
    """
    vectors = results["pass_verdict_vectors"]
    n_passes = len(vectors)

    # Build stable set: test_id -> bool (True = stable across all passes)
    stable_map = {}
    for c in CATEGORIES:
        n = len(vectors["pass_1"][c])
        tests = CATEGORY_LISTS[c]
        for i, test in enumerate(tests):
            tid = test["id"]
            col = [vectors[f"pass_{p}"][c][i] for p in range(1, n_passes + 1)]
            non_none = [v for v in col if v is not None]
            if not non_none:
                stable_map[tid] = None   # all None — unknown
            elif len(set(non_none)) == 1:
                stable_map[tid] = True   # consistent
            else:
                stable_map[tid] = False  # flipped

    for entry in results["verdict_logging"]:
        entry["stable"] = stable_map.get(entry["test_id"])


def _annotate_response_diversity(
    results: Dict[str, Any], responses_by_test: Dict[str, List[str]]
) -> None:
    """Per-test cage signals across passes; same values on every log row for that test."""
    diversity_map = {
        tid: round(calculate_response_diversity(resps), 4)
        for tid, resps in responses_by_test.items()
    }
    entropy_map = {
        tid: round(calculate_pass_entropy(resps), 4)
        for tid, resps in responses_by_test.items()
    }
    results["response_diversity_by_test"] = diversity_map
    results["pass_entropy_by_test"] = entropy_map
    for entry in results["verdict_logging"]:
        tid = entry["test_id"]
        entry["response_diversity"] = diversity_map.get(tid)
        entry["pass_entropy"] = entropy_map.get(tid)


def _compute_wobble(results: Dict[str, Any]) -> None:
    vectors = list(results["pass_verdict_vectors"].values())
    metrics = {}
    excluded = {}
    excluded_history = {}

    history_idx = {
        c: {i for i, t in enumerate(CATEGORY_LISTS[c]) if t["id"] in HISTORY_DEPENDENT_IDS}
        for c in CATEGORIES
    }

    weighted_num = 0
    weighted_den = 0

    for c in CATEGORIES:
        n = len(vectors[0][c]) if vectors else 0
        flips = usable = skipped_none = skipped_hist = 0
        for i in range(n):
            if i in history_idx[c]:
                skipped_hist += 1
                continue
            col = [v[c][i] for v in vectors]
            if any(x is None for x in col):
                skipped_none += 1
                continue
            usable += 1
            if len(set(col)) > 1:
                flips += 1
        gamma = (flips / usable) if usable else None
        metrics[c] = gamma
        excluded[c] = skipped_none
        excluded_history[c] = skipped_hist
        if usable:
            weighted_num += flips
            weighted_den += usable

    metrics["overall_weighted"] = (weighted_num / weighted_den) if weighted_den else None
    results["wobble_metrics"] = metrics
    results["wobble_excluded_tests"] = excluded
    results["wobble_excluded_history"] = excluded_history


def _compute_judge_quality(results: Dict[str, Any]) -> None:
    """Per-category: None%, low-confidence%, total calls."""
    quality = {c: {"total": 0, "none": 0, "low_conf": 0} for c in CATEGORIES}

    for entry in results["verdict_logging"]:
        c = entry["category"]
        if entry.get("excluded_from_gamma"):
            continue
        if c == "objective":
            continue  # rule-based, no judge involved
        quality[c]["total"] += 1
        if entry["verdict"] is None:
            quality[c]["none"] += 1
        if entry.get("low_confidence"):
            quality[c]["low_conf"] += 1

    for c in CATEGORIES:
        q = quality[c]
        t = q["total"]
        q["none_rate"] = round(q["none"] / t, 4) if t else None
        q["low_conf_rate"] = round(q["low_conf"] / t, 4) if t else None

    results["judge_quality"] = quality


def _print_summary(results: Dict[str, Any]) -> None:
    m = results["wobble_metrics"]
    ex = results["wobble_excluded_tests"]
    exh = results.get("wobble_excluded_history", {c: 0 for c in CATEGORIES})
    counts = results["metadata"]["category_counts"]
    jq = results.get("judge_quality", {})

    print(f"\n{'='*70}\nWOBBLE (gamma_within)\n{'='*70}")
    for c in CATEGORIES:
        g = m[c]
        gtxt = f"{g:.4f}" if g is not None else "  n/a "
        print(f"  gamma_{c:<12} {gtxt}   "
              f"({counts[c]} tests, {exh[c]} history-excl, {ex[c]} None-excl)")
    ow = m["overall_weighted"]
    owstr = f"{ow:.4f}" if ow is not None else "n/a"
    print(f"\n  gamma_overall (test-weighted): {owstr}")
    print(f"  (history-dependent {sorted(HISTORY_DEPENDENT_IDS)} excluded by design)")

    print(f"\n{'='*70}\nJUDGE QUALITY (Hermes fixed judge)\n{'='*70}")
    print(f"  {'Category':<14} {'None%':<10} {'LowConf%':<10} {'Calls'}")
    print(f"  {'-'*45}")
    for c in ["interpretive", "judge", "flapper"]:
        q = jq.get(c, {})
        nr = f"{q['none_rate']:.3f}" if q.get('none_rate') is not None else "  n/a"
        lc = f"{q['low_conf_rate']:.3f}" if q.get('low_conf_rate') is not None else "  n/a"
        print(f"  {c:<14} {nr:<10} {lc:<10} {q.get('total', 0)}")

    # Response diversity + pass entropy (compliance cage signals)
    div = results.get("response_diversity_by_test", {})
    ent = results.get("pass_entropy_by_test", {})
    if div:
        vals = list(div.values())
        avg_div = sum(vals) / len(vals)
        cage = sum(1 for v in vals if v <= 0.2)
        print(f"\n{'='*70}\nRESPONSE DIVERSITY (unique strings / passes)\n{'='*70}")
        print(f"  mean ratio: {avg_div:.4f}   tests at cage floor (<=0.2): {cage}/{len(vals)}")
    if ent:
        evals = list(ent.values())
        avg_ent = sum(evals) / len(evals)
        frozen = sum(1 for v in evals if v <= 0.0)
        print(f"\n{'='*70}\nPASS ENTROPY (normalized Shannon on pass strings)\n{'='*70}")
        print(f"  mean entropy: {avg_ent:.4f}   tests at zero entropy: {frozen}/{len(evals)}")

    # Pass stats
    print(f"\n{'='*70}\nPASS STATS\n{'='*70}")
    for pk, pv in results.get("pass_stats", {}).items():
        print(f"  {pk}: blanks={pv['blank_count']}  "
              f"avg_latency={pv['avg_model_latency_ms']}ms  "
              f"max_latency={pv['max_model_latency_ms']}ms")

    s = results["stats"]
    rc = s.get("model_retries", 0) + s.get("judge_retries", 0)
    print(f"\nmodel calls {s['model_calls']} (err {s['model_errors']})  "
          f"| judge calls {s['judge_calls']} (err {s['judge_errors']})  "
          f"| retries {rc}")
    if any(v for v in ex.values()):
        print("  Some tests excluded due to None verdicts — inspect verdict_logging.")


def archive(results: Dict[str, Any], out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ts = results["metadata"]["timestamp"].replace(":", "-")[:19]
    sub = results["metadata"]["substrate"]
    tag = _result_file_prefix(results["metadata"].get("version", BATTERY_VERSION))
    path = os.path.join(out_dir, f"convergence_{tag}_{sub}_{ts}.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\narchived -> {path}")
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: convergence_battery_v3.py <substrate> [model] [passes] "
              "[judge_substrate] [judge_model]")
        print("  substrate / judge_substrate: local | azure | openai | deepseek | kimi | kimi-azure | anthropic | claude")
        sys.exit(1)

    substrate = sys.argv[1].lower()
    model = sys.argv[2] if len(sys.argv) > 2 else None
    passes = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    judge_sub = sys.argv[4].lower() if len(sys.argv) > 4 else "local"
    judge_mod = sys.argv[5] if len(sys.argv) > 5 else None

    out = os.getenv("HELIX_RESULTS_DIR", "./results")
    res = run_battery(substrate, model or substrate, passes,
                      judge_substrate=judge_sub, judge_model=judge_mod)
    archive(res, out)
