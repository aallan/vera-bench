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
(released 2026-04-26). However, `actions/setup-python@v6` bakes pip
26.0.1 into its Python 3.12 toolchain image, so `pip-audit` running
inside the runner reports the runner's own pip as vulnerable until
GitHub refreshes the toolchain image.

The workaround is a `pip install --upgrade pip` step before `pip-audit`
runs, pulling pip 26.1 from PyPI to replace the bundled 26.0.1.

**Removal trigger:** when `actions/setup-python@v6` ships a runner
image with pip ≥ 26.1 natively, drop the `pip install --upgrade pip &&`
prefix from the `Install dependencies and pip-audit` step. Verification
guidance is in issue #63.

---

## Documentation pins

### `assets/results-graph.png` shows v0.0.7 data, not the latest

**File:** `assets/results-graph.png`
**Documented in:** [scripts/README.md](scripts/README.md#plot_resultspy--benchmark-comparison-chart)

The canonical chart committed to the repo is currently pinned to
**v0.0.7** content to match the v0.0.7 narrative in the top-level
README. The benchmark itself is at v0.0.9 (60 problems vs 50), and the
plotting script's default invocation regenerates from the *current*
pyproject version — so running `python scripts/plot_results.py` with
no args overwrites the pinned image with v0.0.9 content.

If you accidentally overwrite the pin, restore with:

```bash
python scripts/plot_results.py --version 0.0.7 --output assets/results-graph.png
```

**Removal trigger:** when the v0.0.9 narrative is written up in the
top-level README, the pin can be released — `python scripts/plot_results.py`
will then regenerate the canonical chart from current data each time.

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

For analyses that need the breakdown, see
[issue #61](https://github.com/aallan/vera-bench/issues/61) — the
follow-up to expose `cached_tokens` separately is tracked there.

**Removal trigger:** none — this is a permanent provenance note about
a metric semantic change. Will eventually move to a CHANGELOG note
once #61 is resolved and the breakdown is exposed structurally.

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

Verify with `vera version` — should print `vera 0.0.111` or later, not
the Homebrew tool's banner.

**Removal trigger:** none — this is a permanent dev-env hazard
caused by a name collision with an unrelated tool. Will stay until
either Homebrew's package renames or we ship a wrapper that errors out
helpfully when invoked from the wrong path.
