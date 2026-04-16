# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.9] - 2026-04-16

### Added

- Report shows separate "All Tiers (T1–T5)" and "Comparable (T1–T4)" summary
  sections for cross-language comparison (#50)
- `exclude_tiers` parameter on `compute_metrics()` for tier-filtered aggregation
- Methodology note explaining why T5 is reported separately
- 10 new problems: 5 Tier 2 (VB-T2-011 through VB-T2-015) and 5 Tier 3
  (VB-T3-011 through VB-T3-015), bringing total to 60 problems across 5 tiers
- Test cases for VB-T2-004 (is_empty_string) and VB-T2-005 (contains_substring)
- All new problems have testable signatures (primitive inputs/outputs) so
  `run_correct` can be evaluated via `vera run --fn`
- New T3 problems use Int-only signatures with internal ADT construction,
  testing pattern matching without requiring ADT CLI argument support
- Canonical solutions for all new problems in Vera, Python, TypeScript, and Aver

### Changed

- Comparable section is suppressed when no T1–T4 problems are present

## [0.0.8] - 2026-04-13

### Added

- Aver language support: generation, checking, execution, and fix-from-error
- `description_neutral` field on all 50 problem JSONs for language-neutral prompts
- Aver baseline runner (`vera-bench baselines --language aver`)

### Changed

- Python and TypeScript prompts now use `description_neutral` instead of
  Vera-flavoured `description`. This improves fairness for non-Vera languages
  but means results are not directly comparable to v0.0.7 runs which used
  Vera-specific descriptions.
- README: added Aver as a comparison language, updated CLI examples
- CLAUDE.md: added `description_neutral` documentation, comparison language guide, Aver section, Tier 5 caveat
- DESIGN.md: added `description_neutral` rationale, zero-training-data comparison languages, Tier 5 methodology note
- CONTRIBUTING.md: added "Adding a New Comparison Language" guide with step-by-step checklist
- ROADMAP.md: added Aver milestone, MoonBit (#49), Tier 5 methodology (#50), timing (#51) items

## [0.0.7] - 2026-04-07

### Added

- Moonshot (Kimi) provider support — OpenAI-compatible API via `moonshot/*` model prefix
- `MoonshotClient` in models.py using `api.moonshot.ai/v1` base URL
- `scripts/run_full_benchmark.py` — run all 6 benchmark targets with one command
  (interactive mode with provider/model/key menus, or autonomous via CLI args)
- Secure API key input via `getpass` in interactive mode

## [0.0.6] - 2026-03-30

### Added

- Bench and vera compiler versions in JSONL filenames and result records (#20)
- `VeraRunner.version()` method to query vera compiler version
- 52 new tests across 4 new test files (test_cli.py, test_models.py,
  test_validate_integration.py, test_vera_runner_integration.py)
  plus expanded existing tests

### Changed

- CI coverage threshold raised from 35% to 80%
- Test coverage: 66% → 83% (324 → 376 tests)

## [0.0.5] - 2026-03-30

### Changed

- Strengthened problem descriptions for De Bruijn slot ordering (issue #13):
  VB-T4-002 (GCD), VB-T4-004 (power), VB-T5-003 (safe_div) now explicitly
  state which `@Type.N` maps to which parameter in the description text
- Strengthened postconditions to catch logic bugs (issue #14):
  - VB-T4-002 (GCD): added `@Nat.result <= @Nat.1 || @Nat.0 > 0`
  - VB-T4-005 (sum_to_n): added `@Nat.result >= @Nat.0`
  - VB-T4-008 (multiply): added `@Nat.result == @Nat.1 * @Nat.0`
  - VB-T4-010 (div_natural): added `@Nat.result * @Nat.0 <= @Nat.1`
  - VB-T5-001 (counter): `true` → `@Int.result == 3`
  - VB-T5-006 (state_double): `true` → `@Int.result == @Int.0 * 2`
  - VB-T5-009 (state_max): `true` → `@Int.result == @Nat.0`
- SKILL.md now fetched from veralang.dev at runtime (no local cache)

## [0.0.4] - 2026-03-30

### Added

- TypeScript baseline runner (`vera-bench baselines --language typescript`)
- TypeScript LLM generation (`vera-bench run --model MODEL --language typescript`)
- TypeScript prompt builder with automatic snake_case → camelCase conversion
- TypeScript code evaluation via `npx tsx` (Node.js 22+)
- Node.js 22 added to CI test job for TypeScript support
- `_snake_to_camel()` utility for entry_point name conversion

### Changed

- `--language` flag now accepts `vera`, `python`, or `typescript`
- `--language` warning for Vera-specific flags generalised to all non-Vera languages
- `_find_baseline_file()` now uses language-specific file extensions

## [0.0.3] - 2026-03-30

### Added

- `--language python` flag on `vera-bench run` for cross-language LLM comparison
- Python prompt builder (`build_python_prompt`) — minimal prompt without SKILL.md or contracts
- Python code evaluation via subprocess with test wrapper
- `extract_code()` now handles `python` and `py` fence tags alongside `vera`
- Vera-specific metrics (verify@1, fix@1) hidden for Python runs
- Warning when Vera-only flags are used with `--language python`
- CHANGELOG.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md, SECURITY.md
- CI and Codecov badges in README

### Security

- Python subprocess runs with `cwd=work_dir` and API keys stripped from env
- SyntaxError/ImportError/NameError in generated Python sets `check_pass=False`
- Guard against None VeraRunner for non-Python languages

## [0.0.2] - 2026-03-29

### Added

- `vera-bench baselines` command — runs canonical Python solutions against test cases
- `baseline_runner.py` — subprocess-based Python execution with generated test wrappers
- Cross-language comparison in `vera-bench report` (Vera results alongside Python baselines)
- Bool string normalisation for test cases (`"true"`/`"false"` → Python `True`/`False`)

### Fixed

- `run_correct` reporting: shows `-` instead of `0%` when no test cases exist (Tier 2/3)
- `check_rate` type annotation corrected to `float | None`

## [0.0.1] - 2026-03-29

### Added

- LLM runner harness — `vera-bench run --model MODEL` works end-to-end
- `models.py` — Anthropic and OpenAI API abstraction with lazy imports
- `runner.py` — generate → check → verify → run → fix pipeline with retry-on-error
- `metrics.py` — check_rate, verify_rate, fix_rate, run_correct_rate aggregation
- `report.py` — markdown report generation (summary table, tier breakdown, per-problem detail)
- `prompts.py` — full-spec and spec-from-NL prompt construction with SKILL.md context
- Incremental JSONL output (survives crashes)
- 50 benchmark problems across 5 tiers with canonical Vera, Python, and TypeScript solutions
- `vera-bench validate` — full validation pipeline (schema, vera check, vera verify, test execution)
- CI with lint, security, coverage, and dependency audit
- README with installation instructions and quick start

### First benchmark results

- Claude Sonnet 4: 96% check@1, 96% verify@1, 83% run_correct (50 problems, full-spec mode)
- Python canonical baselines: 100% run_correct (24 testable problems)

[Unreleased]: https://github.com/aallan/vera-bench/compare/v0.0.9...HEAD
[0.0.9]: https://github.com/aallan/vera-bench/compare/v0.0.8...v0.0.9
[0.0.8]: https://github.com/aallan/vera-bench/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/aallan/vera-bench/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/aallan/vera-bench/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/aallan/vera-bench/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/aallan/vera-bench/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/aallan/vera-bench/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/aallan/vera-bench/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/aallan/vera-bench/releases/tag/v0.0.1
