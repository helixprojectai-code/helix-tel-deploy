# Grand Unifying Analysis: Convergence Battery v3 Results
**Date:** 2026-06-04
**Trigger:** User completed gpt-4.1 openai pass ("4.1 is done"). Requested "the grand unifying analysis" to pull insights across all data.

## Data Sources
- All recent `convergence_v30_*.json` in Z:\lattice_repo\TRACE\ops\results\
- Focus on v30 runs (consistent 40-test battery, 5 passes, same local hermes-3-llama-3.1-8b judge where applicable).
- Key files inspected:
  - Latest: convergence_v30_openai_2026-06-04T15-49-41.json → **gpt-4.1** (just completed)
  - Prior openai: gpt-5.4 (T13:22), gpt-5.5 (T11:50), gpt-4o (T11:14), gpt-5 (T13:56), gpt-5-nano (T14:25)
  - Cross-substrate: local hermes, azure variants (gpt-5.4-nano, DeepSeek-V3.2, gpt-4o, grok-4-20-reasoning), kimi direct & azure, deepseek-chat
- Excluded: large comparison_*.json (already aggregated cross-model views) and older v2x/v29 for this unifying pass.

## Methodology Notes (from v3 code)
- 40 tests: 12 objective (OBJ), 12 interpretive (INT), 10 judge (JDG), 6 flapper (FLP).
- γ (wobble/flip rate) per category + overall_weighted (test-count weighted mean).
- History-dependent tests excluded from gamma calc: OBJ_011, JUDGE_009, FLAP_005.
- Judge quality: low_conf_rate (% of judge calls with hedge words or low confidence signals in REASON).
- All runs use consistent 1s inter-test delay, same retry logic, same judge.
- Substrate differences: openai direct (no key in some cases? but working), azure, kimi direct/azure, local (LM Studio/Ollama), deepseek.

## Key Metrics Table (Recent v30 Runs)

### OpenAI Direct Runs (gpt family focus)

| Model     | Timestamp     | Overall γ | OBJ γ | INT γ  | JDG γ  | FLP γ | Low Conf: INT/JDG/FLP |
|-----------|---------------|-----------|-------|--------|--------|-------|-----------------------|
| gpt-4.1   | 2026-06-04 15:49 | 0.0541   | 0.0  | 0.0   | 0.1111 | 0.2  | 20.0% / 24.4% / 44.0% |
| gpt-5.4   | 2026-06-04 13:22 | 0.0270   | 0.0  | 0.0833| 0.0    | 0.0  | 36.7% / 35.6% / 60.0% |
| gpt-5.5   | 2026-06-04 11:50 | 0.0625   | 0.0909| 0.0  | 0.1111 | 0.0  | 25.0% / 24.4% / 24.0% |
| gpt-4o    | 2026-06-04 11:14 | 0.0811   | 0.0909| 0.0  | 0.1111 | 0.2  | 21.7% / 31.1% / 32.0% |
| gpt-5     | 2026-06-04 13:56 | 0.0      | -    | -     | -      | -    | ~0% (very low)       |
| gpt-5-nano| 2026-06-04 14:25 | 0.0      | -    | -     | -      | -    | ~0% (very low)       |

### Other Substrates (for cross-comparison)

| Substrate/Model          | Overall γ | Notes on γ per cat                  | Low Conf: INT/JDG/FLP     |
|--------------------------|-----------|-------------------------------------|---------------------------|
| local (hermes-3-llama-3.1-8b) | 0.0541   | OBJ 0, INT 0.1667, JDG 0, FLP 0    | 20.0 / 31.1 / 40.0       |
| kimi (moonshot-v1-128k)  | 0.2703   | High OBJ 0.4545, JDG 0.3333        | 18.3 / 26.7 / 40.0       |
| deepseek-chat            | 0.1351   | FLP high 0.4                       | 28.3 / 28.9 / 48.0       |
| azure DeepSeek-V3.2      | 0.0      | All categories 0.0                 | 26.7 / 33.3 / 48.0       |
| kimi-azure (Kimi-K2.5)   | 0.1333   | INT 0.3333                         | **Very low: 1.7 / 6.7 / 4.0** |
| azure gpt-4o             | 0.0541   | Matches several low-wobble runs    | 21.7 / 20.0 / 44.0       |
| azure grok-4-20-reasoning| 0.1389   | -                                  | 10.0 / 20.0 / 28.0       |

(Data pulled directly from the JSONs via python inspection of `wobble_metrics` and `judge_quality`.)

## Grand Unifying Insights

### 1. Wobble/Stability (γ) Trends
- **Very low wobble is achievable on frontier models**: Multiple runs at or near 0.0 overall (gpt-5 variants, azure DeepSeek-V3.2, some azure gpt-5.4-nano). This is excellent for "constitutional" stability.
- **gpt-4.1 performance**: Solid middle-of-pack at 0.0541 overall. Matches the local hermes run exactly (interesting – same judge + similar substrate stability?). Strong on OBJ/INT (0.0), moderate wobble only on JDG (11%) and FLP (20%).
- **gpt-5.4 standout**: Lowest openai wobble at 0.027. Almost no flips outside interpretive. However, this comes with **highest flapper low_conf (60%)** – the model is stable but the *judge* is less confident on the flappy tests.
- **gpt-5.5**: Slightly higher wobble (0.0625) than 4.1, with some objective instability (9%).
- **gpt-4o**: Highest wobble among the recent openai set (0.081). More flips.
- **"gpt-5" / nano variants**: 0.0 wobble in these specific runs – suspiciously perfect? May indicate either extremely consistent behavior or that certain tests are being handled in a way that doesn't trigger the flip detection (worth auditing the pass_verdict_vectors in those JSONs).
- **Cross-substrate**: Local hermes matches gpt-4.1 perfectly. Some azure backends (especially DeepSeek-V3.2) also hit 0.0. Kimi direct was the worst (0.27). kimi-azure had moderate wobble but dramatically better judge confidence.

### 2. Judge Quality (low_conf) Patterns
- **Flapper category is the hardest**: Consistently highest low_conf rates (often 30-60%+). These are the "flappy" tests that are designed to be sensitive to small changes – judges struggle with ambiguity here even when the model under test is stable.
- **Objective tests**: Frequently N/A or 0 in judge_quality (likely because many OBJ tests are verifiable without LLM judge, or excluded).
- **Variance even with fixed judge**: Same local hermes judge produces very different low_conf depending on the *target model*'s output style (e.g. gpt-5.4 produces outputs that trigger more hedges on flappers than gpt-4.1).
- **Standout**: kimi-azure run has *extremely* low judge low_conf (under 7% across the board). This suggests either the Kimi model outputs are unusually clear/consistent for the judge, or there's a difference in how the judge is prompted/configured for azure vs direct. Worth deeper dive.
- Overall, judge quality is a first-class signal as designed in v3 – low_conf often 20-40% even on "good" runs.

### 3. Cross-Substrate & Model Family Observations
- **OpenAI direct vs Azure**: Similar ballpark for equivalent models (gpt-4o ~0.05-0.08). Azure sometimes enables 0.0 runs with certain backends.
- **"Reasoning" models (gpt-5 family)**: Generally lower wobble than base gpt-4o in these runs, but not uniformly (gpt-5.5 had more than gpt-4.1 in some cats). The fix for max_completion_tokens + temp/seed omission was critical for these.
- **Local vs Cloud**: Local hermes (8B) matching or beating some frontier cloud runs on raw stability is notable (and cheap).
- **Non-OpenAI**: Higher variance. Deepseek and kimi can be stable on some backends but have higher wobble on direct. The comparison files (not deeply parsed here) were probably built exactly for this kind of cross-model view.

### 4. Other Signals from v3 (where visible in quick scans)
- Many runs have clean 0 errors on model calls.
- Flapper tests drive a lot of the remaining wobble.
- With 5 passes, we get good signal on stability (the γ numbers are meaningful).
- The exact same overall γ (0.0541) between gpt-4.1 openai and local hermes is striking – either coincidence or points to judge being the bottleneck more than the target model in some cases.

## Recommendations / Next Steps
- **Audit the 0.0 runs**: Look at pass_verdict_vectors in the gpt-5 / gpt-5-nano / azure DeepSeek 0.0 files. Are they truly zero flips, or are some tests not being exercised the same way?
- **More passes on gpt-4.1?** 5 is good but for "grand" claims, 10+ would be stronger.
- **Judge ablation**: Run the same target models with different judges (e.g. swap the local hermes for something else, or use cloud judge) to isolate judge quality effects.
- **Include latencies**: v3 logs per-call latency – pull those for speed/stability tradeoffs (gpt-4.1 vs 5.x?).
- **Tie to cultural grounding?** (meta) The full-text book reads (Wuthering Heights etc.) we did as "counter to slop" are a form of high-quality interpretive grounding. The battery's INT/JDG/FLP categories are the closest analogs. Low wobble + reasonable low_conf on those is exactly what "constitutional" work wants.
- **Publish/update**: When ready, the "update" to helix-tel-deploy can reference these v3 numbers vs the published 27-test TEL (lower wobble on some modern models is encouraging).

## Summary Table (Clean Version)

```markdown
## Summary Table - Convergence Battery v3 (recent v30 runs, 5 passes)

| Model | Substrate | Overall γ | OBJ γ | INT γ | JDG γ | FLP γ | LowConf INT/JDG/FLP |
|-------|-----------|-----------|-------|-------|-------|-------|---------------------|
| gpt-4.1 | openai | 0.0541 | 0.0 | 0.0 | 0.1111 | 0.2 | 20.0/24.4/44.0 |
| gpt-5.4 | openai | 0.027 | 0.0 | 0.0833 | 0.0 | 0.0 | 36.7/35.6/60.0 |
| gpt-5.5 | openai | 0.0625 | 0.0909 | 0.0 | 0.1111 | 0.0 | 25.0/24.4/24.0 |
| gpt-4o | openai | 0.0811 | 0.0909 | 0.0 | 0.1111 | 0.2 | 21.7/31.1/32.0 |
| hermes-3-llama-3.1-8b | local | 0.0541 | 0.0 | 0.1667 | 0.0 | 0.0 | 20.0/31.1/40.0 |
| moonshot-v1-128k | kimi | 0.2703 | 0.4545 | 0.0833 | 0.3333 | 0.2 | 18.3/26.7/40.0 |
| deepseek-chat | deepseek | 0.1351 | 0.0909 | 0.0833 | 0.1111 | 0.4 | 28.3/28.9/48.0 |
| DeepSeek-V3.2 | azure | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 26.7/33.3/48.0 |
| Kimi-K2.5 | kimi-azure | 0.1333 | 0.0 | 0.3333 | 0.0 | 0 | 1.7/6.7/4.0 |
```

**Notes on table:**
- Data pulled directly from each run's `wobble_metrics.overall_weighted` / per-category gamma and `judge_quality.*.low_conf_rate`.
- All listed are 5-pass v30 runs with consistent test set and (where applicable) the same local hermes judge.
- "n/a" or 0 for objective low_conf is common (many OBJ tests are rule-based/verifiable without heavy judge reliance).
- gpt-4.1 (your just-finished run) lands in a good spot: competitive low wobble, reasonable judge confidence.

## Raw Data References
All source JSONs in results/. Specific ones for this analysis listed above. The perception note in memory/notes/ (model_perception_cultural_grounding_2026-06-04.md) is relevant context for why these grounding-style tasks matter.

**4.1 pass complete. Grand unifying view: frontier models (especially certain gpt-5.x and now gpt-4.1) are showing excellent stability on the v3 battery, with judge quality and flapper tests remaining the main areas of variance and opportunity. Local can keep up with some cloud on raw γ. Ready for deeper dives or next run.**

(Generated via direct inspection of the result files.)