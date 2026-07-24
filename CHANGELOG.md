# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`scripts/sweep_status.py` / `scripts/rerun_failed.py` — sweep
  visibility and surgical repair.** `vera-bench run`'s `rich` progress
  blanks itself off-TTY, so `run_sweep.sh`'s tee'd logs hold only a banner
  and the JSONL rows are the only live signal. `sweep_status.py` censuses
  them and separates what a single "dirty" flag conflates: transient infra
  (re-run), `finish_reason=length` (raise `--max-tokens`), and refusals or
  compile errors (real results — keep). `rerun_failed.py` re-runs only a
  target's transiently-failed problems into a scratch `--output-dir` and
  splices them back by `problem_id`, instead of re-running all 60 to repair
  one timeout.

### Changed

- **Charts report "% solved" (pass@1), not `run_correct`.** `run_correct`
  was measured only over the problems that compiled, so a model that
  refused or failed to compile shrank its own denominator and scored
  *higher* for answering less. `% solved` fixes the denominator at the
  gradeable set (problems with test cases): a refusal, a compile failure,
  a runtime error and a wrong answer all count as not-solved.
- **One canonical model matrix; `run_full_benchmark.py` replaced by
  `run_sweep.sh`.** The 8-model lineup was duplicated across three files
  that could drift — `run_full_benchmark.py` (for the gate),
  `plot_results.py` (for the charts), and the sweep runner. It now lives
  once in `vera_bench/matrix.py`; `plot_results.MODELS` derives from it, and
  `preflight.sh` and `run_sweep.sh` enumerate from it.
  `run_full_benchmark.py` — interactive menu, no `--parallel`, a 3600s
  per-target timeout that killed slow Moonshot runs, no resume — is deleted.
  The new `scripts/run_sweep.sh` runs the provider streams concurrently and
  is idempotent: it skips any target already on disk and clean and re-runs
  the rest, so a killed or rate-limited sweep is recovered by re-running it.
  "Clean" reuses `sweep_status.py`'s classifier — a file is dirty only for a
  genuine *transient* fault (rate-limit, timeout, empty content); a refusal
  or a `finish_reason=length` truncation is a real result and is left alone.
  The reasoning models get a bigger `--max-tokens` (16000 fable, 32000 kimi)
  so they stop truncating, and the pro tier is opt-in (`SWEEP_INCLUDE_PRO=1`).
- **`preflight.sh` s3 probes prompt caching for every provider**, not just
  `$REASON_BASE`. Moonshot was never measured and Anthropic was covered only
  incidentally. 1 call becomes 6; override with `PREFLIGHT_CACHE_PROBE`.

### Removed

- **The CVE-2026-3219 `pip install --upgrade pip` workaround** in `ci.yml`, and
  its `KNOWN_ISSUES.md` entry
  ([#63](https://github.com/aallan/vera-bench/issues/63)) —
  `actions/setup-python` now ships pip 26.1.2, so the step did nothing.

### Fixed

- **`errored` counted model runtime-failures as harness errors.** The
  metric added in [#95](https://github.com/aallan/vera-bench/issues/95)
  tallied every row carrying an `error_message`. But the Vera evaluator
  now records the runtime diagnostic for a contract violation, a
  division by zero, a stack overflow — code that *compiled and ran* and
  was graded `run_correct=False`. Those are model failures already in
  the denominator, not the grading gaps `errored` exists to surface. It
  now counts only rows that produced no run verdict
  (`run_correct is None`). The v0.1.7 canary showed the bug directly:
  `errored 1/60` and `3/60` on healthy runs whose only "errors" were the
  model failing hard problems at runtime — after the fix, both are 0,
  with `run_correct` unchanged. `errored` is a derived metric, so
  re-running `vera-bench report` corrects already-swept files.
- **Moonshot cache hits were always recorded as zero.** `_openai_cached_tokens`
  read only `usage.prompt_tokens_details.cached_tokens` — the OpenAI *nested*
  location — but Moonshot reports it at the **top level**, `usage.cached_tokens`
  (per their API reference). The field survives SDK parsing
  (`CompletionUsage` is `extra="allow"`) but we never looked there, so every
  Moonshot row logged `cached_tokens=0` despite Moonshot caching at ~99% on the
  shared Vera prefix — understating cache savings for both Kimi entries. The
  reader now checks both, nested first. Surfaced by the new per-provider s3
  probe above, which is exactly what it was built to catch.
- **Documentation consistency pass** over `README.md`, `CLAUDE.md`,
  `CONTRIBUTING.md`, `KNOWN_ISSUES.md`, `scripts/README.md` and
  `preflight.sh`: stale counts, inaccurate claims and a missing
  `## [Unreleased]` heading. One worth calling out — OpenRouter is a supported
  provider like any other, not something AILANG requires.

## [0.0.16] - 2026-07-23

### Added

- **Per-test subprocess-failure diagnostics for the Aver evaluator**
  ([#72](https://github.com/aallan/vera-bench/issues/72)). The
  `_evaluate_aver_code` per-test loop previously `continue`d silently
  on timeout and non-zero exit — a model whose type-correct Aver
  crashed at runtime was indistinguishable in JSONL from one with
  wrong logic (`error_message=None, check_pass=True,
  run_correct=False`). The loop now captures the first failing
  test's diagnostic (stderr-or-stdout coalesce, 400-char truncation,
  explicit exit-code marker when silent) into `error_message`,
  matching the AILANG evaluator's existing pattern. Both evaluators
  now share a `_first_run_error` formatting helper.
- **`openai-pro/` model-routing prefix — reasoning-mode benchmark
  entries.** `openai-pro/gpt-5.6-sol` runs Sol at
  `reasoning.mode: pro` as a distinct benchmark entry from
  default-mode `gpt-5.6-sol`: same model, different reasoning
  budget — a controlled comparison of whether Vera's contracts do
  the work the reasoning budget otherwise would. Mechanics:
  - `create_client` routes the prefix to `OpenAIClient(...,
    reasoning_mode="pro")`; the runner needs no changes (the
    `complete()` Protocol carries no per-call config by design).
  - Both Sol arms run through the **Responses API**, which is the
    only endpoint carrying `reasoning.mode`, and both get the same
    16k output floor — an unequal budget would be a second variable
    in a comparison that claims to have one. `gpt-5.6-terra` is not
    half of the pair and stays on Chat Completions.
  - JSONL rows are self-describing: `model: "<api-model>#pro"` and
    `"<api-model>#standard"` respectively. Result filenames are
    already distinct (built from the CLI model string).
  - The response echoes the *effective* mode, and a mismatch — or an
    absent echo — raises rather than being recorded as a pro result.
  - `OpenAIClient` now sends `max_completion_tokens` (the GPT-5.x
    reasoning families reject the legacy `max_tokens` kwarg).
  - `scripts/run_full_benchmark.py` `_detect_provider` recognises
    the prefix (→ `OPENAI_API_KEY`).

- **Prompt-cache instrumentation for OpenAI and Moonshot clients**
  ([#61](https://github.com/aallan/vera-bench/issues/61)). Both
  providers now cache automatically server-side (OpenAI ≥1024-token
  prompts; Moonshot longest-prefix matching — a request cache-hits
  only when it shares a prefix with a prior request) — the work is
  routing and observability, not cache management:
  - New `cached_tokens` field on `LLMResponse` and `ProblemResult`
    (JSONL rows): the cache-hit portion of `input_tokens`. Anthropic
    reports `cache_read_input_tokens`; OpenAI-compatible providers
    report `usage.prompt_tokens_details.cached_tokens` (read via a
    shared `_openai_cached_tokens` guard that tolerates absent /
    None / non-int fields). Sweep cost analysis can now compute
    cache-hit rates per provider directly from result files.
  - OpenAI requests carry a stable `prompt_cache_key` (SHA-256 of
    the system prompt, via `extra_body`) so same-prefix requests
    route to the same cache shard — recommended by OpenAI for the
    GPT-5.6 family. During sweeps the ~28k-token SKILL.md prefix
    gets its own shard per language-mode.
  - Moonshot sends no cache parameter — their Context Caching is
    fully automatic with no routing key (their earlier explicit
    X-Msh-* header scheme is obsolete).
- **OpenAI and Moonshot clients hardened to the OpenRouter error
  standard**: `AuthenticationError` → `EnvironmentError` (abort the
  run — retrying 60 problems on a bad key is waste), `RateLimitError`
  / `BadRequestError` / `APIStatusError` → clean `RuntimeError`
  messages, and explicit errors on empty `choices` / empty `content`
  (previously returned `text=""` and the harness blamed the model
  for "did not define entry point").

### Changed

- **Minimum `openai` SDK raised from `>=1.50` to `>=2.45`.** The
  `openai-pro/` path calls `responses.create` with `prompt_cache_key`
  and `reasoning={"mode": "pro"}`; the declared floor supported none of
  the three. Verified against the wheels rather than inferred:
  `responses.create` arrived in 1.66.0, `prompt_cache_key` in 2.0.0,
  and `reasoning.mode` in 2.45.0. 2.0 would in fact work at runtime —
  `maybe_transform` forwards keys a TypedDict does not declare, and the
  response model is pydantic `extra="allow"` — but relying on that
  makes a silent failure possible: if either behaviour changed, the
  "pro" entry would run in standard mode, the effective-mode guard
  would no-op, and the reasoning chart would compare a model against
  itself while looking entirely normal.

### Fixed

- **A sweep with most calls failing could report an excellent score**
  ([#95](https://github.com/aallan/vera-bench/issues/95)). `run_correct`
  is measured over `run_eligible` — problems whose attempt compiled —
  so rows that never reached the compiler (API errors, auth rejections,
  timeouts) left the denominator entirely. Verified: **40 API failures
  plus 20 successes reported `run_correct = 100%`**, and nothing in the
  output said so; `check@1` merely dropped, which is a normal result
  for a model struggling with Vera. The rate itself is unchanged, since
  altering it would break comparability with published results.
  Instead `BenchmarkMetrics` gained `run_eligible` and `errored`, the
  CLI summary now prints the graded denominator whenever it differs
  from the problem count plus an `errored: N/60` row in red, and
  `extract_data` treats a file with nothing gradeable as *missing*
  rather than plotting it as a genuine 0% — the same conflation the
  `missing` set already prevents for absent files, one layer down.
- **`vera run` failures were indistinguishable from wrong answers.**
  The per-test loop in `_evaluate_vera_code` discarded the exit code and
  stderr on failure, and swallowed every exception through a bare
  `except Exception` with no message — so a compiler crash was recorded
  as `error_message=None, check_pass=True, run_correct=False`, byte-identical
  to a model writing a wrong program. The #72 diagnostics work reached the
  Aver and AILANG evaluators but never the Vera path, which is the
  headline number. Now captures the first failure via a `_vera_run_error`
  sibling of `_first_run_error`, including **signal detection**:
  `subprocess` reports a signal death as a negative return code, so a
  compiler SIGBUS arrives as `exit_code == -10` and is now named as such.
  Not hypothetical — vera SIGBUS'd repeatedly on 2026-07-23
  ([aallan/vera#1145](https://github.com/aallan/vera/issues/1145)), and
  every one of those would have been scored against the model.
- **`preflight.sh` now exits non-zero when the gate fails.** It could
  print `*** pro may be SILENTLY IGNORED ***` — the one finding that
  invalidates the reasoning slide — and still exit 0, because the S2 and
  S3 analyses printed their verdicts from inside Python heredocs without
  touching the pass/fail counters. A chained
  `preflight.sh && run_full_benchmark.py` would have sailed straight
  past it. S2's verdict now feeds the counters and the script ends on
  its own tally.
- **Both Sol arms now send `store=False`.** The Responses API defaults
  to `store=True` where Chat Completions does not persist at all, so
  the pro routing silently introduced 30-day server-side retention of
  every prompt and completion. Beyond the data-handling question,
  retained content could feed cross-run caching or personalisation —
  and a benchmark whose second run is informed by its first is not
  measuring what it claims to.
- **Claude Fable 5 returned no code at all.** `AnthropicClient.complete`
  read `response.content[0].text`, but models with extended thinking
  return `ThinkingBlock` entries *ahead of* the `TextBlock` — so every
  Fable 5 call died with `'ThinkingBlock' object has no attribute
  'text'`, recorded as an API-error row with no generated code. The
  whole fable tier of the v0.0.16 matrix would have come back empty.
  A new `_anthropic_text` helper selects blocks by `.type == "text"`
  and joins them, ignoring thinking and redacted-thinking blocks.
  Caught by smoke S1 (2026-07-23); the pre-existing unit test missed it
  because a bare `MagicMock` auto-supplies any attribute, including the
  `.text` the real `ThinkingBlock` lacks.
- **`openai-pro/` went to the wrong endpoint — now uses the Responses
  API.** The reasoning tier was passed as `extra_body={"reasoning":
  {"mode": "pro"}}` on Chat Completions, which rejects it with `400
  Unknown parameter: 'reasoning'`, so every Sol@pro call failed. Per
  OpenAI's reasoning guide, **mode and effort are independent axes** —
  mode selects standard vs pro *execution*, effort controls how much
  reasoning happens — and `reasoning.mode` exists only on the Responses
  API (`Literal["standard", "pro"]` in openai-python 2.47). Pro is
  therefore not expressible on Chat Completions at all: `reasoning` is
  rejected as unknown, and `reasoning_effort="max"` is rejected too
  (`gpt-5.6-sol` accepts only `none`/`low`/`medium`/`high`/`xhigh`
  there — `max` is Responses-only). A client with a reasoning mode set
  now routes to `responses.create` with `instructions`/`input`/
  `max_output_tokens` and reads usage from `input_tokens` /
  `output_tokens` / `input_tokens_details.cached_tokens`. Two new
  guards: an unknown mode raises at construction, and a response whose
  echoed *effective* `reasoning.mode` differs from the requested one
  raises rather than being recorded as a pro result — a silent
  downgrade would turn the headline pro-vs-default comparison into a
  model compared against itself. Confirms the CodeRabbit finding on
  [#92](https://github.com/aallan/vera-bench/pull/92) that was declined
  pending evidence.

  **Both Sol entries are pinned to the Responses API** via
  `RESPONSES_API_MODELS`, with the default entry sending an explicit
  `reasoning.mode: "standard"`. Pro mode exists only on Responses, so
  leaving the default arm on Chat Completions would vary endpoint and
  mode together and the reasoning-budget comparison could not attribute
  its delta to deliberation. The 16000-token output floor applies to
  both arms for the same reason. `gpt-5.6-terra` is a separate tier row
  rather than half of a controlled pair, and stays on Chat Completions.
  Sol rows now report `model` as `gpt-5.6-sol#standard` /
  `gpt-5.6-sol#pro`; charts key on filenames, which are unchanged.
- **Long result paths wrapped mid-token in console output.** `Output:
  <path>` was printed through rich, which wraps at the console width
  (80 when not a tty — CI, and any sweep log piped to a file), breaking
  paths across lines mid-word and making them un-greppable and
  un-copy-pasteable. Now printed with `soft_wrap=True`. This was also
  failing `test_run_ailang_full_path_success` on `main`.
- **`aver`/`ailang` version-probe timeouts reported the wrong cause.**
  A `TimeoutExpired` from `--version` was either unhandled (ailang) or
  folded into the not-found branch (aver), which advised reinstalling a
  compiler that is already installed. Both now report the timeout
  distinctly.
- **AILANG version parsing corrupted result filenames.** `run
  --language ailang` built its output filename from the compiler's
  raw `--version` stdout. `ailang --version` prints a **seven-line**
  banner (version, commit, full SHA, build stamp, blank, tagline,
  copyright), and the old `.strip().replace("ailang ", "")` matched
  nothing in it — the binary prints `AILANG v0.30.0`, capitalised.
  The entire banner therefore landed in the filename, producing a
  216-character name containing embedded newlines and colons. macOS
  creates such a file happily, so this failed silently: every shell
  glob in the sweep runbook, the `file_prefix` matching in
  `plot_results.py`, and the release tarball would all have missed
  the AILANG results. Never caught because `baselines --language
  ailang` uses a separate code path that does not embed versions.
  Both the Aver and AILANG probes now share a `_parse_version_banner`
  helper that takes the first line and extracts the numeric version
  token, falling back to `"unknown"` (which callers already treat as
  "omit the version from the filename"). The AILANG probe also now
  catches `TimeoutExpired`, matching the Aver probe.
- **Vera 0.1.x compatibility for the problem set and canonical
  solutions.** Vera moved from v0.0.177 to v0.1.6+ (the v0.1.0 bug
  burndown plus the 0.1.x line) and three compiler changes broke
  `vera-bench validate` (22/60 failures). All three are now resolved;
  the benchmark validates 60/60 against Vera HEAD (v0.1.6,
  `f6f586b0`):
  - **VB-T1-002 renamed `clamp` → `clamp_to_range`** across the
    problem JSON (signature, entry_point, prose) and all five
    canonical solutions (TypeScript as `clampToRange`). Vera 0.1.x
    makes `clamp` a built-in (spec §9.6) and rejects redefinition
    with `E151` — the problem was unwritable as specified. Problem
    `id` is unchanged (`VB-T1-002`).
  - **State-handler solutions updated for intrinsic-hybrid clause
    semantics** ([vera#1003](https://github.com/aallan/vera/issues/1003),
    shipped in Vera 0.1.x; see also vera#976/#973/#988). Handler
    clause bodies used to be type-checked but never executed — the
    runtime always used builtin state-cell semantics. Now clause
    bodies execute, and the old `put(@Int) -> { resume(()) } with
    @Int = @Int.0` idiom resolves `@Int.0` to the handler state, so
    the "update" is state = old-state — a silent no-op that made
    VB-T5-001 return 0 instead of 3 and broke 3 of 4 VB-T5-006 test
    cases. All four State solutions (T5-001, T5-004, T5-006,
    T5-009) drop the `with` clause; the intrinsic store threads
    state natively (the canonical form in SKILL.md's `run_counter`
    example). T5-004/T5-009 passed tests only incidentally and
    carried the same latent no-op.
  - **`vera_verify_tier1` flipped to `false` on 19 problems**
    (T1-008, T1-010, T2-001, T2-010, T2-014, T3-001..005, T3-008,
    T3-012, T4-001, T4-004, T4-005, T4-007, T4-008, T4-010,
    T5-004). Vera 0.1.x auto-synthesises `int_overflow` /
    `nat_to_int_coerce` proof obligations on all integer
    arithmetic; on unbounded `Int`/`Nat` inputs these are
    legitimately unprovable at Tier 1 (proving them would require
    adding range preconditions — changing the published contracts
    of 19 problems). The obligations are checked at Tier 3
    (runtime) instead, which is the correct classification. This
    flag gates only canonical validation; LLM `verify@1` scoring
    is computed from `verify_pass` and is unaffected.

### Compatibility note

Requires Vera ≥ 0.1.x (the intrinsic-hybrid handler semantics and
`clamp` built-in). Canonical Vera solutions no longer compile/run
correctly on Vera ≤ 0.0.x: the renamed `clamp_to_range` does not
collide there (fine), but the State solutions rely on the new
clause-execution semantics. Aver baselines verified unchanged on
Aver 0.27.1 (the v0.0.14 `Int.div` migration was forward-compatible
throughout); AILANG baselines verified on AILANG v0.30.0.

## [0.0.15] - 2026-06-22

### Fixed

- **`VB-T5-002 greeter_io_boundary` canonical Vera solution** removed
  unused `greet_all` and `greet_loop` helper functions that were not
  required by the problem spec. The helpers contained a latent
  verification gap: `greet_loop` called `greet(...)` in *statement
  position* (discarded result) without propagating `greet`'s
  precondition `requires(string_length(@String.0) > 0)`. Pre-Vera
  v0.0.176 the verifier silently skipped statement-position calls
  during call-site precondition checking ([aallan/vera#730](https://github.com/aallan/vera/issues/730)),
  hiding the gap. v0.0.176 closed that hole, and `vera verify` on the
  pre-fix solution failed with `E501` and a counterexample showing an
  empty-string array element would violate `greet`'s contract. The
  fix simplifies the canonical solution to exactly what the problem
  asks for: the `effect IO` declaration, `build_greeting` (pure
  helper), and `greet` (IO entry point). No `greet_all` / `greet_loop`.

### Compatibility note

This is a **forward-compat methodology release** for Vera v0.0.176
and later. Same shape as v0.0.11 (Aver 0.16 `Console.print` typing)
and v0.0.14 (upcoming Aver `Int.div` migration): an upstream
compiler tightened its semantics, vera-bench had a latent gap, and
this release updates the canonical solution to be strictly correct.

For Vera ≤ v0.0.175 (when statement-position calls were silently
skipped by the call-site precondition checker), the previous canonical
solution worked but was technically writing incorrect Vera. For Vera
≥ v0.0.176, v0.0.14 and earlier vera-bench releases fail `vera
verify` on VB-T5-002 — this is the unblock.

Bisection trail: v0.0.175 passed verification (9 Tier 1 + 1 Tier 3),
v0.0.176 introduced the call-site check and failed with `E501`,
v0.0.177 carried the same failure forward. Confirmed locally in a
fresh venv across all three releases.

Vera, Aver, Python, TypeScript, and AILANG scoring for other
problems are unaffected — the change is scoped to the single
VB-T5-002 canonical solution. All other 59 canonical Vera solutions
still verify cleanly against v0.0.177.

## [0.0.14] - 2026-06-03

### Changed

- **Aver baselines migrated from the integer `/` operator to
  `Int.div`** ([#82](https://github.com/aallan/vera-bench/pull/82), by
  [@jasisz](https://github.com/jasisz), Aver's upstream author).
  Aver's upcoming release drops the partial integer `/` operator —
  integer division can divide by zero (and overflow on `i64::MIN /
  -1`), so it's now the `Result`-returning function `Int.div(a, b) :
  Result<Int, String>`, matching `Int.mod` and Aver's "partial
  operations are functions" rule. (Float `/` stays a total
  operator.) Five Aver baselines used integer `/`:
  - `VB_T3_011_safe_divide` and `VB_T5_003_safe_division_exceptions`
    consume `Int.div`'s `Result` idiomatically via `match Ok/Err`.
    The redundant manual `b == 0` checks are gone — `Int.div`
    already reports the failure — and `try_div` in T5-003
    simplifies to `Int.div(a, b)`, since the function was literally
    re-implementing what `Int.div` now does.
  - `VB_T1_007_safe_modulo` (`a - (a / b) * b`),
    `VB_T4_002_greatest_common_divisor` (`a - (a / b) * b`), and
    `VB_T4_007_count_digits` (`n / 10`) use
    `Result.withDefault(Int.div(...), 0)` — the divisor is
    precondition-guaranteed non-zero in each context, so the
    sentinel never fires in practice.

### Compatibility note

Aver scoring on the upcoming Aver release (post-0.23) requires
v0.0.14 — without this release, every `aver run` against an
`Int.div`-aware compiler would fail. For Aver ≤ 0.23, the converse
applies: these baselines will not compile against `Int.div`-less
compilers. Result files are tagged with `bench_version` so
cross-version comparisons can detect this boundary.

Same forward-compat shape as v0.0.11's `Console.print("{x}")`
migration for Aver 0.16. Vera, Vera spec-from-NL, Python,
TypeScript, and AILANG scoring are unaffected — `0.0.14` is purely
an Aver baseline migration for those languages.

## [0.0.13] - 2026-05-29

### Changed

- **Default Anthropic flagship migrated from Claude Opus 4 to Claude
  Opus 4.8** (`claude-opus-4-20250514` → `claude-opus-4-8`). Opus 4
  is deprecated and retires 2026-06-15. Per the 4.6-generation naming
  convention, the new model ID is dateless and is itself a pinned
  snapshot (not an evergreen alias).
- **Default Anthropic Sonnet-tier migrated from Claude Sonnet 4 to
  Claude Sonnet 4.6** (`claude-sonnet-4-20250514` →
  `claude-sonnet-4-6`). Sonnet 4 is deprecated and retires the same
  day as Opus 4 (2026-06-15); without this migration the Sonnet
  benchmark slot would start returning 404 from the API.
- Affected files: `scripts/run_full_benchmark.py` (`MODELS` dict +
  docstring examples), `scripts/plot_results.py` (`MODELS` list of
  `ModelSpec`s),
  `scripts/README.md` (example commands + slug-convention prose),
  `README.md` (Quick start examples — 9 occurrences, all swapped via
  `replace_all` after verifying the historical v0.0.7 results table
  on lines 24/31 uses the marketing names "Claude Opus 4" / "Claude
  Sonnet 4" and is unaffected), and test fixtures in
  `tests/test_models.py`, `tests/test_cli.py`, `tests/test_runner.py`.
- Deliberately untouched: `scripts/plot_slide.py` (v0.0.7 talk-slide
  renderer, pinned to the v0.0.7 lineup) and the historical results
  table / narrative in `README.md` (locked to v0.0.7 data per the
  chart-pin policy documented in `KNOWN_ISSUES.md`).

## [0.0.12] - 2026-05-25

### Added

- **AILANG comparison language**
  ([#70](https://github.com/aallan/vera-bench/pull/70),
  [#75](https://github.com/aallan/vera-bench/pull/75)).
  Fourth comparison language alongside Python, TypeScript, and Aver.
  AILANG is another zero-training-data language, providing an additional
  data point for the language-design-vs-training-data thesis. Includes:
  prompt builder (`build_ailang_prompt` / `build_ailang_fix_prompt`),
  code evaluator (`_evaluate_ailang_code` with per-test-case main
  synthesis), baseline runner (`run_ailang_baseline`), CLI plumbing
  (`--language ailang` for both `run` and `baselines`), and 60
  canonical reference solutions (`solutions/ailang/*.ail`). The AILANG
  teaching prompt is loaded via `ailang prompt --source embedded`
  (matching the AILANG eval-harness pattern) — no URL fetching. The
  full-benchmark sweep script (`scripts/run_full_benchmark.py`) now
  includes AILANG LLM + AILANG baseline targets (#75), bringing the
  matrix from 8 to 10 targets per model.
- **`--parallel N` flag for concurrent benchmark sweeps**
  ([#73](https://github.com/aallan/vera-bench/pull/73)). Dispatches
  problems to a `ThreadPoolExecutor` with `N` workers. Each worker is
  I/O-bound on its LLM call + subprocess `check`/`run`, so the GIL is
  not a bottleneck. Default `parallel=1` preserves the existing
  sequential code path. Validated with `click.IntRange(min=1)` to
  reject 0/negative at parse time.
- **OpenRouter client** for accessing AILANG-capable models via the
  OpenAI-compatible OpenRouter API. Used by the AILANG LLM-eval mode
  to reach models not directly available from Anthropic/OpenAI/Moonshot.
  Explicit error handling for `AuthenticationError`, `RateLimitError`,
  `BadRequestError`, `APIStatusError`, empty `choices`, and empty
  `content` (with `finish_reason` surfaced).
- **AILANG retry-on-error** in `run_single_problem`. The existing
  `build_ailang_fix_prompt` was previously dispatched only as
  unreachable code; now `--max-fix-attempts > 0` actually retries
  AILANG failures (was silently no-op, undercounting AILANG vs
  Aver/Vera by the entire attempt-2 contribution).
- **Worker crash recording** in `run_benchmark`. Both sequential and
  parallel paths now synthesise a `ProblemResult` with
  `traceback.format_exc()` in `error_message` when
  `run_single_problem` raises. Previously, parallel-path worker
  crashes vanished silently from the JSONL — a 60-problem sweep with
  2 crashes wrote 58 rows and downstream `vera-bench report` showed
  "58/58 (100%)" with no record of the crashes.

### Changed

- **Per-test runtime error capture in AILANG evaluator**. The
  `_evaluate_ailang_code` loop previously `continue`d on timeout and
  non-zero exit, so a row where every test failed at runtime was
  indistinguishable from one that compiled but produced wrong output
  (both showed `check_pass=True, run_correct=False, tests_passed=0,
  error_message=None`). Now captures the first non-zero
  stderr/stdout/exit-N marker into `error_message` (truncated to 400
  chars). Issue [#72](https://github.com/aallan/vera-bench/issues/72)
  tracks the broader per-test stderr aggregation shared with the
  Aver path.
- **Compile-vs-runtime tag classification** in `baseline_runner.py`
  is now regex-based (`re.search(r"\bError ([A-Z]+)_", err)`) with an
  explicit `compile_tags = ("PAR", "TC", "MOD", "ELB", "LINK", "TY")`
  allow-list. Previously used substring matching, which would have
  silently misclassified a future AILANG release adding `Error
  PARSER_` (matches `Error PAR`) or any new tag.
- **Sequential and parallel run_benchmark paths now share fault
  semantics**. Pre-#73, `--parallel 1` aborted on any worker
  exception while `--parallel 2+` logged-and-continued. Now both
  paths wrap `run_single_problem` in identical `try/except` and route
  crashes through `_crash_result` + `_record` helpers.

### Fixed

- `_strip_ailang_main` brace-counter bug: the previous heuristic
  mis-classified canonical AILANG main lines like
  `export func main() -> () ! {IO} {` because `{IO}` provides
  balanced braces, leaving the body as orphan code that broke the
  injected per-test-case `main`. Replaced with indentation +
  bare-`}` regex sentinel logic.
- `_USER_AGENT` constant in `prompts.py` was stuck at `0.0.9` since
  that release. Now matches the package version.

### Compatibility note

Vera, Vera spec-from-NL, Python, TypeScript, and Aver scoring is
unaffected — `0.0.12` is purely additive for those languages. The
AILANG baseline + LLM-eval mode is a new fourth comparison target;
result files from `0.0.12` onwards include AILANG rows that
`0.0.11`-and-earlier sweeps cannot have produced.

The `--parallel N` flag is opt-in; default `parallel=1` exactly
replicates the `0.0.11` sequential code path. JSONL line content is
identical between sequential and parallel modes; only ordering may
differ (parallel writes by completion order, not problem index).

## [0.0.11] - 2026-05-04

### Changed

- Aver test-wrapper harness emits `Console.print("{<call>}")` (string
  interpolation) instead of `Console.print(<call>)`. Aver 0.16
  ("Anneal") tightens `Console.print` to require `String` — the
  previous form silently coerced `Int`, `Bool`, `List<T>`, etc. and
  was a typecheck error from 0.16 onwards. Interpolation predates the
  breaking change by many versions, so the same wrapper works on
  Aver 0.10–0.15 and on 0.16+ (#65).
- All 56 canonical Aver baseline solutions migrated from
  `Console.print(EXPR)` to `Console.print("{EXPR}")`. Mechanical and
  shape-preserving for nested expressions and string arguments.
- 9 baselines whose `main()` printed only a subset of their
  problem-JSON `test_cases` had `main()` regenerated to print every
  test case. This was a pre-existing coverage gap that surfaces only
  after the interpolation migration brings them past `aver check`.

### Added

- 3 Aver baselines restored: `VB_T2_011_starts_with_prefix.av`,
  `VB_T2_012_ends_with_suffix.av`, `VB_T2_013_get_char_code.av`.
  Originally added in v0.0.9 then removed during PR #57 review
  because the Aver stdlib didn't expose `starts_with` / `ends_with` /
  `char_at` at the time. Aver 0.15+ has `String.startsWith`,
  `String.endsWith`, `String.charAt`, and `Char.toCode`, so the three
  baselines are reinstated.

### Compatibility note

Aver scoring on Aver 0.16+ requires v0.0.11 — without this release,
every injected `aver run` crashes at typecheck and `run_correct = 0%`
across the board. For Aver 0.10–0.15, scoring may differ slightly
between v0.0.10 and v0.0.11 result files for the same model on the
same problems:

- The 9 coverage-gap fixes mean `run_correct` is now measured against
  the full set of test cases declared in each problem JSON, rather
  than the partial set the baseline `main()` happened to print. Some
  problems that previously appeared to pass on a partial check may
  now fail on the full check, and vice versa.
- The 3 restored T2 baselines (T2-011/012/013) now contribute to the
  Aver baseline `run_correct` denominator (60 / 60), where they
  previously contributed nothing (no canonical solution available, so
  pre-#65 Aver baselines reported 60 problems with 3 effectively
  excluded from scoring).

The Aver baseline rises to 100% check@1, 100% run_correct against
Aver 0.15.2 with this PR; the previous baseline was 95%/73% on the
same compiler. The lift is real (not a definitional artefact) but
result files are tagged with `bench_version` so cross-version
comparisons can detect this boundary.

Vera, Vera spec-from-NL, Python, and TypeScript scoring is
unaffected.

## [0.0.10] - 2026-04-29

### Changed

- Aver evaluation harness strips module-header `effects [...]` declarations
  before injecting the test main (#62). The injected main needs
  `! [Console.print]`, which would violate any narrower boundary the LLM
  declared (including the common `effects []` for "pure" modules) once
  Aver 0.13 ships and enforces the boundary as a hard type error.
- The strip is window-scoped (only fires inside the module-header block,
  not on `effects [...]`-shaped lines elsewhere), tolerates arbitrary
  whitespace between `effects` and `[`, and tolerates trailing line
  comments after the closing `]`.

### Compatibility note

This is a methodology change for Aver scoring: the same LLM output now
goes through an extra strip pass before reaching the compiler. On Aver
0.12 and earlier the strip is a no-op (LLMs don't emit module-level
`effects [...]` because the docs don't yet describe it), so today's
Aver scores are byte-identical to v0.0.9. Once Aver 0.13 ships and the
boundary becomes part of the doc nudge to models, Aver `run_correct`
rates from v0.0.10 onwards will diverge from any v0.0.9-tagged Aver
results run against Aver 0.13+ — the strip will activate on a measurable
fraction of generations and prevent the underdeclared-effects type
error. Result files are tagged with `bench_version` so cross-version
comparisons can detect this boundary.

Vera, Vera spec-from-NL, Python, and TypeScript scoring is unaffected.

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

[Unreleased]: https://github.com/aallan/vera-bench/compare/v0.0.16...HEAD
[0.0.16]: https://github.com/aallan/vera-bench/compare/v0.0.15...v0.0.16
[0.0.15]: https://github.com/aallan/vera-bench/compare/v0.0.14...v0.0.15
[0.0.14]: https://github.com/aallan/vera-bench/compare/v0.0.13...v0.0.14
[0.0.13]: https://github.com/aallan/vera-bench/compare/v0.0.12...v0.0.13
[0.0.12]: https://github.com/aallan/vera-bench/compare/v0.0.11...v0.0.12
[0.0.11]: https://github.com/aallan/vera-bench/compare/v0.0.10...v0.0.11
[0.0.10]: https://github.com/aallan/vera-bench/compare/v0.0.9...v0.0.10
[0.0.9]: https://github.com/aallan/vera-bench/compare/v0.0.8...v0.0.9
[0.0.8]: https://github.com/aallan/vera-bench/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/aallan/vera-bench/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/aallan/vera-bench/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/aallan/vera-bench/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/aallan/vera-bench/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/aallan/vera-bench/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/aallan/vera-bench/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/aallan/vera-bench/releases/tag/v0.0.1
