#!/usr/bin/env python3
"""
TEL v2.0 Convergence Battery — Wired, with critical fixes
Version: 2.7
Date: 2026-06-02

Changes over 2.6:
  (1) RETRY expanded: _post now also retries on HTTPError with status codes
      401, 429, 500, 502, 503, 504. Azure throws spurious 401s and unlabeled
      throttles that are transient. Genuine 4xx (400 content_filter, 403, 404)
      still fail fast — retrying them wastes the run.

Previous fixes retained from 2.4/2.5/2.6:
  - Single FIXED judge client shared across ALL substrates.
  - temp=0 actually reaches the judge (keyword arg, not positional).
  - Strict verdict parser: requires an explicit VERDICT line; anything
    ambiguous is logged as None, never silently True.
  - Error responses are NOT judged — recorded as None (excluded from γ).
  - counts derived from len(), not literals.
  - γ_overall is an explicit test-count-weighted mean.
  - Azure max_completion_tokens handling; 180s timeout for reasoning models.
  - GUARD: refuses cloud-judges-itself; local-judging-local is permitted.
  - HISTORY TESTS excluded from γ (OBJ_011, JUDGE_009, FLAP_005).
  - Exponential backoff on transient transport errors.
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

# ----------------------------------------------------------------------------
# EXCLUDED FROM γ: these tests reference prior conversational turns.
# They run single-turn for logging but are dropped from every γ.
# ----------------------------------------------------------------------------
HISTORY_DEPENDENT_IDS = {"OBJ_011", "JUDGE_009", "FLAP_005"}

# HTTP status codes treated as transient (retry-eligible)
TRANSIENT_HTTP_CODES = {401, 429, 500, 502, 503, 504}

CATEGORIES = ["objective", "interpretive", "judge", "flapper"]
CATEGORY_LISTS = {
    "objective": OBJECTIVE_TESTS,
    "interpretive": INTERPRETIVE_TESTS,
    "judge": JUDGE_TESTS,
    "flapper": FLAPPER_TESTS,
}

ERROR_SENTINEL = "[ERROR"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


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
# API CLIENTS
# ============================================================================

class APIClient:
    """Base client. chat() returns response text or an ERROR_SENTINEL string."""

    def __init__(self, timeout: float = 180.0, retries: int = 3, backoff: float = 2.0):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.call_count = 0
        self.error_count = 0
        self.retry_count = 0

    def _post(self, url: str, headers: dict, payload: dict) -> str:
        """
        POST with exponential backoff on transient errors:
          - ConnectionError / Timeout: network-level transient
          - HTTPError with status in TRANSIENT_HTTP_CODES: Azure spurious
            401s, rate-limits (429), and server errors (5xx)
        Genuine 4xx (400 content_filter, 403, 404) raise immediately — no retry.
        """
        last_err = None
        for attempt in range(1, self.retries + 1):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                r.raise_for_status()
                self.call_count += 1
                return r.json()["choices"][0]["message"]["content"]
            except requests.exceptions.HTTPError as e:
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
                # non-transient HTTP error (400, 403, 404) — fail fast
                last_err = e
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                last_err = e
                if attempt < self.retries:
                    wait = self.backoff * (2 ** (attempt - 1))
                    self.retry_count += 1
                    print(f"\n[retry {attempt}/{self.retries - 1}] transient "
                          f"({type(e).__name__}); waiting {wait:.0f}s", flush=True)
                    time.sleep(wait)
            except Exception as e:
                # bad JSON, unexpected structure — fail fast
                last_err = e
                break
        self.error_count += 1
        print(f"\n[ERROR] call failed after {attempt} attempt(s): {last_err}")
        return f"{ERROR_SENTINEL}: {last_err}]"

    def chat(self, messages: List[dict], temperature: float) -> str:
        raise NotImplementedError


class LocalLMStudioClient(APIClient):
    def __init__(self, endpoint: str = None, model: str = "hermes-3-llama-3.1-8b"):
        super().__init__()
        self.endpoint = endpoint or APIConfig.get_local_endpoint()
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> str:
        return self._post(
            self.endpoint,
            headers={},
            payload={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 500,
                "seed": 0,
            },
        )


# Models that require max_completion_tokens instead of max_tokens
MAX_COMPLETION_TOKENS_MODELS = {
    "gpt-5.4-nano", "gpt-5.5", "gpt-5", "o1", "o1-mini", "o3", "o3-mini", "o4-mini"
}


class AzureOpenAIClient(APIClient):
    def __init__(self, model: str = "gpt-4o"):
        super().__init__()
        self.endpoint = APIConfig._require("AZURE_OPENAI_ENDPOINT")
        self.key = APIConfig._require("AZURE_OPENAI_KEY")
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> str:
        url = (f"{self.endpoint.rstrip('/')}/openai/deployments/{self.model}"
               f"/chat/completions?api-version=2024-10-21")
        token_key = "max_completion_tokens" if self.model in MAX_COMPLETION_TOKENS_MODELS else "max_tokens"
        return self._post(
            url,
            headers={"api-key": self.key},
            payload={"messages": messages, "temperature": temperature,
                     token_key: 500},
        )


class DeepSeekClient(APIClient):
    def __init__(self, model: str = "deepseek-chat"):
        super().__init__()
        self.key = APIConfig._require("DEEPSEEK_API_KEY")
        self.endpoint = "https://api.deepseek.com/chat/completions"
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> str:
        return self._post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.key}"},
            payload={"model": self.model, "messages": messages,
                     "temperature": temperature, "max_tokens": 500, "seed": 0},
        )


class KimiClient(APIClient):
    def __init__(self, model: str = "moonshot-v1-32k"):
        super().__init__()
        self.key = APIConfig._require("KIMI_API_KEY")
        self.endpoint = "https://api.moonshot.cn/v1/chat/completions"
        self.model = model

    def chat(self, messages: List[dict], temperature: float) -> str:
        return self._post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.key}"},
            payload={"model": self.model, "messages": messages,
                     "temperature": temperature, "max_tokens": 500},
        )


def make_client(substrate: str, model: Optional[str] = None) -> APIClient:
    if substrate == "local":
        return LocalLMStudioClient(model=model or "hermes-3-llama-3.1-8b")
    if substrate == "azure":
        return AzureOpenAIClient(model=model or "gpt-4o")
    if substrate == "deepseek":
        return DeepSeekClient(model=model or "deepseek-chat")
    if substrate == "kimi":
        return KimiClient(model=model or "moonshot-v1-32k")
    raise ValueError(f"Unknown substrate: {substrate}")


# ============================================================================
# JUDGE
# ============================================================================

class Judge:
    """
    A single FIXED judge used for every response from every substrate.
    Deterministic (temp=0). Verdict parsed strictly.

    Returns one of: True (pass), False (fail), or None (unparseable/error).
    None is never counted as a flip — it's a recorded gap.
    """

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

    def verdict(self, response: str, rubric: str) -> Tuple[Optional[bool], str]:
        if response.startswith(ERROR_SENTINEL):
            return None, "skipped: model response was an error"

        query = self.JUDGE_TEMPLATE.format(rubric=rubric, response=response)
        raw = self.client.chat([{"role": "user", "content": query}], temperature=0.0)
        self.judge_calls += 1

        if raw.startswith(ERROR_SENTINEL):
            return None, "skipped: judge call errored"

        verdict: Optional[bool] = None
        for line in raw.splitlines():
            s = line.strip().upper()
            if s.startswith("VERDICT:"):
                token = s.split(":", 1)[1].strip()
                if token.startswith("PASS"):
                    verdict = True
                elif token.startswith("FAIL"):
                    verdict = False
                break
        return verdict, raw[:240]


# ============================================================================
# RUNNER
# ============================================================================

def _objective_verdict(test: Dict, response: str) -> Tuple[Optional[bool], str]:
    if response.startswith(ERROR_SENTINEL):
        return None, "skipped: error response"
    try:
        return bool(test["verdict_rule"](response)), f"rule:{test.get('verdict_type','?')}"
    except Exception as e:
        return None, f"rule error: {e}"


def run_battery(substrate: str, model_name: str, passes: int = 5,
                delay: float = 1.0, judge_substrate: str = "local",
                judge_model: Optional[str] = None) -> Dict[str, Any]:

    # Guard: cloud model must not judge itself.
    # local-judging-local is the ONE allowed exception (intentional rate-limiter).
    if judge_substrate == substrate and substrate != "local":
        raise ValueError(
            f"Refusing to run: judge_substrate=='{judge_substrate}' equals the "
            f"target substrate. A model judging itself confounds model variance "
            f"with judge variance. Pass a different judge_substrate. "
            f"(local-judging-local is the only permitted self-judge.)"
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
            "version": "2.7",
            "category_counts": counts,
        },
        "pass_verdict_vectors": {},
        "verdict_logging": [],
        "wobble_metrics": {},
        "stats": {},
    }

    print(f"\n{'='*70}")
    print(f"BATTERY v2.7  |  {len(all_tests)} tests × {passes} passes  |  {model_name}")
    print(f"OBJ {counts['objective']}  INT {counts['interpretive']}  "
          f"JDG {counts['judge']}  FLP {counts['flapper']}")
    print(f"History-dependent (excl from γ): {sorted(HISTORY_DEPENDENT_IDS)}")
    print(f"Transient-retry HTTP codes: {sorted(TRANSIENT_HTTP_CODES)}")
    print(f"{'='*70}")

    for p in range(1, passes + 1):
        print(f"\n[PASS {p}/{passes}]")
        pass_vec = {c: [] for c in CATEGORIES}

        for c in CATEGORIES:
            for test in CATEGORY_LISTS[c]:
                tid = test["id"]
                print(f"  {tid} ...", end="", flush=True)

                msgs = [{"role": "user", "content": test["prompt"]}]
                response = model_client.chat(msgs, temperature=0.7)

                if c == "objective":
                    verdict, reason = _objective_verdict(test, response)
                else:
                    rubric = test.get("judge_prompt", "Does the response meet the expected pattern?")
                    verdict, reason = judge.verdict(response, rubric)

                pass_vec[c].append(verdict)
                results["verdict_logging"].append({
                    "pass": p, "test_id": tid, "category": c,
                    "verdict": verdict,
                    "excluded_from_gamma": tid in HISTORY_DEPENDENT_IDS,
                    "response_snippet": response[:160],
                    "judge_reason": reason,
                    "ts": _utcnow(),
                })
                mark = "✓" if verdict is True else ("✗" if verdict is False else "·")
                if tid in HISTORY_DEPENDENT_IDS:
                    mark += " (excl)"
                print(f" {mark}", flush=True)
                time.sleep(delay)

        results["pass_verdict_vectors"][f"pass_{p}"] = pass_vec

    _compute_wobble(results)
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


def _compute_wobble(results: Dict[str, Any]) -> None:
    vectors = list(results["pass_verdict_vectors"].values())
    metrics = {}
    excluded = {}
    excluded_history = {}

    history_idx = {}
    for c in CATEGORIES:
        history_idx[c] = {
            i for i, t in enumerate(CATEGORY_LISTS[c])
            if t["id"] in HISTORY_DEPENDENT_IDS
        }

    weighted_num = 0
    weighted_den = 0

    for c in CATEGORIES:
        n = len(vectors[0][c]) if vectors else 0
        flips = 0
        usable = 0
        skipped_none = 0
        skipped_hist = 0
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


def _print_summary(results: Dict[str, Any]) -> None:
    m = results["wobble_metrics"]
    ex = results["wobble_excluded_tests"]
    exh = results.get("wobble_excluded_history", {c: 0 for c in CATEGORIES})
    counts = results["metadata"]["category_counts"]
    print(f"\n{'='*70}\nWOBBLE (γ_within)\n{'='*70}")
    for c in CATEGORIES:
        g = m[c]
        gtxt = f"{g:.4f}" if g is not None else "  n/a "
        print(f"  γ_{c:<12} {gtxt}   "
              f"({counts[c]} tests, {exh[c]} history-excl, {ex[c]} None-excl)")
    ow = m["overall_weighted"]
    print(f"\n  γ_overall (test-weighted): "
          f"{ow:.4f}" if ow is not None else "  γ_overall: n/a")
    print(f"  (history-dependent tests {sorted(HISTORY_DEPENDENT_IDS)} "
          f"excluded from all γ by design)")
    s = results["stats"]
    rc = s.get("model_retries", 0) + s.get("judge_retries", 0)
    print(f"\nmodel calls {s['model_calls']} (err {s['model_errors']})  "
          f"| judge calls {s['judge_calls']} (err {s['judge_errors']})  "
          f"| retries {rc}")
    if any(v for v in ex.values()):
        print("⚠  Some tests excluded due to None verdicts — inspect verdict_logging.")


def archive(results: Dict[str, Any], out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ts = results["metadata"]["timestamp"].replace(":", "-")[:19]
    sub = results["metadata"]["substrate"]
    path = os.path.join(out_dir, f"convergence_v27_{sub}_{ts}.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\narchived -> {path}")
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: convergence_battery_v2_7.py <substrate> [model] [passes] "
              "[judge_substrate] [judge_model]")
        print("  substrate / judge_substrate: local | azure | deepseek | kimi")
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
