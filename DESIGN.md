# VeraBench: Design Document

This document explains why the benchmark exists, how it works, and why the decisions were made.

---

## What This Is

VeraBench is a HumanEval/MBPP-style benchmark adapted for Vera, a programming language designed for LLMs to write. The benchmark measures whether LLMs write better code in Vera than in existing languages — the core thesis of the entire Vera project.

The benchmark lives in its own repository (`aallan/vera-bench`), separate from the compiler (`aallan/vera`). It treats `vera` as a black-box CLI tool: `vera check`, `vera verify`, `vera run`. No compiler internals are imported.

### Why separate repos

- The benchmark is a **research artifact** with its own publication trajectory, citation, and versioning. "VeraBench v1.0 evaluated against vera v0.0.103" needs to be a clean sentence.
- The **software is structurally different**: the compiler is parse→typecheck→verify→compile; the benchmark is prompt→call-LLM-API→capture-output→run-vera-subprocess→collect-metrics.
- Different **dependency trees**: the benchmark needs LLM API clients (anthropic, openai, etc.), the compiler doesn't.
- Different **contributor profiles**: researchers running evaluations vs. people submitting compiler patches.

### Prior art

| Benchmark | Problems | Language | Task | Key metric |
|-----------|----------|----------|------|------------|
| **HumanEval** (OpenAI, 2021) | 164 | Python | Function completion from docstring | pass@k |
| **MBPP** (Google, 2021) | 974 | Python | Function from NL description + 3 tests | pass@1 |
| **DafnyBench** (Loughridge et al., 2024) | 782 | Dafny | Fill in verification annotations | success rate |
| **VerifyThisBench** (Deng et al., 2025) | ~150 | Dafny/Lean/Coq | End-to-end: spec + code + proof from NL | success rate |
| **CLEVER** (Thakur et al., 2025) | 161 | Lean | Spec equivalence + implementation correctness | pass@k-seconds |
| **VERINA** (Ye et al., 2025) | 189 | Lean | Spec + code + proof generation | pass@1 per subtask |

---

## The Five Difficulty Tiers

| Tier | Focus | What it tests |
|------|-------|--------------|
| 1 | Pure arithmetic | Basic syntax, `@T.n` slot references, simple contracts |
| 2 | String & array ops | Built-in function discovery (`domain_verb` naming) |
| 3 | ADTs & match | Data type definition, De Bruijn indices in match arms |
| 4 | Recursion & termination | `decreases` clauses, Z3 verification |
| 5 | Multi-function & effects | IO, State, Exn, effect propagation across functions |

---

## Metrics

For each problem × model combination:

- **check@1** — Does the first attempt pass `vera check`?
- **verify@1** — Does the best passing attempt pass `vera verify` with Tier 1 contracts? (If attempt 1 fails check but attempt 2 succeeds, verify is evaluated on attempt 2.)
- **fix@1** — Given the error message from a failed first attempt, can the model fix it in one turn?
- **run_correct** — Does the best passing attempt produce the correct output for all test cases?

Aggregate rates are computed per tier and overall. Cross-language baselines (Python, TypeScript) measure the same problems without Vera's contract system for comparison.

---

## Key Design Decisions

**Problem descriptions are natural language, not code stubs.** Unlike HumanEval (which gives a Python function signature + docstring), VeraBench gives a natural language description + the Vera function signature + optionally the contracts.

**Contracts can be provided or omitted.** For Tiers 1–2, provide the contracts in the prompt (full-spec mode). For Tiers 3–5, a spec-from-NL variant where the agent must also write the contracts.

**The SKILL.md is always provided.** Unlike benchmarks for well-known languages, Vera is not in any model's training data. The SKILL.md is the sole source of language knowledge.

**Retry with error feedback is a first-class metric.** Vera's error messages are designed to be agent-friendly (natural language, concrete fix suggestions). This is a competitive advantage worth measuring.

**Pin SKILL.md versions for reproducibility.** The `context/` directory stores SKILL.md snapshots. Different vera versions can be tested with different SKILL.md versions.

---

## What NOT to Do

- **Don't import vera compiler internals.** The benchmark should work with any version of `vera` that has the same CLI interface.
- **Don't make Tier 5 problems require network access.** Mock the `Http` and `Inference` effects.
- **Don't use problems from the vera examples/ or conformance/ directories.** Those are in the repo and therefore in training data. Write fresh problems.
- **Don't over-engineer.** Ship, get data, iterate.

---

## Links and References

- Vera repo: https://github.com/aallan/vera
- Vera language reference: https://veralang.dev/SKILL.md
- GitHub issue #225: https://github.com/aallan/vera/issues/225
- HumanEval: https://github.com/openai/human-eval
- MBPP: https://github.com/google-research/google-research/tree/master/mbpp
- DafnyBench: https://github.com/sun-wendy/DafnyBench (paper: arXiv:2406.08467)
