# Roadmap

## Where we are

**v0.0.3** — 50 problems across 5 tiers, working LLM harness (Anthropic + OpenAI), Python baseline runner, cross-language Python generation comparison. First results: Claude Sonnet 4 achieves 96% check@1, 96% verify@1, 83% run_correct in Vera; 92% run_correct in Python.

## Milestone 1: Publication-ready benchmark (current)

- [ ] Run against 5+ models (Claude Opus/Sonnet, GPT-4o, DeepSeek, Gemini)
- [ ] Run spec-from-NL mode comparison (issue #7)
- [ ] TypeScript baseline runner
- [ ] Generate paper-quality figures (matplotlib/seaborn in analysis/)
- [ ] Hugging Face dataset export
- [ ] CITATION.cff
- [ ] Expand to 75+ problems (15 per tier)
- [ ] Strengthen problem descriptions for slot ordering (issue #13)
- [ ] Strengthen postconditions to catch slot-swap bugs (issue #14)
- [ ] Improve SKILL.md coverage of where blocks (issue #15)
- [ ] Increase test coverage to >90% (issue #5)

## Milestone 2: Longitudinal tracking

- [ ] Pin SKILL.md version in results metadata
- [ ] Track results across vera compiler versions
- [ ] Track results across model releases
- [ ] Automated weekly/monthly benchmark runs via GitHub Actions scheduled workflow
- [ ] Results dashboard (GitHub Pages or similar)

## Milestone 3: Advanced evaluation modes

- [ ] spec-from-NL mode (agent writes contracts, not just implementation)
- [ ] Multi-turn agent evaluation (agent gets multiple attempts with error feedback)
- [ ] Agentic evaluation (agent uses vera check/verify as tools)
- [ ] Multi-file problems (Tier 5, testing module system)

## Milestone 4: Community and ecosystem

- [ ] Published paper (arXiv + workshop submission)
- [ ] Leaderboard on veralang.dev or GitHub Pages
- [ ] Community problem submissions
- [ ] Integration with evaluation frameworks (DeepEval, LM Evaluation Harness)
