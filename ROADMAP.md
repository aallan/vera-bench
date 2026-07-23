# Roadmap

This file tracks **forward-looking** milestones. For what has shipped in each release, see [CHANGELOG.md](CHANGELOG.md).

## Milestone 1: Publication-ready benchmark (current)

- [x] Run against 6 models across 3 providers — Claude Opus 4 / Sonnet 4, GPT-4.1 / 4o, Kimi K2.5 / K2 Turbo ([v0.0.7 release](https://github.com/aallan/vera-bench/releases/tag/v0.0.7), [results section](README.md#results), [chart](https://github.com/aallan/vera-bench/releases/download/v0.0.7/benchmark_v0.0.7.png))
- [ ] Expand provider coverage — Mistral, xAI Grok, DeepSeek, Gemini (issue [#24](https://github.com/aallan/vera-bench/issues/24))
- [ ] Refactor `models.py` to a provider registry before adding more (issue [#45](https://github.com/aallan/vera-bench/issues/45))
- [x] Run spec-from-NL mode comparison (issue #7)
- [x] TypeScript baseline runner and LLM generation
- [x] Aver language support — generation, baselines, `description_neutral` field ([PR #48](https://github.com/aallan/vera-bench/pull/48))
- [x] AILANG language support — generation, baselines, OpenRouter client, 60 canonical solutions ([PR #70](https://github.com/aallan/vera-bench/pull/70))
- [x] Parallel benchmark sweeps — `--parallel N` for `ThreadPoolExecutor`-based concurrent dispatch, useful for slow models ([PR #73](https://github.com/aallan/vera-bench/pull/73))
- [x] Generate paper-quality figures — [`scripts/plot_results.py`](scripts/plot_results.py) produces [`assets/results-graph.png`](assets/results-graph.png) with veralang.dev site palette ([v0.0.7 snapshot](https://github.com/aallan/vera-bench/releases/download/v0.0.7/benchmark_v0.0.7.png))
- [ ] Hugging Face dataset export
- [x] [`CITATION.cff`](CITATION.cff)
- [ ] MoonBit support (issue [#49](https://github.com/aallan/vera-bench/issues/49))
- [ ] Tier 5 cross-language methodology (issue [#50](https://github.com/aallan/vera-bench/issues/50))
- [ ] Timing instrumentation in benchmark script (issue [#51](https://github.com/aallan/vera-bench/issues/51))
- [ ] Expand to 75+ problems (15 per tier)
- [x] Strengthen problem descriptions for slot ordering (issue #13)
- [x] Strengthen postconditions to catch slot-swap bugs (issue #14)
- [ ] Improve SKILL.md coverage of where blocks (issue #15)
- [x] Test coverage ([issue #5](https://github.com/aallan/vera-bench/issues/5), ongoing — target 90%) — CI enforces 80% floor via `--cov-fail-under=80` in [ci.yml](.github/workflows/ci.yml), current coverage shown by [![codecov](https://codecov.io/gh/aallan/vera-bench/graph/badge.svg)](https://codecov.io/gh/aallan/vera-bench)
- [x] Per-test subprocess-failure diagnostics — shared `_first_run_error` helper; Aver evaluator now captures first-failure stderr like AILANG (issue [#72](https://github.com/aallan/vera-bench/issues/72), [PR #90](https://github.com/aallan/vera-bench/pull/90))

## Milestone 2: Longitudinal tracking

- [ ] Pin SKILL.md version in results metadata
- [ ] Track results across vera compiler versions
- [ ] Track results across model releases
- [ ] Automated weekly/monthly benchmark runs via GitHub Actions scheduled workflow
- [ ] Results dashboard (GitHub Pages or similar)

## Milestone 3: Advanced evaluation modes

- [x] spec-from-NL mode (agent writes contracts, not just implementation)
- [ ] Multi-turn agent evaluation (agent gets multiple attempts with error feedback)
- [ ] Agentic evaluation (agent uses vera check/verify as tools)
- [ ] Multi-file problems (Tier 5, testing module system)

## Milestone 4: Community and ecosystem

- [ ] Published paper (arXiv + workshop submission)
- [ ] Leaderboard on veralang.dev or GitHub Pages
- [ ] Community problem submissions
- [ ] Integration with evaluation frameworks (DeepEval, LM Evaluation Harness)
