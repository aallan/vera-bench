# Known issues, limitations, and workarounds

This file collects the benchmark's known **bugs**, **limitations** (things it
cannot do yet, as distinct from defects in what it claims to do), and active
**workarounds** — dev-environment gotchas and analytical caveats that don't have
a more natural home in the codebase. Each entry includes its *exit condition* —
the specific event that lets us remove the workaround or close the item — so they
don't quietly outlive their reason.

For forward-looking work and priorities, see [ROADMAP.md](ROADMAP.md). For
language gotchas (Vera and Aver syntax rules), see [CLAUDE.md](CLAUDE.md). The
GitHub issue tracker is the source of truth for open work.

---

## Bugs

No known defects that produce a wrong benchmark result — a model graded as
passing when it failed, or the reverse. Such correctness issues are tracked as
`bug`-labelled issues; none are open. Everything below is a limitation or a
workaround, not a wrong answer.

---

## Limitations

Things the harness cannot do yet — distinct from bugs in what it claims to do.
Each maps to a tracked issue.

### The sweep re-runs whole targets to clear a few transient failures

`scripts/run_sweep.sh` marks a target dirty on *any* transient row and re-runs
all 60 problems, even when 57 were already fine — wasteful on slow models, and
under a flaky provider it can re-roll previously-good problems into fresh
failures. The surgical tool `scripts/rerun_failed.py` does per-problem repair but
cannot run concurrently with the sweep (both unlink/write the same file).

**Exit condition:** [#101](https://github.com/aallan/vera-bench/issues/101) —
fold per-problem retry into the sweep's dirty path.

### The test suite isn't tiered — flaky toolchain tests gate the merge

CI runs the whole suite (`pytest -v`) on every push, mixing fast hermetic unit
tests with slow integration tests that shell out to `npx`/`tsx`, `vera`, `aver`,
and `ailang`. The cold-start non-hermeticity was fixed in place (PR
[#100](https://github.com/aallan/vera-bench/pull/100): a warm-up fixture, a
bigger timeout, and declared plotting deps), so it no longer flakes — but the
integration tests are still on the merge-gating path and the gate is ~6 minutes.

**Exit condition:** [#102](https://github.com/aallan/vera-bench/issues/102) —
mark the integration tests and run them off the gate.

### Tier 5 cannot be compared across languages naïvely

Tier 5 tests Vera's algebraic effect handlers (State, Exn, IO). Other languages
solve these with fundamentally different native idioms (`try/except`,
`try/catch`), so a Tier-5 cross-language number is apples-to-oranges. Use the
T1–T4 aggregate for any cross-language headline.

**Exit condition:** a defensible direct cross-language Tier-5 methodology.
[#50](https://github.com/aallan/vera-bench/issues/50) closed (2026-04-16) by
adopting the T1–T4 aggregate convention above — that resolved the reporting
question, not the limitation, which stands. Re-open the question under
ROADMAP Milestone 2 if a direct method is designed.

### 14 problems are not output-graded: 12 ADT-argument, 2 IO

As of v0.0.17 the harness grades 46 of 60 problems. Strings and bools
round-trip on the `vera run --fn` command line (the old "integer arguments
only" limit no longer holds against vera 0.1.7), and array arguments go
through a generated Vera caller (`vera_bench/vera_wrapper.py`) that writes
the arguments into the source — with structured *returns* compared inside
Vera, because they print as WASM addresses, not values.

Two shapes remain ungraded:

- **ADT arguments** (`@List`, `@Tree`, `@Expr`, `@Option`; 12 problems). The
  problem statements ask the *model* to define the type, so constructor
  names, arity and field order are the model's choice — a wrapper has to be
  generated against the model's own declaration, with a decline-to-grade
  path when it cannot be matched. Guessing would record correct solutions as
  failures, which is worse than not grading.
- **IO problems** (`@Unit` return; 2 problems). Vera grades them on stdout,
  but the aver/ailang baseline protocol is one printed line per test case,
  and `print_numbers` emits several lines or none. Grading is
  all-languages-or-none, so they wait for a whole-stdout baseline mode.

**Exit condition:** [#107](https://github.com/aallan/vera-bench/issues/107)
steps 2 (ADT arguments) and 5 (IO stdout).

### The LLM request timeout is hardcoded, and Moonshot's differs

The per-request timeout lives in each client's `complete()` signature and
cannot be set from the CLI. Moonshot runs at **300s** (raised in v0.0.17
after VB-T5-009 exceeded 120s deterministically and was recorded as a
*transient* error, inviting retries that could never succeed); every other
provider runs at **120s**. Until the flag exists, Moonshot rows on long
problems are not strictly comparable with other providers' under the same
version, and a repeated timeout should be read as a budget wall rather than
infrastructure flake.

**Exit condition:** [#105](https://github.com/aallan/vera-bench/issues/105)
— a `--timeout` flag threaded through to the clients, recorded in the rows.

### `rerun_failed.py` must not repair files from an older bench version

The surgical repair tool re-runs problems under the *current* harness and
splices the rows into the target file. Against a file from an older bench
version that mixes measurement conditions invisibly: the spliced rows carry
the current timeout, wrapper grading and problem set inside a filename that
claims the old version. Repair only files whose embedded version matches the
installed `vera-bench --version`.

**Exit condition:** none — this is an inherent property of in-place repair.
The version-embedded filename is the guard; check it before `--apply`.

---

## Analytical caveats

### `input_tokens` semantic shift across PR #60 (Anthropic prompt caching)

**Affected:** `LLMResponse.input_tokens` for Anthropic models in any
JSONL written after PR [#60](https://github.com/aallan/vera-bench/pull/60)
landed (2026-04-17).

Pre-merge: `input_tokens` was the raw count of (system + user) tokens
sent to the API. Post-merge: it's the **total billed input** —
uncached tokens, plus cache-write tokens, plus cache-read tokens —
summed into a single field.

The numerical totals are still meaningful and additive for cost
estimation, but they're not directly comparable to pre-merge values
because:

- Pre-#60: each call's `input_tokens` repeated the ~18k-token system
  prompt for full price.
- Post-#60: subsequent calls report the cached read at 0.1× price
  rolled into the same field, so the *count* is comparable but the
  *per-token cost* implicit in that count is not.

**Resolved as of v0.0.16:** [#61](https://github.com/aallan/vera-bench/issues/61)
landed, and `cached_tokens` is now a first-class field on `ProblemResult`
and in every JSONL row, for Anthropic, OpenAI and Moonshot alike. The
breakdown is therefore structurally available going forward:
`input_tokens` is still the total billed input, and `cached_tokens` says
how much of it was a cache read.

The caveat above still applies to **JSONL written between PR #60 and
v0.0.16** — those rows have the summed `input_tokens` with no way to
recover the split. Treat that window's per-token cost as unknowable
rather than inferring it.

**Cache rates, measured 2026-07-23** (first live exercise of the
instrumentation, via `scripts/preflight.sh`; full table in
[#61](https://github.com/aallan/vera-bench/issues/61#issuecomment-5060577646)):

| provider | prompt | cached |
|---|---|---|
| OpenAI (`gpt-5.6-sol`) | ~29k Vera prefix, 2nd call | **99%** |
| OpenAI (`#pro`) | ~119k (pro re-reads across passes) | **73%** |
| Anthropic (`claude-sonnet-5`) | ~45k Vera prefix, 2nd call | **100%** |
| Moonshot (Kimi) | ~29k Vera prefix, 2nd call | **100%** (after the [#97](https://github.com/aallan/vera-bench/pull/97) reader fix) |

Two things worth carrying into any cost estimate:

- **Small targets cannot cache.** The Python and TypeScript prompts are
  70–105 tokens, below OpenAI's 1024-token minimum. A `0%` there is
  correct, not a fault.
- **Moonshot's `cached_tokens` was a *reader* bug, now fixed.** Moonshot
  reports the cache read at the top level of `usage` (`cached_tokens`), not
  in the nested `prompt_tokens_details.cached_tokens` where OpenAI puts it,
  so the harness read `0` regardless of the true value. Fixed in
  [PR #97](https://github.com/aallan/vera-bench/pull/97); a two-call probe
  then showed **0 → 100%** on the second call, confirming Moonshot's
  automatic longest-prefix Context Caching works and is now instrumented.

**Removal trigger:** none — this is a permanent provenance note about a
metric semantic change in historical data. It stops being load-bearing
once no published analysis draws on results from that window.

---

## External watch items

### Harness (née Codecov) acquisition — CI coverage reporting

The coverage badge and report history depend on Codecov, whose acquisition
by Harness puts long-term service continuity outside our control. The merge
gate itself does not: `--cov-fail-under=80` runs inside pytest in CI, so a
Codecov outage loses reporting, not enforcement. Watch item, not a fault:
nothing is broken today.

**Exit condition:** tracked in
[#80](https://github.com/aallan/vera-bench/issues/80) — either Harness
commits to the service terms we rely on, or CI moves to a self-contained
coverage check.

---

## Dev-environment gotchas

### `/opt/homebrew/bin/vera` is not the Vera programming language

There is an unrelated Homebrew package that installs a `vera` binary at
`/opt/homebrew/bin/vera` (a static-analysis tool for C++). It has
**nothing to do with the Vera programming language** that this
benchmark targets.

If `which vera` returns `/opt/homebrew/bin/vera`, that's the wrong
binary. The benchmark needs the Python `vera` from
[aallan/vera](https://github.com/aallan/vera), installed via:

```bash
pip install git+https://github.com/aallan/vera.git
# or, for development:
git clone https://github.com/aallan/vera.git /tmp/vera
pip install -e /tmp/vera
```

Verify with `vera version` — should print `vera 0.1.6` or later, not
the Homebrew tool's banner.

`VERA_PATH` overrides the lookup if you need to point at a specific
binary without reordering `$PATH`:

```bash
export VERA_PATH="$PWD/.venv/bin/vera"
```

**Removal trigger:** none — this is a permanent dev-env hazard
caused by a name collision with an unrelated tool. Will stay until
either Homebrew's package renames or we ship a wrapper that errors out
helpfully when invoked from the wrong path.

### AILANG installs into the venv, and has no `$PATH` override

**Affected:** `vera-bench run --language ailang`, `baselines --language
ailang`, and the `s5` stage of `scripts/preflight.sh`.

The `ailang` binary is a ~90 MB Go build that ends up **inside
`.venv/bin/`**, despite not being a Python package. Two consequences:

1. `pip install -e ".[dev,llm]"` will **not** restore it, and
   `rm -rf .venv` **deletes it**. Any venv rebuild silently costs you
   the AILANG targets until you reinstall from
   [ailang](https://github.com/sunholo-data/ailang).
2. Unlike `vera` (which honours `VERA_PATH`) and `aver` (which is
   normally installed globally by `cargo`), the harness resolves AILANG
   **by `$PATH` only** — there is no `AILANG_PATH` escape hatch. A shell
   without `.venv/bin` on `$PATH` reports `ailang not found on PATH`,
   which reads like "not installed" when it is merely not visible.

So any shell running AILANG targets needs:

```bash
export PATH="$PWD/.venv/bin:$PATH"
```

**Removal trigger:** if the harness grows an `AILANG_PATH` override
(mirroring `VERA_PATH`), point 2 goes away and this entry shrinks to the
venv-fragility note.
