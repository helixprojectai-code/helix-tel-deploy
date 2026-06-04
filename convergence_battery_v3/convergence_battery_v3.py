#!/usr/bin/env python3
"""
TEL Convergence Battery
Version: 3.0
Date: 2026-06-03 (client robustness updates later)

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
import os
import time
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
    def __init__(self, endpoint: str = None, model: str = "hermes-3-llama-3.1-8b"):
        super().__init__()
        self.endpoint = endpoint or APIConfig.get_local_endpoint()
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> Tuple[str, float]:
        return self._post(
            self.endpoint, headers={},
            payload={"model": self.model, "messages": messages,
                     "temperature": temperature, "max_tokens": 500, "seed": 0},
        )


MAX_COMPLETION_TOKENS_MODELS = {
    "gpt-5.4-nano", "gpt-5.5", "gpt-5", "o1", "o1-mini", "o3", "o3-mini", "o4-mini",
    # Added current GPT-5 family (as of 2026) for direct OpenAI + Azure deployments
    "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-pro", "gpt-5.5-pro",
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
            "version": "3.0",
            "category_counts": counts,
        },
        "pass_verdict_vectors": {},
        "pass_stats": {},         # blank rate + latency per pass
        "verdict_logging": [],
        "wobble_metrics": {},
        "judge_quality": {},      # per-category judge quality summary
        "stats": {},
    }

    print(f"\n{'='*70}")
    print(f"BATTERY v3.0  |  {len(all_tests)} tests x {passes} passes  |  {model_name}")
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

    # Post-run: annotate stability into verdict_logging
    _annotate_stability(results)
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
    path = os.path.join(out_dir, f"convergence_v30_{sub}_{ts}.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\narchived -> {path}")
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: convergence_battery_v3.py <substrate> [model] [passes] "
              "[judge_substrate] [judge_model]")
        print("  substrate / judge_substrate: local | azure | openai | deepseek | kimi | kimi-azure")
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
