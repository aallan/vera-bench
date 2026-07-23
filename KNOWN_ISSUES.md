# Known issues and workarounds

This file collects active workarounds, dev-environment gotchas, and
analytical caveats that don't have a more natural home in the codebase.
Entries are deliberately written to include their *exit condition* — the
specific event that lets us remove the workaround or close the caveat —
so they don't quietly outlive their reason.

For tracked feature work and roadmap items, see [ROADMAP.md](ROADMAP.md).
For language gotchas (Vera and Aver syntax rules), see
[CLAUDE.md](CLAUDE.md).

---

## CI workarounds

### CI: `pip install --upgrade pip` in the dependency-audit job

**File:** `.github/workflows/ci.yml`, `dependency-audit` job
**Tracking issue:** [#63](https://github.com/aallan/vera-bench/issues/63)
**Related:** [aallan/vera#537](https://github.com/aallan/vera/issues/537)
(same workaround, same root cause)

[CVE-2026-3219](https://nvd.nist.gov/vuln/detail/CVE-2026-3219) is a
vulnerability in pip 26.0.1's archive handling. It was fixed in pip 26.1
(released 2026-04-26). However, the `actions/setup-python` toolchain
image baked pip 26.0.1 into its Python 3.12 environment, so `pip-audit`
running inside the runner reported the runner's own pip as vulnerable
until GitHub refreshed the image.

The workaround is a `pip install --upgrade pip` step before `pip-audit`
runs, pulling pip 26.1 from PyPI to replace the bundled 26.0.1.

**Status:** issue #63 is **closed**, but the workaround is still present
in `ci.yml` and the action has since been bumped to `@v7`. Nobody has
verified whether the `@v7` image ships pip ≥ 26.1 natively, so the step
may now be redundant.

**Removal trigger:** confirm what pip version the current
`actions/setup-python@v7` image ships (add a temporary `pip --version`
step, or check a recent run log). If it is ≥ 26.1, drop the
`pip install --upgrade pip &&` prefix from the `Install dependencies and
pip-audit` step and delete this entry. If it is still older, reopen #63
so the trigger has a live home again.

---

## Documentation pins

### `assets/results-graph.png` shows v0.0.7 data, not the latest

**File:** `assets/results-graph.png`
**Documented in:** [scripts/README.md](scripts/README.md#plot_resultspy--benchmark-comparison-chart)

The canonical chart committed to the repo is currently pinned to
**v0.0.7** content to match the v0.0.7 narrative in the top-level
README. The benchmark itself has moved on since then — at the time of
writing, 60 problems vs the v0.0.7 chart's 50, plus additional
comparison languages (Aver, AILANG) and methodology changes — and the
plotting script's default invocation regenerates from the *current*
`pyproject.toml` version. So running `python scripts/plot_results.py`
with no args overwrites the pinned image with current-version content.

If you accidentally overwrite the pin, restore with:

```bash
python scripts/plot_results.py --version 0.0.7 --output assets/results-graph.png
```

**Removal trigger:** when the top-level README narrative is rewritten
against a current data release (with re-run results across the
expanded problem set and comparison languages), the pin can be
released — `python scripts/plot_results.py` will then regenerate the
canonical chart from current data each time.

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
| Moonshot | — | **not yet measured** |

Two things worth carrying into any cost estimate:

- **Small targets cannot cache.** The Python and TypeScript prompts are
  70–105 tokens, below OpenAI's 1024-token minimum. A `0%` there is
  correct, not a fault.
- **Moonshot's `cached_tokens` has never been observed non-zero.** Both
  Kimi entries have only ever run against the small Python target, so
  their `0%` is uninformative. Their Context Caching is automatic
  longest-prefix with no routing key, so there is no parameter to
  misconfigure — but the read is unproven. The next full sweep is the
  first real test.

**Removal trigger:** none — this is a permanent provenance note about a
metric semantic change in historical data. It stops being load-bearing
once no published analysis draws on results from that window.

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
