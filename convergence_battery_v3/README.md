# TRACE Ops — Convergence Battery (v3)

Tools for running the TEL constitutional test battery against multiple LLM substrates to measure stability (wobble / γ metrics), judge quality, latency, and cross-model convergence.

**Current recommended script:** `convergence_battery_v3.py`

See also:
- [CONVERGENCE_BATTERY_RUNBOOK.md](./CONVERGENCE_BATTERY_RUNBOOK.md) — detailed metrics, interpretation, troubleshooting, and background
- [EVOLUTION.md](./EVOLUTION.md) — development history and design lessons (educational record)
- `compare_substrates_v3.py` — analyze results across runs
- `run_cloud_battery.sh` — helper for sequential cloud runs
- `list_openai_models.py` — query what models your OpenAI key can actually see

---

## Quick Start

```powershell
cd Z:\lattice_repo\TRACE\ops

# Example: run on direct OpenAI
python convergence_battery_v3.py openai gpt-4o
```

Results are written to `./results/` (or `$env:HELIX_RESULTS_DIR`).

---

## Command Line Reference (v3)

### Syntax
```powershell
python convergence_battery_v3.py <substrate> [model] [passes] [judge_substrate] [judge_model]
```

**Positional arguments:**
- `<substrate>` — required: `local | azure | openai | deepseek | kimi | kimi-azure`
- `[model]` — optional model or deployment name (defaults per substrate if omitted)
- `[passes]` — optional, default `5`
- `[judge_substrate]` — optional, default `local`
- `[judge_model]` — optional (only applies if judge_substrate is provided)

**Valid substrates** (usable for both the model under test and the judge):
- `local`
- `azure`
- `openai`
- `deepseek`
- `kimi`
- `kimi-azure`
- `anthropic` / `claude` (Anthropic Claude models)

### Minimal Runs (default model + 5 passes + local judge)
```powershell
python convergence_battery_v3.py local
python convergence_battery_v3.py azure
python convergence_battery_v3.py openai
python convergence_battery_v3.py deepseek
python convergence_battery_v3.py kimi
python convergence_battery_v3.py kimi-azure
```

### With Explicit Model
```powershell
python convergence_battery_v3.py local hermes-3-llama-3.1-8b
python convergence_battery_v3.py azure gpt-4o
python convergence_battery_v3.py azure gpt-5.4-nano
python convergence_battery_v3.py azure gpt-5.5
python convergence_battery_v3.py openai gpt-4o
python convergence_battery_v3.py openai gpt-4.1
python convergence_battery_v3.py openai gpt-5.5
python convergence_battery_v3.py openai o3-mini
python convergence_battery_v3.py openai o4-mini
python convergence_battery_v3.py deepseek deepseek-chat
python convergence_battery_v3.py kimi kimi-k2.6
python convergence_battery_v3.py kimi-azure "Kimi-K2.5"
python convergence_battery_v3.py anthropic claude-sonnet-4-6
python convergence_battery_v3.py claude "claude-3-5-sonnet-20241022"
```

### With Custom Passes
```powershell
python convergence_battery_v3.py openai gpt-4o 3
python convergence_battery_v3.py local hermes-3-llama-3.1-8b 10
python convergence_battery_v3.py deepseek deepseek-chat 7
```

### With Custom Judge (including cross-substrate)
Default judge is `local` (Hermes). You can run the model on one substrate and the judge on another.

**Recommended (cloud model + cheap local judge):**
```powershell
python convergence_battery_v3.py openai gpt-4o 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py azure gpt-4o 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py openai gpt-5.5 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py azure gpt-5.5 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py openai o3-mini 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py deepseek deepseek-chat 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py kimi kimi-k2.6 5 local hermes-3-llama-3.1-8b
```

**Bare judge substrate (uses its own default model):**
```powershell
python convergence_battery_v3.py openai gpt-4o 5 local
python convergence_battery_v3.py azure gpt-5.4-nano 5 local
python convergence_battery_v3.py openai gpt-5.5 5 local
```

**Using a cloud model as judge:**
```powershell
python convergence_battery_v3.py openai o3-mini 5 openai gpt-4o
python convergence_battery_v3.py deepseek 5 azure gpt-4o
python convergence_battery_v3.py azure gpt-4o 5 kimi kimi-k2.6
python convergence_battery_v3.py openai gpt-4.1 5 deepseek deepseek-chat
```

**Full 5-argument examples:**
```powershell
python convergence_battery_v3.py openai gpt-4o 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py kimi-azure "Kimi-K2.5" 3 azure gpt-4o
```

### Judge Rules
- You **cannot** use the same non-local substrate for both the model and the judge.
- Only `local` is permitted for self-judging.
- The code will raise an error if you try `openai ... 5 openai ...` (or equivalent for azure/deepseek/kimi).

---

## Environment Variables

Set these **before** running:

| Substrate     | Required Variables                              | Notes |
|---------------|--------------------------------------------------|-------|
| `local`       | `LOCAL_LM_ENDPOINT` (optional)                  | Defaults to `http://localhost:1234/v1/chat/completions` |
| `azure`       | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`     | `model` arg = your Azure **deployment name** |
| `openai`      | `OPENAI_API_KEY`                                | Use official model IDs (`gpt-4o`, `o3-mini`, etc.) |
| `deepseek`    | `DEEPSEEK_API_KEY`                              | Usually `deepseek-chat` |
| `kimi`        | `KIMI_API_KEY`                                  | Moonshot direct |
| `kimi-azure`  | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`     | `model` arg = Azure deployment name for Kimi |

Example:
```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:DEEPSEEK_API_KEY = "sk-..."
```

## Discovering Available Models

Before choosing a model for the next run, you can query exactly what your key has access to:

```powershell
$headers = @{ Authorization = "Bearer $env:OPENAI_API_KEY" }
$models = (Invoke-RestMethod -Uri "https://api.openai.com/v1/models" -Headers $headers).data

$models | Where-Object { $_.id -match '^(gpt-4|gpt-5|o[0-9])' } | 
  Select-Object id, @{n='created';e={[datetime]::UnixEpoch.AddSeconds($_.created).ToString('yyyy-MM-dd')}} |
  Sort-Object created -Descending | Format-Table -AutoSize
```

The v3 `OpenAIClient` (and Azure client) will automatically pick the correct `max_completion_tokens` vs `max_tokens` **and drop `temperature`/`seed`** for reasoning models (GPT-5 family + o-series) thanks to the `_needs_max_completion_tokens` / `_is_reasoning_model` helpers + expanded list. New variants like `gpt-5.5`, `gpt-5.5-pro`, future o* etc. work out of the box without code changes.

You can also import the public helpers from the v3 module for your own experiments:
```python
from convergence_battery_v3 import needs_max_completion_tokens, get_token_key
print(get_token_key("gpt-5.5"))      # 'max_completion_tokens'
print(needs_max_completion_tokens("o3-mini"))  # True
# (Internally, GPT-5 family and o-series also trigger temperature/seed omission via the same logic.)
```

There's also a small `list_openai_models.py` in this directory that does the same query in Python (easier to extend or run cross-platform).

---

## Results & Analysis

- Output directory: `./results/` or `$env:HELIX_RESULTS_DIR`
- Files: `convergence_v301_<substrate>_<timestamp>.json` (v3.0.1+); legacy `convergence_v30_*` (v3.0)
- Cross-run analysis:
  ```powershell
  python compare_substrates_v3.py results/convergence_v301_*.json
  # mixed with v3.0 runs:
  python compare_substrates_v3.py results/convergence_v30_*.json results/convergence_v301_*.json
  ```

---

## Other Scripts

- `run_cloud_battery.sh` — interactive helper for running multiple cloud substrates sequentially (includes a v3 openai section)
- `list_openai_models.py` — tiny standalone script to query exactly which models your `OPENAI_API_KEY` can see (filters to gpt/o-series by default). Run with `--all` or `--json`.
- Legacy versions (`convergence_battery_v2_*.py`, `convergence_battery_v2_wired.py`, `convergence_battery_v2_9.py`, etc.) are deliberately left unchanged in their original form. 

  This repository is intentionally educational: the collection of versioned files lets readers trace the actual development path (client abstractions, fixed-judge isolation, substrate support, retry logic, model parameter handling, etc.). Read the v2 files roughly in the order they were created to follow how the battery evolved to v3. v3 is the current recommended version for new experiments.

---

## More Information

For metrics explanation (γ_objective, γ_interpretive, judge quality, stability flags, etc.), full runbook, troubleshooting, and interpretation guidelines, see:

**[CONVERGENCE_BATTERY_RUNBOOK.md](./CONVERGENCE_BATTERY_RUNBOOK.md)**

For the broader TRACE / TEL context, see the `chronicle/` and `memory/` directories at the TRACE root.

## Evolution & Educational Notes

This collection of versioned scripts is intentionally kept as a development history. See [EVOLUTION.md](./EVOLUTION.md) for a guided tour of the major changes, design lessons, and why older v2 files were left untouched. It explains the progression from early clients through fixed-judge rules, retry logic, openai direct support, and the later model-parameter robustness work.