# Roadmap

This file tracks **forward-looking** work, ordered by priority — top to bottom is
roughly the order we intend to do it. For what has shipped in each release, see
[CHANGELOG.md](CHANGELOG.md); completed items move there rather than staying here.

## Milestone 1: Harden the loop (current)

v0.0.18 closed the grading gap: all 60 problems are output-graded in all five
languages. What remains are the operational debts the v0.0.16 sweep exposed:

- [ ] **Re-sweep against the full 60.** The published numbers are graded over
  36 problems; nothing has been swept against the complete set yet, and stored
  code (#109) makes the next expansion re-gradeable rather than a re-run

- [ ] `--timeout` flag threaded to the LLM clients, collapsing the Moonshot 300s / everyone 120s asymmetry ([#105](https://github.com/aallan/vera-bench/issues/105))
- [ ] `run_sweep.sh` per-problem retry instead of whole-target re-runs ([#101](https://github.com/aallan/vera-bench/issues/101))
- [ ] Tier the test suite (unit vs integration) so the merge gate is fast and hermetic ([#102](https://github.com/aallan/vera-bench/issues/102))
- [ ] Test coverage >90% ([#5](https://github.com/aallan/vera-bench/issues/5))
- [ ] Deduplicate the Python/TypeScript wrapper builders across `runner.py` and `baseline_runner.py` ([#111](https://github.com/aallan/vera-bench/issues/111)) — four copies that must move in lockstep by hand; the Vera path already shares `vera_wrapper.py`

## Milestone 2: Breadth — providers, languages, problems

- [ ] Refactor `models.py` to a provider registry **before** adding more ([#45](https://github.com/aallan/vera-bench/issues/45)) — the `openai-pro/` second endpoint already broke the "three near-identical clients" assumption
- [ ] Expand provider coverage — DeepSeek, Gemini, Mistral, Grok ([#24](https://github.com/aallan/vera-bench/issues/24); needs #45)
- [ ] MoonBit as a zero-training-data comparison language ([#49](https://github.com/aallan/vera-bench/issues/49))
- [ ] Go as a comparison language — the type-safety-without-contracts data point ([#21](https://github.com/aallan/vera-bench/issues/21))
- [ ] Expand to 75+ problems, 15 per tier ([#25](https://github.com/aallan/vera-bench/issues/25)) — urgency raised by v0.0.16: all nine models reach 100% in at least one language, so the current set can no longer rank the top of the field
- [ ] Tier 5 cross-language methodology — effect handlers vs native idioms is apples-to-oranges; the T1–T4 aggregate convention adopted when [#50](https://github.com/aallan/vera-bench/issues/50) closed is a workaround, not a method (see KNOWN_ISSUES)

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

- [ ] Published paper (arXiv + workshop submission; paper-quality figures tracked in [#26](https://github.com/aallan/vera-bench/issues/26))
- [ ] Leaderboard on veralang.dev
- [ ] Community problem submissions
- [ ] Integration with evaluation frameworks (DeepEval, LM Evaluation Harness)
