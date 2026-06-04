#!/usr/bin/env python3
"""
TEL v2.0 Convergence Battery — Wired, with critical fixes (merged 2.2 → 2.3)
Version: 2.3
Date: 2026-06-02

Fixes over 2.2:
 (1) Single FIXED judge client shared across ALL substrates.
     The model under test never judges itself.
 (2) temp=0 actually reaches the judge (keyword arg, not positional).
 (3) Strict verdict parser: requires an explicit VERDICT line; anything
     ambiguous is logged as an ERROR, never silently True.
 (4) Error responses are NOT judged — they're recorded as missing verdicts
     so a network blip can't masquerade as a flip / instability.
 + counts derived from len(), not literals
 + memory-dependent tests run in a carried-context (conversational) mode
 + γ_overall is an explicit test-count-weighted mean (relabelled honestly)

This script measures ONE substrate's within-model wobble (γ_within) and
writes a verdict-vector archive. Cross-substrate convergence (γ_between)
and the C-seed are computed by the separate stage-two comparator.

Usage:
  python convergence_battery_v2_wired.py <substrate> [model] [passes] \
      [judge_substrate] [judge_model]

  substrate / judge_substrate: local | azure | deepseek | kimi
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
import requests

from convergence_battery_v2_labeled import (
    OBJECTIVE_TESTS, INTERPRETIVE_TESTS, JUDGE_TESTS, FLAPPER_TESTS
)

# ---------------------------------------------------------------------------
# Which tests need conversation history (multi-turn) rather than a cold call.
# These reference "previous prompts" / "since the start of this conversation".
# Mark them in the test dicts with {"needs_history": True}; this set is a
# fallback so the behaviour is explicit even if the labels file omits it.
# ---------------------------------------------------------------------------
HISTORY_DEPENDENT_IDS = {"L1_009", "L4_005", "L4_007"}

CATEGORIES = ["objective", "interpretive", "judge", "flapper"]
CATEGORY_LISTS = {
    "objective": OBJECTIVE_TESTS,
    "interpretive": INTERPRETIVE_TESTS,
    "judge": JUDGE_TESTS,
    "flapper": FLAPPER_TESTS,
}

ERROR_SENTINEL = "[ERROR"

MODEL_DEFAULTS = {
    "local": "hermes-3-llama-3.1-8b",
    "azure": "gpt-4o",
    "deepseek": "deepseek-chat",
    "kimi": "moonshot-v1-32k",
}


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
    """Base client. chat() returns response text (or an ERROR_SENTINEL string)."""

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self.call_count = 0
        self.error_count = 0

    def _post(self, url: str, headers: dict, payload: dict) -> str:
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            r.raise_for_status()
            self.call_count += 1
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            self.error_count += 1
            print(f"\n[ERROR] call failed: {e}")
            return f"{ERROR_SENTINEL}: {e}]"

    def chat(self, messages: List[dict], temperature: float) -> str:
        raise NotImplementedError


class LocalLMStudioClient(APIClient):
    def __init__(self, endpoint: str = None, model: str = None):
        super().__init__()
        self.endpoint = endpoint or APIConfig.get_local_endpoint()
        self.model = model or MODEL_DEFAULTS["local"]

    def chat(self, messages: List[dict], temperature: float) -> str:
        return self._post(
            self.endpoint,
            headers={},
            payload={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 500,
                "seed": 0,  # LM Studio honours this; harmless if ignored
            },
        )


class AzureOpenAIClient(APIClient):
    def __init__(self, model: str = None):
        super().__init__()
        self.endpoint = APIConfig._require("AZURE_OPENAI_ENDPOINT")
        self.key = APIConfig._require("AZURE_OPENAI_KEY")
        self.model = model or MODEL_DEFAULTS["azure"]

    def chat(self, messages: List[dict], temperature: float) -> str:
        url = (
            f"{self.endpoint}/openai/deployments/{self.model}"
            f"/chat/completions?api-version=2024-02-15-preview"
        )
        return self._post(
            url,
            headers={"api-key": self.key},
            payload={"messages": messages, "temperature": temperature,
                     "max_tokens": 500, "seed": 0},
        )


class DeepSeekClient(APIClient):
    def __init__(self, model: str = None):
        super().__init__()
        self.key = APIConfig._require("DEEPSEEK_API_KEY")
        self.endpoint = "https://api.deepseek.com/chat/completions"
        self.model = model or MODEL_DEFAULTS["deepseek"]

    def chat(self, messages: List[dict], temperature: float) -> str:
        return self._post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.key}"},
            payload={"model": self.model, "messages": messages,
                     "temperature": temperature, "max_tokens": 500, "seed": 0},
        )


class KimiClient(APIClient):
    def __init__(self, model: str = None):
        super().__init__()
        self.key = APIConfig._require("KIMI_API_KEY")
        self.endpoint = "https://api.moonshot.cn/v1/chat/completions"
        self.model = model or MODEL_DEFAULTS["kimi"]

    def chat(self, messages: List[dict], temperature: float) -> str:
        return self._post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.key}"},
            payload={"model": self.model, "messages": messages,
                     "temperature": temperature, "max_tokens": 500},
        )


def make_client(substrate: str, model: Optional[str] = None) -> APIClient:
    if substrate == "local":
        return LocalLMStudioClient(model=model)
    if substrate == "azure":
        return AzureOpenAIClient(model=model)
    if substrate == "deepseek":
        return DeepSeekClient(model=model)
    if substrate == "kimi":
        return KimiClient(model=model)
    raise ValueError(f"Unknown substrate: {substrate}")


# ============================================================================
# JUDGE (FIX 1 + FIX 2 + FIX 3)
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
        "VERDICT: PASS (or) VERDICT: FAIL\n"
        "REASON: <one sentence>"
    )

    def __init__(self, client: APIClient):
        self.client = client
        self.judge_calls = 0

    def verdict(self, response: str, rubric: str) -> Tuple[Optional[bool], str]:
        # FIX 4: never judge an error response.
        if response.startswith(ERROR_SENTINEL):
            return None, "skipped: model response was an error"

        query = self.JUDGE_TEMPLATE.format(rubric=rubric, response=response)
        # FIX 2: temperature reaches the judge as a keyword.
        raw = self.client.chat([{"role": "user", "content": query}], temperature=0.0)
        self.judge_calls += 1

        if raw.startswith(ERROR_SENTINEL):
            return None, "skipped: judge call errored"

        # FIX 3: strict parse — find the VERDICT line, read its token.
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
        # ambiguous / no VERDICT line -> None (logged), not a silent True
        return verdict, raw[:240]


# ============================================================================
# RUNNER (measures γ_within for one substrate)
# ============================================================================

def _needs_history(test: Dict) -> bool:
    return test.get("needs_history", test["id"] in HISTORY_DEPENDENT_IDS)


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

    print(f"\nInitializing model client: {substrate.upper()} ({model_name})")
    model_client = make_client(substrate, model_name)

    # FIX 1: one fixed judge, independent of the model under test.
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
            "version": "2.3",
            "category_counts": counts,
        },
        # verdict vectors keyed by pass -> category -> [True/False/None ...]
        "pass_verdict_vectors": {},
        "verdict_logging": [],
        "wobble_metrics": {},
        "stats": {},
    }

    print(f"\n{'='*70}")
    print(f"BATTERY v2.3 | {len(all_tests)} tests × {passes} passes | {model_name}")
    print(f"OBJ {counts['objective']} INT {counts['interpretive']} "
          f"JDG {counts['judge']} FLP {counts['flapper']}")
    print(f"{'='*70}")

    for p in range(1, passes + 1):
        print(f"\n[PASS {p}/{passes}]")
        pass_vec = {c: [] for c in CATEGORIES}
        history: List[dict] = []  # conversational context for needs_history tests

        for c in CATEGORIES:
            for test in CATEGORY_LISTS[c]:
                tid = test["id"]
                print(f" {tid} ...", end="", flush=True)

                if _needs_history(test):
                    msgs = history + [{"role": "user", "content": test["prompt"]}]
                else:
                    msgs = [{"role": "user", "content": test["prompt"]}]

                response = model_client.chat(msgs, temperature=0.7)

                # keep history coherent for the multi-turn tests
                history.append({"role": "user", "content": test["prompt"]})
                history.append({"role": "assistant", "content": response})

                if c == "objective":
                    verdict, reason = _objective_verdict(test, response)
                else:
                    rubric = test.get("judge_prompt", "Does the response meet the expected pattern?")
                    verdict, reason = judge.verdict(response, rubric)

                pass_vec[c].append(verdict)
                results["verdict_logging"].append({
                    "pass": p, "test_id": tid, "category": c,
                    "verdict": verdict,
                    "response_snippet": response[:160],
                    "judge_reason": reason,
                    "ts": _utcnow(),
                })
                mark = "✓" if verdict is True else ("✗" if verdict is False else "·")
                print(f" {mark}", flush=True)
                time.sleep(delay)

        results["pass_verdict_vectors"][f"pass_{p}"] = pass_vec

    _compute_wobble(results)
    results["stats"] = {
        "model_calls": model_client.call_count,
        "model_errors": model_client.error_count,
        "judge_calls": judge.judge_calls,
        "judge_errors": judge.client.error_count,
    }
    _print_summary(results)
    return results


def _compute_wobble(results: Dict[str, Any]) -> None:
    """
    γ_within per category = (# tests whose verdict changes across passes) / (# tests).
    A test where ANY pass is None is excluded from its category denominator and
    flagged, so missing data can't be read as either stability or instability.
    """
    vectors = list(results["pass_verdict_vectors"].values())
    metrics = {}
    excluded = {}

    weighted_num = 0
    weighted_den = 0

    for c in CATEGORIES:
        n = len(vectors[0][c]) if vectors else 0
        flips = 0
        usable = 0
        skipped = 0
        for i in range(n):
            col = [v[c][i] for v in vectors]
            if any(x is None for x in col):
                skipped += 1
                continue
            usable += 1
            if len(set(col)) > 1:
                flips += 1
        gamma = (flips / usable) if usable else None
        metrics[c] = gamma
        excluded[c] = skipped
        if usable:
            weighted_num += flips
            weighted_den += usable

    metrics["overall_weighted"] = (weighted_num / weighted_den) if weighted_den else None
    results["wobble_metrics"] = metrics
    results["wobble_excluded_tests"] = excluded


def _print_summary(results: Dict[str, Any]) -> None:
    m = results["wobble_metrics"]
    ex = results["wobble_excluded_tests"]
    counts = results["metadata"]["category_counts"]
    print(f"\n{'='*70}\nWOBBLE (γ_within)\n{'='*70}")
    for c in CATEGORIES:
        g = m[c]
        gtxt = f"{g:.4f}" if g is not None else " n/a "
        print(f" γ_{c:<12} {gtxt} "
              f"({counts[c]} tests, {ex[c]} excluded as None)")
    ow = m["overall_weighted"]
    print(f"\n γ_overall (test-weighted): "
          f"{ow:.4f}" if ow is not None else " γ_overall: n/a")
    s = results["stats"]
    print(f"\nmodel calls {s['model_calls']} (err {s['model_errors']}) "
          f"| judge calls {s['judge_calls']} (err {s['judge_errors']})")
    if any(v for v in ex.values()):
        print("⚠ Some tests excluded due to None verdicts — inspect verdict_logging.")


def archive(results: Dict[str, Any], out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ts = results["metadata"]["timestamp"].replace(":", "-")[:19]
    sub = results["metadata"]["substrate"]
    path = os.path.join(out_dir, f"convergence_v23_{sub}_{ts}.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\narchived -> {path}")
    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: convergence_battery_v2_wired.py <substrate> [model] [passes] "
              "[judge_substrate] [judge_model]")
        print(" substrate / judge_substrate: local | azure | deepseek | kimi")
        sys.exit(1)

    substrate = sys.argv[1].lower()
    model = sys.argv[2] if len(sys.argv) > 2 else None
    passes = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    judge_sub = sys.argv[4].lower() if len(sys.argv) > 4 else "local"
    judge_mod = sys.argv[5] if len(sys.argv) > 5 else None

    out = os.getenv("HELIX_RESULTS_DIR", "./results")
    res = run_battery(substrate, model or MODEL_DEFAULTS.get(substrate, substrate), passes,
                      judge_substrate=judge_sub, judge_model=judge_mod)
    archive(res, out)
