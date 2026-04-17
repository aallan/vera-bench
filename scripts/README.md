# scripts/

Operational scripts that sit alongside the `vera-bench` CLI — not shipped with
the installed package, but kept in-repo for reproducibility.

| Script | Purpose |
|--------|---------|
| [`run_full_benchmark.py`](#run_full_benchmarkpy--full-matrix-benchmark-runner) | Runs every target (Vera, spec-from-NL, Python, TypeScript, Aver + baselines) for one model |
| [`plot_results.py`](#plot_resultspy--benchmark-comparison-chart) | Generates the headline benchmark comparison chart |
| [`validate_problems.py`](#validate_problemspy--problem-set-validation) | Validates every problem JSON + canonical Vera solution |

---

## `run_full_benchmark.py` — full matrix benchmark runner

Runs all eight benchmark targets for a single model, writing result JSONLs to
`results/` and a timing summary to `results/timing.json`. Running it once per
model sweeps the full matrix used by `plot_results.py`.

### The eight targets

| # | Target | Uses |
|---|--------|------|
| 1 | Vera full-spec | model + Vera compiler + SKILL.md |
| 2 | Vera spec-from-NL | model + Vera compiler + SKILL.md |
| 3 | Python LLM | model |
| 4 | TypeScript LLM | model (via `npx tsx`) |
| 5 | Aver LLM | model + Aver compiler + llms.txt |
| 6 | Python baselines | canonical `solutions/python/*.py` |
| 7 | TypeScript baselines | canonical `solutions/typescript/*.ts` |
| 8 | Aver baselines | canonical `solutions/aver/*.av` |

Targets 6–8 don't call an LLM — they just run the canonical solutions against
each problem's test cases to confirm the problem JSONs are self-consistent.
Skip them with `--skip-baselines` when running multiple models back-to-back
(they produce the same numbers every time).

### Usage

```bash
# Interactive mode — prompts for provider, model, and API key
python scripts/run_full_benchmark.py

# Autonomous mode (CI-friendly)
ANTHROPIC_API_KEY=sk-ant-... \
  python scripts/run_full_benchmark.py --model claude-sonnet-4-20250514

# Pass the key as a flag (avoid in shell history / CI logs — prefer env var)
python scripts/run_full_benchmark.py \
  --model gpt-4.1-2025-04-14 --api-key sk-...

# Skip baselines when sweeping multiple models
python scripts/run_full_benchmark.py \
  --model claude-opus-4-20250514 --skip-baselines
```

### Environment variables by provider

The script auto-detects the provider from the model string and looks up the
right env var:

| Provider | Model-string prefix | Env var |
|----------|---------------------|---------|
| Anthropic | `claude-*` or `anthropic/*` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-*`, `o1-*`, `o3-*`, `openai/*` | `OPENAI_API_KEY` |
| Moonshot | `moonshot/*` | `MOONSHOT_API_KEY` |

Missing env var + no `--api-key` + no TTY → the script exits with an error.
Missing env var + TTY → it prompts via `getpass`.

### Sweeping the full matrix

There's no built-in "run all models" mode — run the script once per model:

```bash
set -euo pipefail
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export MOONSHOT_API_KEY=...

# Run baselines once (they don't depend on the model)
# — or pass --skip-baselines on every call if they're already fresh.
for model in \
  claude-opus-4-20250514 \
  claude-sonnet-4-20250514 \
  gpt-4.1-2025-04-14 \
  gpt-4o \
  moonshot/kimi-k2.5 \
  moonshot/kimi-k2-turbo-preview; do
  python scripts/run_full_benchmark.py --model "$model" --skip-baselines
done

# Baselines once
vera-bench baselines
vera-bench baselines --language typescript
vera-bench baselines --language aver

# Headline chart
python scripts/plot_results.py
```

### Timing expectations

Rough per-model totals observed on v0.0.9 (60 problems, 2026-04):

| Provider / model | Full suite (8 targets) |
|------------------|-----------------------|
| Claude Opus 4 | ~17 min |
| Claude Sonnet 4 | ~15 min |
| GPT-4.1 / GPT-4o | ~10–12 min |
| Moonshot K2.5 | ~3.5 h (slow provider; Aver especially) |
| Moonshot K2 Turbo | ~1.5 h |

The full six-model sweep is dominated by the two Moonshot models. Expect
5–8 hours end-to-end.

### Output files

For model `M` at bench version `V` and compiler versions `VV` / `AV`:

| File | Contents |
|------|----------|
| `results/{M}-bench-{V}-vera-{VV}.jsonl` | Vera full-spec attempts |
| `results/{M}-spec-from-nl-bench-{V}-vera-{VV}.jsonl` | Vera spec-from-NL attempts |
| `results/{M}-python-bench-{V}.jsonl` | Python generation attempts |
| `results/{M}-typescript-bench-{V}.jsonl` | TypeScript generation attempts |
| `results/{M}-aver-bench-{V}-aver-{AV}.jsonl` | Aver generation attempts |
| `results/{python,typescript,aver}-baseline.jsonl` | Canonical solution runs |
| `results/timing.json` | Per-target wall-clock + status for the most recent run |

Each JSONL line is **one attempt on one problem** — failed `vera check`/`aver
check` runs produce multiple lines per problem (the model is asked to fix
and retry). The harness auto-resumes: rerunning the same invocation skips
problems that already have a passing attempt on file.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All targets passed |
| `1` | One or more targets failed, or missing API key / unknown model |

A failed target does **not** abort the rest — the script always runs all
eight, writes `timing.json` with each target's status, then exits non-zero
at the end if any failed. This makes partial-run recovery straightforward.

---

## `plot_results.py` — benchmark comparison chart

Produces `assets/results-graph.png`: a four-panel chart showing
`run_correct` rates across six models × four modes (Vera full-spec, Vera
spec-from-NL, Python, TypeScript). This is the canonical chart shown in
the top-level README.

> **Heads up:** the committed `assets/results-graph.png` is pinned to the
> **v0.0.7** data (to match the v0.0.7 narrative in the top-level
> README). Running `python scripts/plot_results.py` with no args will
> regenerate it from the *current* pyproject bench version (v0.0.9), so
> it overwrites the pinned image. Don't commit that overwrite until the
> v0.0.9 writeup is ready; regenerate the pinned image with
> `--version 0.0.7 --output assets/results-graph.png` to restore it.

### Usage

```bash
# Default: regenerate the canonical chart from pyproject.toml's bench version
# -> assets/results-graph.png (committed; overwritten on each run)
python scripts/plot_results.py

# Include Aver as an extra comparison language (off by default)
# -> assets/results-graph_with-aver.png (gitignored)
python scripts/plot_results.py --extra aver

# Historical bench version (requires JSONL files from that era in results/)
# -> assets/results-graph_v0.0.7.png (gitignored)
python scripts/plot_results.py --version 0.0.7

# Combination
# -> assets/results-graph_v0.0.9_with-aver.png (gitignored)
python scripts/plot_results.py --version 0.0.9 --extra aver

# Custom output path (bypasses the convention)
python scripts/plot_results.py --output /tmp/draft.png

# Custom results directory
python scripts/plot_results.py --results-dir path/to/archive
```

### Filename convention

Only the **canonical chart** (`assets/results-graph.png`) is committed to
the repo — it gets replaced in-place every time you regenerate from the
current release's JSONL data. Any variant — historical `--version` or extra
`--extra` language — produces a suffixed filename that is gitignored:

| Invocation | Output path | Committed? |
|------------|-------------|------------|
| (no flags) | `assets/results-graph.png` | ✅ |
| `--extra aver` | `assets/results-graph_with-aver.png` | ❌ gitignored |
| `--version 0.0.7` | `assets/results-graph_v0.0.7.png` | ❌ gitignored |
| `--version 0.0.7 --extra aver` | `assets/results-graph_v0.0.7_with-aver.png` | ❌ gitignored |

The `--output` flag overrides this convention entirely if you want a custom
path (useful for draft charts written to `/tmp/`).

### Default mode set vs. optional comparison languages

The default chart shows four modes: `Vera`, `Vera NL`, `Python`, `TypeScript`.
These are the "always-on" languages — Vera is the subject; Python and
TypeScript are the apples-to-apples comparisons. Aver is an additional
functional language available via `--extra aver`:

```bash
# Default: Python + TypeScript only (+ Vera, Vera NL)
python scripts/plot_results.py

# With Aver added as a fifth mode
python scripts/plot_results.py --extra aver
```

### Adding a new optional language

Example: adding Rust later.

1. Run the benchmark with `--language rust` so a JSONL file exists.
2. Add the mode to `MODE_PATTERNS` with its filename fragment:
   ```python
   "Rust": "rust-",
   ```
3. If the Rust compiler stamps a version into the filename (like Vera or
   Aver do), add it to `_COMPILER_SUFFIXED`:
   ```python
   _COMPILER_SUFFIXED = {"Vera": "vera", "Vera NL": "vera", "Aver": "aver", "Rust": "rust"}
   ```
4. Add a colour to `COLORS`.
5. Register the `--extra` choice:
   ```python
   OPTIONAL_COMPARISON_MODES = {"aver": "Aver", "rust": "Rust"}
   ```

No changes to the plot functions are needed — they already accept a
dynamic list of comparison modes.

All numbers are computed on the fly from the JSONL result files via
`vera_bench.metrics.compute_metrics`. **Do not hand-edit percentages** — if a
number looks wrong, fix the underlying results and rerun.

### Which files it reads

For a given `--version X.Y.Z`, the script globs `results/` for files matching
each model × mode combination:

| Mode | Glob pattern |
|------|--------------|
| Vera full-spec | `{prefix}-bench-{X-Y-Z}-vera-*.jsonl` |
| Vera NL | `{prefix}-spec-from-nl-bench-{X-Y-Z}-vera-*.jsonl` |
| Python | `{prefix}-python-bench-{X-Y-Z}.jsonl` |
| TypeScript | `{prefix}-typescript-bench-{X-Y-Z}.jsonl` |
| Aver (opt-in) | `{prefix}-aver-bench-{X-Y-Z}-aver-*.jsonl` |

Where `{prefix}` is the model's `file_prefix` from the `MODELS` registry
(e.g. `claude-opus-4-20250514`, `moonshot-kimi-k2.5`). Dots in the version
are converted to dashes to match the filename convention.

If multiple files match (e.g. the same model was re-run against a newer Vera
compiler), the most recently modified file wins. The Vera compiler version
displayed in the chart subtitle is auto-detected from the filenames of the
Vera full-spec results.

### Missing-file behaviour

If a file is missing, the script prints a warning like

```
Warnings:
  Kimi K2.5 / Vera NL: no file matching bench-0.0.9
```

…and continues with a `0%` bar for that cell. Fix by running the missing
target (`vera-bench run --model ... --language ...`) and re-running the plot
script.

### Adding a new model

Edit the `MODELS` list near the top of `plot_results.py`:

```python
MODELS: list[ModelSpec] = [
    ModelSpec("Claude Opus 4", "claude-opus-4-20250514", "flagship"),
    ...
    ModelSpec("My New Model", "my-new-model-id", "flagship"),
]
```

- `display` — shown on the chart (keep short, ~12 chars)
- `file_prefix` — the model-ID portion of the result filename (run
  `vera-bench run --model X ...` and inspect the resulting filename)
- `tier` — `"flagship"` (top-left panel) or `"sonnet"` (top-right panel).
  This is purely a layout decision about which panel the model renders in;
  the split is "current flagship" vs "previous-gen / cost-tier" by
  convention.

The script expects **exactly three models per tier** for the panels to lay
out correctly. If you want four-and-four, adjust the subplot sizing in
`main()`.

### Adding a new mode

Add an entry to `MODE_PATTERNS` *and* add the colour to `COLORS`. You'll
also need to update the three `plot_*` functions, which currently assume
four modes.

### Chart layout

The chart has four panels, arranged vertically:

1. **Flagship Tier** (top-left) — bars for the three flagship models
2. **Sonnet Tier** (top-right) — bars for the three secondary models
3. **Does Vera beat Python / TypeScript?** — horizontal delta bars per model
4. **All Models × All Modes** — grouped bars showing all four modes per model

See `DESIGN.md` for rationale on the tier split.

### Colour palette

Pulled from `veralang.dev`:

| Role | Hex |
|------|-----|
| Vera | `#1A7F45` (green) |
| Vera NL | `#52b788` (light green) |
| Python | `#E05600` (orange) |
| TypeScript | `#975526` (brown) |
| Aver | `#6B4FBB` (indigo) |
| Positive delta | `#1A7F45` (green) |
| Negative delta | `#C0392B` (red) |

### Historical charts

For any bench version earlier than the pyproject default, pass `--version
X.Y.Z` — the output filename picks up a `_v{X.Y.Z}` suffix and lands in
`assets/`, but is gitignored so it stays local. Useful for confirming a
refactor hasn't changed how historical data renders:

```bash
python scripts/plot_results.py --version 0.0.7
# -> assets/results-graph_v0.0.7.png (local only)
```

The canonical historical snapshot for v0.0.7 lives at its GitHub tag URL:
<https://github.com/aallan/vera-bench/blob/v0.0.7/assets/benchmark_v0.0.7.png>.

### Reproducibility

Because the script reads from JSONL files rather than hardcoded numbers,
regenerating a chart requires the corresponding result files to be present
in `results/`. Note that `results/*.jsonl` is **gitignored** — only the
committed canonical chart (`assets/results-graph.png`) is
version-controlled. To reproduce a historical chart, rerun the relevant
`vera-bench run` / `vera-bench baselines` commands against the target
bench version and compiler to regenerate the JSONL files locally, then run
this script.

---

## `validate_problems.py` — problem-set validation

Runs the full validation suite against every problem JSON in `problems/` and
every canonical Vera solution in `solutions/vera/`. Equivalent to
`vera-bench validate` — this script is a thin standalone wrapper that adds
the repo root to `sys.path` so it works without installing the package.

### What it checks

For each of the 60 problems:

| Column | Meaning |
|--------|---------|
| `Fields` | All required JSON fields present and well-typed |
| `.vera` | Canonical Vera solution file exists |
| `Check` | `vera check solutions/vera/{file}.vera` exits 0 |
| `Verify` | `vera verify` exits 0 and reports at least the expected tier |
| `Tiers` | Verification tier breakdown (T1/T3 counts) |
| `Tests` | `vera run --fn` output matches every `test_cases[*].expected` |

A problem is `OK` only if every column passes. Problems with `test_cases: []`
show `-/-` under `Tests` and still pass (contract-only problems).

### Usage

```bash
python scripts/validate_problems.py
```

No flags. Exits `0` if all 60 problems pass, non-zero otherwise. Run this
before committing changes to `problems/` or `solutions/vera/`.

This is also what CI runs on every PR to the problem set — see
`.github/workflows/`.

### When to run manually

- After editing a problem JSON (e.g. adding test cases, tweaking contracts)
- After rewriting a canonical Vera solution
- After upgrading the Vera compiler (to confirm nothing regressed)
- Before tagging a bench release

It's fast (~5–10 seconds for all 60 problems) so there's no reason to skip
it.
