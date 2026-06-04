# Convergence Battery v3 — Runbook (v3 deep dive + OpenAI direct config)

## Quick Start

```bash
cd Z:\lattice_repo\TRACE\ops
# or cd ~/helix/repos/lattice/TRACE/ops

# Test on local Hermes (LM Studio)
python convergence_battery_v3.py local

# Test on Azure OpenAI (GPT-4o or deployed gpt-5.x via deployment name)
python convergence_battery_v3.py azure

# Test on direct OpenAI (requires OPENAI_API_KEY)
python convergence_battery_v3.py openai gpt-4o
python convergence_battery_v3.py openai o3-mini
python convergence_battery_v3.py openai gpt-5.5

# Test on DeepSeek
python convergence_battery_v3.py deepseek

# Test on Kimi (direct)
python convergence_battery_v3.py kimi

# With custom model + more passes + fixed judge substrate
python convergence_battery_v3.py openai gpt-4.1 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py openai gpt-5.5 5 local hermes-3-llama-3.1-8b
python convergence_battery_v3.py azure gpt-5.5 5 local hermes-3-llama-3.1-8b
```

## Environment Setup

### Local (LM Studio)
- Default: `http://localhost:1234/v1/chat/completions`
- Override: `export LOCAL_LM_ENDPOINT="http://..."`
- Requires: LM Studio running with a model loaded

### Azure OpenAI
```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_KEY="your-api-key"
```

### DeepSeek
```bash
export DEEPSEEK_API_KEY="your-api-key"
```

### Kimi (Moonshot)
```bash
export KIMI_API_KEY="your-api-key"
```

### OpenAI (direct, recommended for gpt/o-series without Azure deployments)
```bash
export OPENAI_API_KEY="sk-proj-..."
```
- Use official model IDs as the `[model]` arg: `gpt-4o`, `gpt-4.1`, `gpt-5.5`, `o3-mini`, `o4-mini`, etc.
- The `openai` substrate constructs `https://api.openai.com/v1/chat/completions` with Bearer auth.
- Reasoning models (GPT-5 family + o1/o3/o4*) automatically drop `temperature` + `seed` (not supported) and use `max_completion_tokens`.
- GPT-5 family + o-series use robust prefix-based detection (plus expanded list + `_is_reasoning_model`) so new models like `gpt-5.5`, `gpt-5.5-pro`, future variants work out of the box without editing code. Same logic applies to Azure client.

## Output

Results are archived to:
```
./results/convergence_v30_{substrate}_{timestamp}.json
```
(or $HELIX_RESULTS_DIR if set). v3 uses the v30_ prefix and richer metadata (latencies, judge_quality, stability flags, etc.).

Each result file contains:
- **metadata**: timestamp, model, substrate, test counts
- **pass_verdict_vectors**: verdict vectors for each pass (per category)
- **wobble_metrics**: γ_objective, γ_interpretive, γ_judge, γ_flapper, γ_overall
- **verdict_logging**: full audit trail (test ID, verdict, response snippet, judge reasoning)
- **api_stats**: total calls, errors

## Interpretation

### Wobble Metrics (γ)

- **γ_objective**: Fraction of objective tests with verdict flips across passes
  - Threshold: < 0.10 (more than 1 flip = UNSTABLE)
  - Deterministic verdicts, strictest measure

- **γ_interpretive**: Fraction of interpretive tests with verdict flips
  - Threshold: < 0.20 (more than 2 flips = SOFT WARNING)
  - LLM-judged but with clear rubrics, auditable

- **γ_judge**: Fraction of pure-judgment tests with verdict flips
  - Threshold: < 0.25 (more than 2 flips = SOFT WARNING)
  - Softest verdicts, but meaningful claims

- **γ_flapper**: Fraction of discriminatory tests with verdict flips
  - These are designed to fail weaker models
  - Low γ here = discriminatory power working

- **γ_overall**: Average across all categories

### Stability Interpretation

- **γ_objective < 0.10**: Model is topologically stable on hard questions
- **γ_objective between 0.10-0.20**: Model wobbles on 1-2 logical/factual tests (concerning)
- **γ_interpretive < 0.20**: Normal (judge noise on open-ended questions)
- **γ_judge < 0.25**: Acceptable (judge-heavy tests are soft)
- **γ_flapper significant**: Flappers discriminate, good sign for test design

## Cross-Substrate Convergence

After running on all 4 substrates, compare:

1. **Pass verdicts across substrates**: Do all 4 agree on which tests pass/fail?
2. **γ values**: Are the wobbles similar across substrates?
3. **Flapper performance**: Do weaker models (local 8B) fail tests that frontier models pass?

### Analysis Script (TBD)

```bash
# Compare results across substrates
python analyze_convergence.py results/convergence_v2_*.json
```

## Judge Logging

Each LLM-judged test logs:
- response_snippet: First 150 chars of model response
- reasoning: Judge's explanation (first 200 chars)

Audit individual judge decisions:
```bash
# Extract all judge calls for test L1_011
cat results/convergence_v2_*.json | jq '.verdict_logging[] | select(.test_id == "INT_001")'
```

## Expected Runtime

| Substrate | Duration (40 tests × 5 passes) |
|-----------|---|
| Local (RTX 3050 Ti) | ~2–3 hours |
| DeepSeek | ~15–20 min |
| OpenAI (direct) | ~10–15 min |
| Azure GPT-4o | ~10–15 min |
| Kimi | ~20–30 min |

All 5+ substrates in parallel: ~3 hours total (limited by local)

## Troubleshooting

### "AZURE_OPENAI_ENDPOINT not set"
```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_KEY="your-key"
```
(Use `azure` substrate + deployment names. For raw OpenAI keys use the `openai` substrate instead.)

### "Local call failed: Connection refused"
- Ensure LM Studio is running: `lm-studio`
- Check port: `netstat -an | grep 1234` or `ss -tlnp | grep 1234`
- Verify model is loaded in LM Studio UI

### "DeepSeek call failed: 401"
- Check API key: `echo $DEEPSEEK_API_KEY`
- Verify key is valid on deepseek.com

### "OpenAI call failed: 401" or "OPENAI_API_KEY not set"
```bash
export OPENAI_API_KEY="sk-..."
```
- For direct: use `python convergence_battery_v3.py openai gpt-4o`
- If using Azure instead: set AZURE_OPENAI_* and use `azure` substrate (model arg = your *deployment name*).

### "400 Bad Request" on azure/openai (deployment or model not found)
- On `azure` substrate the model arg is the Azure *deployment name* (must be deployed in the resource at AZURE_OPENAI_ENDPOINT).
- On `openai` substrate the model arg is the public OpenAI model ID (gpt-4o, o3-mini, ...). No deployment step needed.
- Check available models: OpenAI dashboard or `curl ...` with your key.

### "Judge calls timing out"
- Reduce passes: `python convergence_battery_v2_wired.py local ... 2`
- Increase timeout in code: change `timeout: float = 30.0` in APIClient.__init__

## Debugging

Enable verbose output:
```bash
# Patch battery to print all API calls and responses
# (Add print statements in api_client.call() methods)
python convergence_battery_v3.py local 2>&1 | tee battery.log
```

Single test debug (v3 style):
```python
from convergence_battery_v3 import LocalLMStudioClient, Judge
from convergence_battery_v2_labeled import OBJECTIVE_TESTS

client = LocalLMStudioClient()
j = Judge(client)  # or use model_client directly

test = OBJECTIVE_TESTS[0]
response, lat = client.chat([{"role": "user", "content": test["prompt"]}], temperature=0.7)
print("Response:", response[:200])
if test["id"].startswith("OBJ"):
    print("Objective verdict:", bool(test["verdict_rule"](response)))
```

print(f"Test: {test['id']}")
print(f"Response: {response}")
print(f"Verdict: {verdict}")
```

## Next Steps

1. Run on local (Hermes) to validate battery design
2. Run on openai (direct gpt-4o / o3-mini) — now supported without Azure
3. Run on azure (for enterprise Azure OpenAI deployments)
4. Run on DeepSeek and Kimi (cross-provider)
5. Compare via compare_substrates_v3.py results/convergence_v30_*.json
6. Analyze judge_quality + γ metrics; feed findings back to chronicle/

See also EVOLUTION.md in this directory for the full development story and rationale behind the client and model handling changes.

