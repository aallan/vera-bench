# Roadmap

## Where we are

**v0.0.5** — 50 problems across 5 tiers with strengthened postconditions and explicit slot ordering descriptions. Working LLM harness (Anthropic + OpenAI), Python and TypeScript baseline runners, cross-language generation comparison. SKILL.md fetched from veralang.dev at runtime.

## Milestone 1: Publication-ready benchmark (current)

- [ ] Run against 5+ models (Claude Opus/Sonnet, GPT-4o, DeepSeek, Gemini)
- [x] Run spec-from-NL mode comparison (issue #7)
- [x] TypeScript baseline runner and LLM generation
- [ ] Generate paper-quality figures (matplotlib/seaborn in analysis/)
- [ ] Hugging Face dataset export
- [ ] CITATION.cff
- [ ] Expand to 75+ problems (15 per tier)
- [x] Strengthen problem descriptions for slot ordering (issue #13)
- [x] Strengthen postconditions to catch slot-swap bugs (issue #14)
- [ ] Improve SKILL.md coverage of where blocks (issue #15)
- [ ] Increase test coverage to >90% (issue #5)

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
