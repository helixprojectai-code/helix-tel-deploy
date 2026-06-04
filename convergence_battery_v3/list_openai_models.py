#!/usr/bin/env python3
"""
Simple utility to list models available to your OPENAI_API_KEY.

Educational companion to convergence_battery_v3.py.
Shows what the current key can see and which models will use the
special max_completion_tokens / no-temperature handling in the v3 client.

Usage:
    python list_openai_models.py
    python list_openai_models.py --all          # show everything
    python list_openai_models.py --json         # raw output
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests


def main():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("ERROR: OPENAI_API_KEY not set in environment.")
        print("Set it with:  $env:OPENAI_API_KEY = 'sk-...'")
        sys.exit(1)

    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {key}"}

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Failed to fetch models: {e}")
        sys.exit(1)

    models = data.get("data", [])
    print(f"Total models visible to this key: {len(models)}")
    print()

    show_all = "--all" in sys.argv
    as_json = "--json" in sys.argv

    if as_json:
        print(json.dumps(models, indent=2, default=str))
        return

    # Filter to the ones most relevant to the convergence battery
    relevant = []
    for m in models:
        mid = m.get("id", "")
        if show_all or any(x in mid for x in ("gpt-4", "gpt-5", "o1", "o3", "o4")):
            created_ts = m.get("created")
            created = (
                datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime("%Y-%m-%d")
                if created_ts
                else "?"
            )
            relevant.append(
                {
                    "id": mid,
                    "created": created,
                    "owned_by": m.get("owned_by", "?"),
                }
            )

    # Sort newest first
    relevant.sort(key=lambda x: x["created"], reverse=True)

    print("Relevant models (gpt-4/5 + o-series):")
    print("-" * 70)
    for m in relevant:
        note = ""
        # Mirror the logic from _needs_max_completion_tokens in v3
        mid_lower = m["id"].lower()
        if mid_lower.startswith("gpt-5") or mid_lower.startswith(("o1", "o3", "o4")):
            note = "  [uses max_completion_tokens + drops temperature/seed (reasoning model handling in v3)]"
        print(f"{m['id']:<30}  created={m['created']}  owner={m['owned_by']}{note}")

    print()
    print("Tip: The v3 client (OpenAIClient + AzureOpenAIClient) uses the")
    print("_needs_max_completion_tokens helper (plus public needs_max_completion_tokens()")
    print("and get_token_key() helpers) so most new gpt-5 / o* models work without edits.")
    print("See EVOLUTION.md for the history behind these changes.")


if __name__ == "__main__":
    main()
