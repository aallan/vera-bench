# scripts/

Operational scripts that sit alongside the `vera-bench` CLI — not shipped with
the installed package, but kept in-repo for reproducibility.

| Script | Purpose |
|--------|---------|
| [`preflight.sh`](#preflightsh--pre-sweep-gate) | Pre-sweep gate: model ids, auth, API parameters and every toolchain, one problem each |
| [`run_sweep.sh`](#run_sweepsh--idempotent-full-matrix-sweep-runner) | Idempotent full-matrix sweep — skips clean targets, re-runs infra failures |
| [`plot_results.py`](#plot_resultspy--benchmark-comparison-chart) | Generates the headline benchmark comparison chart |
| [`plot_slide.py`](#plot_slidepy--talk-slide-renderer) | Renders result panels as 16:9 slides for talk presentation |
| [`validate_problems.py`](#validate_problemspy--problem-set-validation) | Validates every problem JSON + canonical Vera solution |

---

## `preflight.sh` — pre-sweep gate

Run this **before** committing to a full sweep. A full sweep is ~52 target-runs — 8 models × 6 LLM targets, plus the 4 baseline runs once for the whole sweep rather than per model — with
no resume (see [Output files](#output-files)), so a wrong model id, a rejected
API parameter, or a compiler missing from `PATH` costs hours and real money to
discover late. Every check here is a single problem — the whole gate is roughly
$1–2.

```bash
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... MOONSHOT_API_KEY=...
bash scripts/preflight.sh                 # all stages
bash scripts/preflight.sh s2 s3           # only these stages
SMOKE_SKIP_MODELS="claude-fable-5" bash scripts/preflight.sh s1
```

Stage selection and `SMOKE_SKIP_MODELS` exist because the calls cost money: a
stage that already passed should not be paid for twice while you iterate on a
fix.

| Stage | Checks | Cost |
|-------|--------|------|
| `s0` | Model ids exist, via the provider listings the script queries — currently OpenAI and Moonshot. Anthropic ids are not queried here and are covered by `s1` instead | free |
| `s1` | Auth, id acceptance and request parameters — one problem per model, Python target (no ~28k-token prefix) | cheap |
| `s2` | The reasoning-budget pair actually differs — same model, same problem, mode the only variable | 2 calls |
| `s3` | Prompt-cache accounting: one model **per provider**, two calls each against the ~29k Vera prefix, checking `cached_tokens` on the second | 6 calls |
| `s5` | All six target variants end-to-end (five languages — Vera runs in both full-spec and spec-from-NL), proving the Vera / Aver / AILANG toolchains work *through the harness* | 6 calls |

The model list is **not** duplicated in the script — `s0` and `s1` read it from
`vera_bench/matrix.py`, so a model added to
the sweep is gated automatically rather than silently skipped. The `s2` pair and
the `s5` canary are roles rather than the whole matrix, so they are named at the
top of the script and overridable via `PREFLIGHT_REASON_BASE`,
`PREFLIGHT_REASON_PRO` and `PREFLIGHT_CANARY`.

Two behaviours worth knowing:

- **It judges result rows, not exit codes.** `vera-bench run` records an API
  error as a JSONL row and still exits `0` — deliberate, so a transient failure
  costs one problem rather than the sweep. A gate reading `$?` therefore reports
  success for a model that never answered; both fable-tier models passed that
  way on 2026-07-23 while failing every call.
- **Each stage writes to its own directory.** Result filenames carry no
  timestamp and `run` unlinks an existing file, so two stages running the same
  model × language × mode would otherwise silently overwrite each other.

Output goes to `/tmp/vb-smoke-<date>-<time>/`, never `results/`, so a gate run
cannot pollute a real sweep. No key is ever printed; the report is safe to
paste. Targets bash 3.2 (macOS system bash).

---

## `run_sweep.sh` — idempotent full-matrix sweep runner

Runs the whole matrix — every model × its targets — in one terminal,
unattended and **recoverable at the target level**, with the provider
streams running concurrently. Its defining property: it **skips any target
whose result file already exists and is clean**, and (re)runs everything
else through fresh `vera-bench run` invocations. Safe to run repeatedly;
re-run it until it reports 0 dirty.

The model list, providers, and which models run the zero-training-data
targets all come from `vera_bench/matrix.py` — the same registry
`preflight.sh` and `plot_results.py` read, and that this runner enumerates
from, so nothing drifts.

### Why a wrapper, and what "clean" means

`vera-bench run` has no resume: it unlinks the output file at startup, so a
target that dies mid-run is lost. The wrapper adds recovery at the *target*
level — not a process resume, but a fresh re-run of only the targets that
aren't already clean, so a killed or partial sweep is recovered simply by
running the script again.

"Clean" reuses `sweep_status.py`'s classifier, so the runner and the status
tool always agree. It distinguishes a **transient fault** (rate-limit,
timeout, empty content) — which is re-run — from a **real result**, which is
not. A refusal, a compile or runtime error, and a `finish_reason=length`
truncation are all real results: the model *was* measured, so the file is
left alone. Length truncations are prevented up front by a bigger
`--max-tokens` for the reasoning models; repair a stray one per-problem with
`rerun_failed.py` rather than re-running all 60. This is the difference
between "the model lost" and "we couldn't fairly measure it."

### Usage

```bash
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... MOONSHOT_API_KEY=...
source .venv/bin/activate

bash scripts/run_sweep.sh                # everything except the pro tier
SWEEP_INCLUDE_PRO=1 bash scripts/run_sweep.sh   # opt in to pro (~$10/target)

# Overnight:
nohup caffeinate -is bash scripts/run_sweep.sh > ~/sweep.out 2>&1 &
tail -f ~/sweep.out
```

Baselines are separate and run once (they don't depend on the model):

```bash
vera-bench baselines                       # python (default)
vera-bench baselines --language typescript
vera-bench baselines --language aver
vera-bench baselines --language ailang
```

### Tunables (env)

| Var | Default | Purpose |
|-----|---------|---------|
| `PAR_ANTHROPIC` / `PAR_OPENAI` / `PAR_MOONSHOT` | 4 / 3 / 3 | per-provider `--parallel`. Lowered from the first-attempt 6/10 that made OpenAI rate-limit and Moonshot return empty content. Drop a provider's further if it still errors. |
| `SWEEP_RETRIES` | 2 | attempts per target per pass, to clear transient empties |
| `SWEEP_INCLUDE_PRO` | 0 | opt IN to the pro tier — it is the expensive one (~$10/target) |
| `MAX_TOKENS_MOONSHOT` | 32000 | output budget for the reasoning kimi models, so they stop truncating (`finish_reason=length`) |

The reasoning models run at a bigger `--max-tokens` automatically — 16000 for
fable, `MAX_TOKENS_MOONSHOT` (32000) for the kimi models — so their thinking
doesn't exhaust the 4096 default and return no answer.

### The targets

Per model: Vera full-spec, Vera spec-from-NL, Python, TypeScript. The
zero-training-data models (`matrix.py` `ztd=True`) additionally run Aver and
AILANG. Baselines (canonical solutions, no LLM) are run separately, once.

### Timing expectations

Moonshot dominates the wall-clock (slow provider, and lower parallelism for
reliability makes it slower still); a full multi-model sweep is an evening
plus overnight. Two v0.0.16-specific notes: reasoning-mode entries
(`openai-pro/*`) are latency-dominated and can run several times longer per
problem than their default-mode sibling, and per-provider rate limits mean
the practical speed-up comes from the per-provider parallelism above, not
from raising any single number.

### Output files

For model `M` at bench version `V` and compiler versions `VV` (Vera) / `AV` (Aver) / `LV` (AILANG):

| File | Contents |
|------|----------|
| `results/{M}-bench-{V}-vera-{VV}.jsonl` | Vera full-spec attempts |
| `results/{M}-spec-from-nl-bench-{V}-vera-{VV}.jsonl` | Vera spec-from-NL attempts |
| `results/{M}-python-bench-{V}.jsonl` | Python generation attempts |
| `results/{M}-typescript-bench-{V}.jsonl` | TypeScript generation attempts |
| `results/{M}-aver-bench-{V}-aver-{AV}.jsonl` | Aver generation attempts |
| `results/{M}-ailang-bench-{V}-ailang-{LV}.jsonl` | AILANG generation attempts |
| `results/{python,typescript,aver,ailang}-baseline.jsonl` | Canonical solution runs |
| `results/timing.json` | Per-target wall-clock + status for the most recent run |

Each JSONL line is **one attempt on one problem** — failed `vera check`/`aver
check` runs produce multiple lines per problem (the model is asked to fix
and retry). **There is no resume**: `vera-bench run` unlinks any existing
output file at startup (`vera_bench/cli.py`), so re-running the same
invocation re-runs every problem from scratch. A crashed sweep leaves a
partial JSONL for forensics, but recovering it means re-running that whole
model x target.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All targets passed |
| `1` | One or more targets failed, or missing API key / unknown model |

A failed target does **not** abort the rest — the script always runs all
ten, writes `timing.json` with each target's status, then exits non-zero
at the end if any failed. This makes partial-run recovery straightforward.

---

## `plot_results.py` — benchmark comparison chart

Produces `assets/results-graph.png`: a multi-panel chart showing
**% solved** (pass@1) across every model in the registry × four modes (Vera full-spec, Vera
spec-from-NL, Python, TypeScript) — solved over the gradeable set, so a refusal,
a compile failure, a runtime error and a wrong answer all count as not-solved.
This is the canonical chart shown in the top-level README.

> **Heads up:** the committed `assets/results-graph.png` is pinned to the
> **v0.0.7** data (to match the v0.0.7 narrative in the top-level
> README). Running `python scripts/plot_results.py` with no args will
> regenerate it from the *current* pyproject bench version, overwriting
> the pinned image. Don't commit that overwrite until the README
> narrative is rewritten against current-version data; regenerate the
> pinned image with `--version 0.0.7 --output assets/results-graph.png`
> to restore it.

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
| `--extra ailang` | `assets/results-graph_with-ailang.png` | ❌ gitignored |
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
(e.g. `claude-opus-4-8`, `moonshot-kimi-k2.6`). Dots in the version are
converted to dashes to match the filename convention; Anthropic's
4.6-generation dateless IDs (e.g. `claude-opus-4-8`) already match the
filename convention without conversion.

If multiple files match (e.g. the same model was re-run against a newer Vera
compiler), the most recently modified file wins. The Vera compiler version
displayed in the chart subtitle is auto-detected from the filenames of the
Vera full-spec results.

### Missing-file behaviour

If a file is missing, the script prints a warning like

```text
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
    ModelSpec("Claude Fable 5", "claude-fable-5", "fable"),
    ModelSpec("Claude Opus 4.8", "claude-opus-4-8", "opus"),
    ...
    ModelSpec("My New Model", "my-new-model-id", "sonnet"),
]
```

- `display` — shown on the chart (keep short, ~12 chars)
- `file_prefix` — the model-ID portion of the result filename (run
  `vera-bench run --model X ...` and inspect the resulting filename)
- `tier` — any key in `TIER_TITLES`: `"fable"` (ceiling), `"opus"`
  (flagship), `"sonnet"` (workhorse), plus the legacy `"flagship"` used by
  historical 2-tier data. This is purely a layout decision about which
  panel the model renders in. A tier not listed in `TIER_TITLES` still
  renders, in a trailing panel with a title-cased fallback name.

Row 1 renders **one panel per populated tier**, in `TIER_TITLES` order:
`fable`, `opus`, `flagship`, `sonnet`. The legacy `flagship` key sits
*between* `opus` and `sonnet` deliberately, so historical 2-tier renders
keep their original left-to-right order (Flagship, then Sonnet). Both the tier count and the models-per-tier count are
data-driven, so an incomplete row is fine — the v0.0.16 fable tier has two
entries because Moonshot ships no ceiling-above-flagship model. A tier with
no models is skipped entirely rather than rendering an empty panel.

### Adding a new mode

Add an entry to `MODE_PATTERNS` *and* add the colour to `COLORS`. The
three `plot_*` functions already accept dynamic mode lists via their
`comparison_modes` / `modes` parameters — no edits needed there. If the
new mode is Vera- or Aver-style (i.e. the result filename carries a
`-{compiler}-{version}` suffix), also add it to `_COMPILER_SUFFIXED` so
`_find_result_file` can resolve the glob pattern.

### Chart layout

Row 1 is **one panel per populated tier**, in `TIER_TITLES` order —
`fable`, `opus`, `flagship`, `sonnet` — followed by two full-width rows.
Both the tier count and the models-per-tier count are data-driven, so the
v0.0.16 matrix renders three tier panels and historical 2-tier data
renders two.

1. **Tier panels** (one per populated tier) — grouped bars for that
   tier's models across Vera + each comparison language
2. **"Does Vera beat …?"** — horizontal delta bars per model, one row per
   comparison language. The panel title is generated from the active
   comparison set, so the default chart shows *"Does Vera beat Python /
   TypeScript?"* and `--extra aver` extends it to *"Does Vera beat Python /
   TypeScript / Aver?"*. The x-axis auto-expands if deltas exceed ±22pp.
3. **All Models × All Modes** — grouped bars showing every mode
   (Vera, Vera NL, and the comparison languages) per model. Bar count per
   model grows with `--extra` flags; default is four.

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
<https://github.com/aallan/vera-bench/releases/download/v0.0.7/benchmark_v0.0.7.png>
(attached as a release asset — durable across tag or repo changes).

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

## `plot_slide.py` — talk-slide renderer

Renders result panels as **16:9 slides** sized and styled for
talk presentation (2880×1620 px, slide-readable typography from the back
of a room). Five slide types:

- `delta` — the "Does Vera beat Python / TypeScript?" horizontal-bar
  chart (the headline storytelling slide)
- `tiers` — per-tier comparison panels side-by-side (2 for historical
  2-tier data, 3 for the fable/opus/sonnet matrix)
- `all-modes` — every model × the 4 core modes in a single grouped-bar panel
- `ztd` — zero-training-data slide: Vera vs Aver vs AILANG on the models
  that ran those generation targets (opt-in; not part of `--type all`)
- `reasoning` — the reasoning-budget slide: one model at two reasoning
  modes (`standard` vs `pro`) (`REASONING_PAIR`, default `GPT-5.6 Sol` vs `GPT-5.6 Sol (pro)`)
  across every core mode, with the per-language delta annotated. Answers
  "does more deliberation help, and does it help *less* on Vera?" — the
  controlled comparison no other provider offers, since both entries are
  the same underlying model. Opt-in; needs both halves of the pair in
  the results directory

### Scope and lifecycle

The script renders against whichever lineup matches the `--version` you
ask for:

- `--version 0.0.7` uses the frozen `MODELS_V_0_0_7` lineup (Claude Opus 4
  / GPT-4.1 / Kimi K2.5 in flagship; Claude Sonnet 4 / GPT-4o / Kimi K2
  Turbo in sonnet). Those slides must keep rendering identically, and the
  live registry has moved on, so the historical lineup is pinned in code
  rather than reconstructed.
- **Any other version** uses the live `plot_results.MODELS`, so slides
  track the current matrix without further edits.

⚠ `--version` still **defaults to `0.0.7`**. A bare
`python scripts/plot_slide.py` therefore renders the frozen historical
lineup, not your current results — pass `--version` explicitly.

It reuses palette, typography constants, and `extract_data()` from
`plot_results.py` so the slide numbers match the README chart by
construction.

### Usage

```bash
# ⚠ --version defaults to 0.0.7, so a bare invocation renders the
# FROZEN historical lineup, not your current results. Pass it.
python scripts/plot_slide.py --version 0.0.16
# -> /tmp/vera-bench_slide_{delta,tiers,all-modes}.png

# The v0.0.7 talk slides, rendered against MODELS_V_0_0_7
python scripts/plot_slide.py --version 0.0.7

# Single slide type
python scripts/plot_slide.py --type delta

# Try a different background
python scripts/plot_slide.py --background cream

# Custom output path (only with single --type)
python scripts/plot_slide.py --type delta --output ~/Desktop/slide-3.png
```

### Backgrounds

| Choice | Hex | Notes |
|--------|-----|-------|
| `paper` (default) | `#FAF7F0` | Off-white; soft, neutral, doesn't compete with chart colours |
| `white` | `#FFFFFF` | Pure white; baseline / high contrast |
| `cream` | `#FEEAD1` | On-brand (veralang.dev palette); warmer |
| `light-grey` | `#F4F4F2` | Neutral, "corporate clean" |

All four are **light themes** — text/spine colours inherited from
`plot_results.py` work on any of them without inversion. A dark-mode
background isn't offered because it requires cascading text-colour
changes that are out of scope for the current talk's design.

### Output handling

Rendered PNGs default to `/tmp/` because they're **talk-prep ephemera**
that belong in the speaker's slide deck rather than the repo. The
gitignore covers `assets/vera-bench_slide_*.png` for the case where
someone explicitly outputs to `assets/` for preview — the canonical
artefact is the script itself, regeneration is cheap.

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
