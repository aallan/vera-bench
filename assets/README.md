# assets/

The images this repository renders, and what they mean. Everything else the
plotting scripts can produce is generated on demand and stays out of the
history; see [Generated, not committed](#generated-not-committed).

Every score chart reports **% solved**: the model wrote code, it compiled, it
ran, and the output matched. A refusal, a compile failure, a crash and a wrong
answer all count alike, as not solved. `fig-coverage.png` is the exception; it
counts problems rather than scoring them. Only 36 of the 60 problems can be
graded that way, so one problem is worth 2.8 percentage points. Keep that
number in mind when reading any gap.

## The seven README figures

Rendered `--bare` and transparent: no title, no subtitle, no footnote, cropped
to the plot, so the prose around them carries what the slide versions bake in.
They are committed because a README image has to be in the repository to
render, which is why they sit outside the `vera-bench_slide_*` naming that
`.gitignore` excludes.

### `fig-delta.png`: Vera against Python and TypeScript

Vera's score minus each comparison language, one row per model, green to the
right. Vera wins outright for four of the nine models and draws level with
three more. The wins are not evenly spread: Claude Fable 5 and Claude Opus 5
carry most of them, and both are models that refused to answer problems in
Python.

### `fig-vera-vs-aver.png`: a controlled comparison

Comparing Vera to Python confounds design against training data: Python is
common in every training set and Vera is absent from all of them.
[Aver](https://github.com/jasisz/aver) is another language designed for models
to write, and it removes that difference. The biggest design difference left is
that Vera has no variable names, using typed slot references. Vera scores
higher on all five models that ran both.

### `fig-generation.png`: the direction of travel

Three Claude flagships across four languages. Claude Opus 4 solved fewer
problems in Vera than in Python; Claude Opus 5 reverses that. Both Vera modes
rise at every step, while Python and TypeScript end where they started or
below. Only the last step is controlled; the earlier one spans a compiler, a
standard library and a revision of the teaching document, so it measures the
ecosystem improving alongside the models, in unknown proportion.

### `fig-reasoning.png`: reasoning mode

GPT-5.6 Sol at `reasoning.mode` standard and pro, same problems, same prompt.
Mode picks which execution path the model takes; `reasoning.effort`, a separate
axis, controls how much reasoning it does once on that path, and this chart
varies mode alone. Nothing moves in any of the four languages.

### `fig-refusal.png`: refusals

A model by language grid. Five refusals in the whole run, every one of them in
Python or TypeScript and none in Vera, and in each case the same model went on
to solve the same problem in four or five other languages. All five came from
Claude Fable 5 and Claude Opus 5, the two models in the benchmark that ship
cybersecurity classifiers, so these are likely false positives from those
guardrails rather than anything to do with the problems themselves.

### `fig-coverage.png`: what the headline metric cannot see

Which of the 60 problems are scored by comparing output, and which are not. 24
are not, because Vera is the only language here invoked without a generated
wrapper: `vera run --fn` passes arguments on a command line, so a problem whose
input is a list or a tree cannot be called at all. Those 24 are the ADT, match
and effect problems, so the score is measured on the part of the set where the
languages are most alike. Tracked in
[#107](https://github.com/aallan/vera-bench/issues/107).

### `fig-saturation.png`: the benchmark is saturating

Every model against every language, one dot each, on a zoomed axis. The field
sits between 92% and 100% on the core languages and all nine models reach 100%
in at least one of them, so with 36 graded problems most gaps are one or two
problems wide. The benchmark can still answer whether an unfamiliar language
costs a model anything; it can no longer rank the field at the top.

### Regenerating them

```bash
V=0.0.16
python scripts/plot_slide.py --version $V --type delta --bare \
  --background transparent --output assets/fig-delta.png
python scripts/plot_slide.py --version $V --type ztd --ztd-modes "Vera,Aver" \
  --bare --background transparent --output assets/fig-vera-vs-aver.png
python scripts/plot_slide.py --version $V --type reasoning --bare \
  --background transparent --output assets/fig-reasoning.png
python scripts/plot_narrative.py --version $V --type generation --bare \
  --background transparent --output assets/fig-generation.png
python scripts/plot_narrative.py --version $V --type refusal --bare \
  --background transparent --output assets/fig-refusal.png
python scripts/plot_narrative.py --version $V --type coverage --bare \
  --background transparent --output assets/fig-coverage.png
python scripts/plot_narrative.py --version $V --type saturation --bare \
  --background transparent --output assets/fig-saturation.png
```

⚠ These carry dark brown text, which suits a light page and the cream section
on veralang.dev. On a dark background they will be hard to read.

## The other committed images

| File | What it is |
|---|---|
| `results-graph.png` | The canonical full chart: three tier panels, the delta chart, and every model against all four core modes. A reference view, and the only committed chart that keeps its own titles. `python scripts/plot_results.py` |
| `vera-bench-social-preview.png` | The README masthead and the GitHub social card. Not generated by the plotting scripts. |

## Generated, not committed

The scripts are the artefact; regenerating is cheap, so the output stays out
of the history. `.gitignore` covers `assets/results-graph_*.png`,
`assets/benchmark_*.png`, `assets/vera-bench_slide_*.png` and
`assets/GRAPHS.md`.

**Talk slides.** Full 16:9, 2880x1620, with titles and captions, sized to read
from the back of a room. `plot_slide.py` renders `delta`, `tiers`,
`all-modes`, `ztd` and `reasoning`; `plot_narrative.py` renders `refusal`,
`generation`, `saturation` and `coverage`.

```bash
python scripts/plot_slide.py --version 0.0.16 --type tiers \
  --output assets/vera-bench_slide_tiers.png
python scripts/plot_narrative.py --version 0.0.16
```

Three have no committed counterpart. **tiers** and **all-modes** are
per-capability-tier and per-mode reference views of numbers the other charts
already carry. **ztd** is the three-language zero-training-data slide, Vera
against Aver against AILANG; the committed `fig-vera-vs-aver.png` is the
two-language cut of it, which is what the README argues from.

**Historical charts.** Earlier sweeps render against the lineup that actually
ran them, which `plot_results.py` keeps in `HISTORICAL_LINEUPS`. If a version
has no matching result files the script exits non-zero rather than writing an
empty chart.

```bash
python scripts/plot_results.py --version 0.0.7   # -> results-graph_v0.0.7.png
python scripts/plot_results.py --version 0.0.9   # -> results-graph_v0.0.9.png
```

## Colour

The palette is the veralang.dev brand, and it does not pass a colourblind
audit on two pairs: Vera green against Python orange at ΔE 4.4 under
protanopia, and Vera green against AILANG magenta at ΔE 2.1 under
deuteranopia. The first cannot be fixed by reassignment, because green against
orange is the red-green axis and it is exactly the comparison the benchmark
exists to make. So identity never rests on colour alone: every bar carries a
fixed texture, every dot a fixed marker shape, and every mark its own printed
value. The full audit and the palette table are in
[`scripts/README.md`](../scripts/README.md).
