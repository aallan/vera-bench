# Roadmap

This file tracks **forward-looking** work, ordered by priority — top to bottom is
roughly the order we intend to do it. For what has shipped in each release, see
[CHANGELOG.md](CHANGELOG.md); completed items move there rather than staying here.

## Milestone 1: v0.0.16 publication (current)

Finishing the 8-model × 3-tier run against Vera 0.1.7 and publishing the results.

- [ ] **Run the sweep to 40/40 and publish** — headline chart, README results narrative, `% solved` tables, "model refused to answer" graph, 16:9 talk slides, tag v0.0.16
- [ ] `run_sweep.sh` per-problem retry instead of whole-target re-runs ([#101](https://github.com/aallan/vera-bench/issues/101))
- [ ] Tier the test suite (unit vs integration) so the merge gate is fast and hermetic ([#102](https://github.com/aallan/vera-bench/issues/102))

## Milestone 2: Breadth — providers, languages, problems

- [ ] Refactor `models.py` to a provider registry **before** adding more ([#45](https://github.com/aallan/vera-bench/issues/45)) — the `openai-pro/` second endpoint already broke the "three near-identical clients" assumption
- [ ] Expand provider coverage — DeepSeek, Gemini, Mistral, Grok ([#24](https://github.com/aallan/vera-bench/issues/24); needs #45)
- [ ] MoonBit as a zero-training-data comparison language ([#49](https://github.com/aallan/vera-bench/issues/49))
- [ ] Go as a comparison language — the type-safety-without-contracts data point ([#21](https://github.com/aallan/vera-bench/issues/21))
- [ ] Expand to 75+ problems, 15 per tier ([#25](https://github.com/aallan/vera-bench/issues/25))
- [ ] Tier 5 cross-language methodology — effect handlers vs native idioms is apples-to-oranges ([#50](https://github.com/aallan/vera-bench/issues/50))

## Milestone 3: Longitudinal tracking

- [ ] Pin SKILL.md version in results metadata; track results across vera compiler versions and model releases
- [ ] Automated scheduled benchmark runs ([#31](https://github.com/aallan/vera-bench/issues/31)) — the preflight gate and error accounting exist; needs matrix sharding (there is no resume) and a structured store
- [ ] Results dashboard ([#30](https://github.com/aallan/vera-bench/issues/30))
- [ ] Hugging Face dataset export ([#27](https://github.com/aallan/vera-bench/issues/27))

## Milestone 4: Advanced evaluation modes

- [ ] Multi-turn evaluation — N attempts with `check`/`verify` feedback each turn, extending fix@1 to fix@N ([#29](https://github.com/aallan/vera-bench/issues/29))
- [ ] Agentic evaluation — expose `vera check`/`verify`/`run` as callable tools the model drives itself ([#29](https://github.com/aallan/vera-bench/issues/29))
- [ ] Multi-file problems exercising the module system (Tier 5)

## Milestone 5: Community and ecosystem

- [ ] Published paper (arXiv + workshop submission)
- [ ] Leaderboard on veralang.dev
- [ ] Community problem submissions
- [ ] Integration with evaluation frameworks (DeepEval, LM Evaluation Harness)
