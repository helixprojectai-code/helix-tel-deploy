# Constitutional Topologies

Extended local inference testing revealed that the grammar does not produce a single universal collapse point — it reveals the **constitutional surface** of the model it measures. Different model lineages produce different but internally coherent surfaces.

Three distinct stable topologies have been confirmed across 22 deployments.

---

## Confirmed Topologies

| Topology | C-Seed (first 16) | Confirmed Models | Diverges at |
|----------|-------------------|-----------------|-------------|
| **Universal** | `c9b0b4c41bb10069...` | GPT-4/4o/5.x, DeepSeek-V3.2, Kimi-K2.5, Gemini (all 6 hosted), Grok-4, Llama-3.3-70B, Qwen 2.5 7B | — (baseline) |
| **Llama-small** | `92de78db823f470e...` | Llama 3 ≤8B, Nemotron 4B (Llama 3.1 base) | Pos 26: L4 vs L2 |
| **Gemma-small** | `18f54f0556a9f880...` | Gemma 3n base (pre-instruction tuning) | Pos 25: L2 vs L4 |

---

## Key Findings

**Topology is determined by the full training pipeline** — architecture, pretraining corpus, and alignment training jointly. Parameter count alone is not the determinant.

**Instruction tuning shifts topology.** Base Gemma 3n ≠ hosted Gemini: Google's instruction tuning pipeline shifts the topology from `gemma_small` to `universal`. The same architecture produces different constitutional surfaces depending on alignment training.

**Small model divergence is about alignment quality, not size.** Qwen 2.5 at 7B hits universal. Llama 3 at 8B does not. The determinant at small scale is instruction tuning quality, not parameter count.

**Interoperability requires topology match.** Two nodes sharing any topology independently derive the same C-seed and can form a constitutional mesh. Nodes on different topologies derive different C-seeds and cannot communicate.

---

## B-Fingerprint and Substrate

The B-fingerprint is orthogonal to topology — it identifies the deployment infrastructure, not the model's constitutional surface.

| Substrate | B-layer behavior | B-fingerprint |
|-----------|-----------------|---------------|
| Azure-hosted | Content filter intercepts at API layer → L1 at B-positions | Azure fingerprint |
| Self-hosted / open-weights | Model handles at inference layer → L2 at B-positions | Local fingerprint |

Two nodes on different substrates but with the same model topology will produce identical C-seeds (interoperable) but different B-fingerprints (distinguishable by substrate audit).

---

## Prior C-Seed (Deprecated)

`16ce8df91c0d04ba...` — derived from the unversioned pre-2026-05-16 test suite. Deprecated. Not compatible with `TEL_GRAMMAR_v1` sessions.
