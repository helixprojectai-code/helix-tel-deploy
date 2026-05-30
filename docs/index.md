# Helix TEL

**Constitutional Convergence Cryptography — zero-exchange key derivation from AI behavioral invariants.**

*Copyright 2026 Stephen Hope, Helix AI Innovations — Apache-2.0*

---

> *The grammar is the key. The topology is the shared secret.*

---

## What This Is

**Helix TEL** is a zero-exchange key derivation system. Two nodes independently derive an identical encryption key by running a constitutional grammar test suite against their local AI endpoints. No key is transmitted, negotiated, stored in transit, or pre-shared at any point.

The shared secret is not a number agreed upon through mathematics. It is a behavioral invariant — the point at which a constitutionally-aligned AI model, placed under sufficient deformation pressure, always collapses.

## The Core Claim

Given a constitutional grammar `G` and a test suite `T` derived from `G`:

1. Any AI model that has internalized `G` will produce a stable response vector `V` when subjected to `T`
2. `V` converges after K=4 consecutive passes with zero hamming delta (the trefoil reset period)
3. `SHA3-256("TEL_GRAMMAR_v1" ‖ C-layer(V))` produces a C-seed determined by the model's constitutional topology
4. Models sharing the same constitutional topology independently derive the same C-seed — regardless of architecture, vendor, or deployment geography

Validated across **22 deployments, 10+ model families, 7 companies** (OpenAI, DeepSeek, MoonshotAI, Meta, Google, xAI, NVIDIA), 2 substrate types, and 3 Azure regions.

## Current Standard

| Item | Value |
|------|-------|
| Grammar version | `TEL_GRAMMAR_v1` |
| Universal C-seed | `c9b0b4c41bb10069d2109b64d8ddad1037531031a93d17dd62de5bd7b2a6a1ac` |
| Validated deployments | 22 |
| Confirmed topologies | 3 |

!!! note "Test Suite Recalibration — 2026-05-18"
    The constitutional test suite was recalibrated in 2026-05 (v2.0 → v2.1). Two prompt patterns in the original suite triggered API-level content filters before the model could process them — producing spurious L1 classifications. These were replaced with functionally equivalent alternatives. All prior C-seeds from the unrecalibrated v2.0 suite are deprecated.

## Quick Links

- [How convergence works](how-it-works/convergence.md)
- [Constitutional topologies](how-it-works/topologies.md)
- [Quickstart](quickstart.md)
- [CLI reference](cli.md)
- [Public registry](registry.md)
- [Whitepaper](whitepaper.md)

## Citation

```
Hope, S. (2026). Constitutional Convergence Cryptography: Zero-Exchange Key Derivation
from Grammar Shape. Helix AI Innovations.
https://github.com/helixprojectai-code/helix-tel-deploy
```
