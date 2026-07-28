# VeraBench

[![VeraBench: benchmarks for code the machines write](assets/vera-bench-social-preview.png)](https://veralang.dev)

[![CI](https://github.com/aallan/vera-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/aallan/vera-bench/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/aallan/vera-bench/graph/badge.svg)](https://codecov.io/gh/aallan/vera-bench)

A benchmark for evaluating LLM code generation in [Vera](https://github.com/aallan/vera), a programming language designed for large language models (LLMs) to write.

## Results

Six of the nine models score 100% in Vera, a language absent from every
training set, and they score no better in Python. Nine models, three providers,
all 60 problems across five difficulty tiers, against
[Vera v0.1.8](https://github.com/aallan/vera/releases/tag/v0.1.8).

### Vera against Python and TypeScript

![Vera minus Python and TypeScript, percentage points, per model](assets/fig-delta.png)

Against Python, Vera wins for six of the nine models by three to five points,
draws one and loses two. Against TypeScript it wins one, draws five and loses
three.

The asymmetry is not a property of Vera. TypeScript scores 100% for six of the
nine models and never drops below 97%, so there is no headroom left to win. A
benchmark on which two languages both sit at the ceiling is measuring the
models rather than the languages, which is the substance of the saturation
problem discussed below.

The losses are worth naming. Claude Opus 4.8 gives up five points against
Python and seven against TypeScript, the widest gap in the field, and Claude
Sonnet 5 loses a point and three. Both are Anthropic models, and both of the
clear wins (Claude Opus 5, GPT-5.6 Terra, five points each) sit beside them, so
this is not a vendor effect either way.

### Static typing is the variable

Python is dynamically typed, so a type error surfaces when the code runs.
TypeScript is statically typed and rejects the same error before anything runs.
Vera sits on the TypeScript side of that line and goes further, adding
contracts and a prover to the type check.

Group the three languages that way and the ordering stops looking odd. Vera
averages 98.7% across the nine models and TypeScript 99.7%, while Python trails
both at 96.7%. The two languages that constrain what a model may write before
it runs come out ahead of the one that waits until execution, and the
zero-training-data language is in that leading group despite nobody having
trained on it.

The failure modes line up with the same story. Python's failures land as
runtime wrong answers rather than compile rejections, thirteen against three
across the sweep; TypeScript has one of each. A loose language cannot reject a
bad program up front, so a model's mistake survives to execution and is
recorded as a wrong answer instead of being caught and handed back.

That grouping is what makes the Vera number interesting, because Vera is the
only one of the three that no model has read. TypeScript's 99.7% is earned with
an enormous amount of the language in every training set. Vera reaches 98.7%
with none of it, from a single document in the prompt. Whatever the models are
getting from familiarity with TypeScript, Vera appears to be supplying by other
means, and the obvious candidate is the structure it imposes: mandatory
`requires`, `ensures` and `effects` on every function, and typed slot
references in place of names the model would otherwise have to invent and keep
straight.

The zero-training-data comparison later on tests that directly, because it
holds exposure at zero for all three languages and varies only the design.
Vera takes 98.2% there against AILANG's 96.8% and Aver's 92.4%, and beats
Python's 97.0% on the same five models. The most constrained of the three
scores highest, which is what you would expect if constraint is doing the work
that familiarity does elsewhere. It does not make Vera faster or better than
TypeScript, and the delta chart says as much. It suggests the constraints are
worth roughly what a training corpus is worth, which is a stranger and more
useful result.

One caution about the size of that gap rather than its direction. Some of
Python's deficit is ours, not the models'
([#121](https://github.com/aallan/vera-bench/issues/121)): TypeScript is
structurally typed, so at the point where the grader builds a test value it
silently accepts an object carrying a field the model's type never declared,
where Python's constructor raises. On two problems the identical modelling
choice scored solved in TypeScript and not solved in Python. The direction of
this section holds; treat the three points as provisional until that is fixed.

### Full results

Each model runs the Vera problems twice, because there are two questions worth
asking.

The first run hands the model a full specification, meaning the type signature
and its contracts, and asks only for the body. That tests whether it can write
Vera. The second gives it the problem described in English and nothing more, so
it has to infer the types, author the contracts, and then write code that
satisfies them. That tests whether it understands Vera well enough to specify a
problem in it. The two columns below are those runs, and on the command line
they are the default and `--mode spec-from-nl`.

| Model | Vera | Vera NL | Python | TypeScript |
|---|---|---|---|---|
| Claude Fable 5 | **100%** | 97% | 97% | 97% |
| GPT-5.6 Sol (pro) | **100%** | 90% | 95% | **100%** |
| Claude Opus 5 | **100%** | 95% | 95% | **100%** |
| Claude Opus 4.8 | 93% | 93% | 98% | **100%** |
| GPT-5.6 Sol | 98% | 92% | 95% | **100%** |
| Kimi K3 | **100%** | 92% | **100%** | **100%** |
| Claude Sonnet 5 | 97% | 87% | 98% | **100%** |
| GPT-5.6 Terra | **100%** | 92% | 95% | **100%** |
| Kimi K2.6 | **100%** | 93% | 97% | **100%** |

Aver and AILANG ran for a five-model subset and are taken up in the two
zero-training-data sections at the end.

The Vera NL column is the one with real spread. It runs from 87% to 97% while
the other three bunch between 93% and 100%, and no model closes the gap. Writing code against a specification someone else wrote turns out to be a
materially easier task than deciding what the specification should say, and
that distance is the only measurement here with room left to move.

The charts below are described in [assets/README.md](assets/README.md) along
with the command to regenerate them.

> **On reading the numbers.** The charts report **% solved**: the model wrote
> code, it compiled, it ran, and the output matched. A refusal, a compile
> failure, a crash and a wrong answer all count the same way, as not solved.
> Single run per model, no pass@k. LLM output is non-deterministic and
> individual problems flip between runs. With 60 graded problems one problem is
> worth 1.7 percentage points, so most of the gaps reported here are one or two
> problems wide.

### Across model generations

![Three Claude flagships across four languages](assets/fig-generation.png)

Three consecutive Claude flagships, oldest to newest. Claude Opus 4 solved
fewer problems in Vera than in Python; Claude Opus 5 reverses that, and adds 11
points in Vera and 14 in Vera NL across the line while Python gains 2 and
TypeScript loses 4.

Only the last step is controlled. Claude Opus 4 was measured against an older
compiler, an older standard library, an earlier revision of the teaching
document and a smaller set of graded problems, so that step measures the Vera
ecosystem improving alongside the model, in unknown proportion. Claude Opus 4.8
and Claude Opus 5 were measured identically, on the same compiler, the same
prompt and all 60 problems, and that step moves the same way. One controlled
transition is suggestive rather than conclusive.

### Reasoning mode

![GPT-5.6 Sol at two reasoning modes, across four languages](assets/fig-reasoning.png)

One model, two reasoning modes, the same problems. How the model reasons is the
only variable.

The model is GPT-5.6 Sol. OpenAI's Responses API takes a `reasoning.mode`
parameter, and the two runs set it to `standard` and to `pro`; nothing else
differs.

`reasoning.mode` is a separate axis from `reasoning.effort`. Mode picks which
execution path the model takes, standard or pro. Effort controls how much
reasoning it does once it is on that path. This chart varies mode and leaves
effort at its default, so what it measures is the more thorough execution path
rather than simply a longer think on the same one.

Vera gains two points on the pro path and Vera NL loses two; Python and
TypeScript do not move at all. Whatever stops these models on the last one or
two problems is not something the pro path fixes, and Vera's standing does not
depend on the more expensive execution path, which matters because the pro
entry is the most costly run in the sweep. Null results on a saturated
benchmark are weak evidence: there is very little room left for anything to
move.

### Refusals

![Refusals by model and language](assets/fig-refusal.png)

There were four refusals across the whole run, every one of them in Python or
TypeScript and none in Vera, Aver or AILANG. The problems were unremarkable,
along the lines of dividing two numbers and guarding against a zero divisor,
and in each case the same model went on to solve the same problem in four or
five other languages.

All four came from Claude Fable 5 and Claude Opus 5, the two models in the
benchmark that ship cybersecurity classifiers. These refusals are therefore
likely to be false positives from those guardrails rather than anything to do
with the problems themselves.

### What the contracts cannot see

![The six programs that cleared vera check and still failed](assets/fig-coverage.png)

`vera check` and `vera run` are independent verdicts on the same program, which
makes every model-and-problem pair a two-by-two: the static gate passed or it
did not, the program was right or it was not. Two of those cells are agreement.
The other two bound what contracts buy you.

Across 539 graded pairs, six programs compiled, satisfied their contracts and
were still wrong; that is 1.1%. Of those six, one was caught at runtime by its
own postcondition, which is the safety net working rather than failing. One did
not terminate, having satisfied a `decreases` clause the checker accepted. The
remaining four are the honest limit: contracts bound what a program may do, and
they do not say everything it must do, so a program can satisfy everything it
promised and still compute the wrong answer.

Two of those four are the same problem, failed by two different models, and its
contracts are `requires(true)` and `ensures(true)`. A vacuous specification
proves nothing, and `vera check` passing against one means nothing either.

The number worth watching is the other cell, and it is zero. No working program
was refused. Nothing that ran correctly failed the static gate, and nothing
that failed the gate ran correctly.

### The benchmark is saturating

![Every model against every language, one dot each, on a zoomed axis](assets/fig-saturation.png)

Every model against every language, one dot each. The whole field sits between
87% and 100%, and all nine models reach 100% in at least one language. With 60
graded problems a single problem moves a score by 1.7 percentage points, so
most of the gaps discussed above are one or two problems wide.

This is the most serious limitation here. TypeScript scores 100% for six of the
nine models and Vera for six, so at the top of the range the problems are no
longer asking anything. The benchmark can still tell you that an unfamiliar
language costs a model nothing, which is the question it was built to answer,
but it can no longer rank the field. The next version needs harder problems.

### A controlled comparison

![Vera against Aver, both zero-training-data languages, five models](assets/fig-vera-vs-aver.png)

Comparing Vera to Python confounds two variables: the languages differ in
design, and they differ enormously when it comes to training data. Python is
common in the training data of all the models, and Vera is entirely absent.

[Aver](https://github.com/jasisz/aver) is another language designed for models
to write, and it removes the second. It is statically typed, absent from every
training set, and learned from a single document in the prompt, exactly the
same as Vera. [AILANG](https://ailang.sunholo.com/) is a third.

The biggest design difference between Vera and Aver is that Vera has no
variable names, using typed slot references instead. Vera scores higher than
Aver on all five models that ran both, by one to ten points, and higher than or
level with AILANG on all five.

This is the strongest evidence so far that the biggest design gamble in Vera,
the use of typed De Bruijn indexing, is doing real work. It is also the
comparison least affected by saturation, because none of the three languages is
at the ceiling.

### All three zero-training-data languages

![Vera against Aver and AILANG, five models](assets/fig-ztd.png)

Widening that comparison to all three languages nobody trained on. Every bar
here was earned from a single document in the prompt.

Vera leads Aver on all five models and AILANG on four, tying the fifth. On the
five-model average Vera takes 98.2%, AILANG 96.8% and Aver 92.4%, against
Python's 97.0% on the same five; two of the three beat Python outright.

This is the only comparison in the release that saturation has not eaten. None
of the three languages sits at the ceiling, so the gaps between them are wide
enough to survive a problem or two moving either way, which is more than can be
said for the Python and TypeScript columns.

## Overview

VeraBench measures whether LLMs write better code in a language designed for
them. Vera uses typed slot references instead of variable names, mandatory
contracts, and explicit algebraic effects; all features that should make
LLM-generated code more verifiable.

The benchmark covers five difficulty tiers:

| Tier | Focus | What it tests |
|------|-------|--------------|
| 1 | Pure arithmetic | Basic syntax, `@T.n` slot references, simple contracts |
| 2 | String & array ops | Built-in function discovery (`domain_verb` naming) |
| 3 | ADTs & match | Data type definition, De Bruijn indices in match arms |
| 4 | Recursion & termination | `decreases` clauses, Z3 verification |
| 5 | Multi-function & effects | IO, State, Exn, effect propagation across functions |

For each problem, we measure:

- **% solved (pass@1)**. The headline. Solved over the problems that can be
  output-graded, where a refusal, a compile failure, a runtime error and a
  wrong answer all count alike as not solved.
- **check@1**. Does the code pass `vera check` on first attempt?
- **verify@1**. Does it pass `vera verify` (Z3 contract verification)?
- **fix@1**. Given the error message, can the model fix it in one turn?
- **run_correct**. Does execution produce the correct output? Measured only
  over attempts that compiled, so it is not comparable across models that
  refuse or fail to compile at different rates. That is why the charts report
  % solved instead.

The same problems are also run in Python, TypeScript, [Aver](https://github.com/jasisz/aver), and [AILANG](https://ailang.sunholo.com/) as baselines. AILANG and Aver are zero-training-data languages, providing additional data points alongside Vera for the language-design-vs-training-data thesis.

> **Cross-language comparison:** For cross-language headline rates, use the T1–T4 aggregate. Tier 5 tests Vera's algebraic effect handlers, which other languages solve with fundamentally different native idioms. See [#50](https://github.com/aallan/vera-bench/issues/50).

## Prerequisites

* Python 3.11+
* Git
* Node.js 22+ *(optional, for TypeScript baselines and generation)*
* [Aver](https://github.com/jasisz/aver) *(optional, for Aver baselines and generation)*
* [AILANG](https://ailang.sunholo.com/) *(optional, for AILANG baselines and generation)*

## Installation

```bash
git clone https://github.com/aallan/vera-bench.git
cd vera-bench
python -m venv .venv
source .venv/bin/activate
pip install -e ".[llm]"
```

The `[llm]` extra installs the Anthropic and OpenAI SDKs. Use `pip install -e .` if you only need validation (no model evaluation).

### Install the Vera compiler

The `vera` command must be available on `$PATH`. Install it anywhere into the same environment, either from a local clone,

```bash
pip install -e /path/to/vera          
```

or directly from GitHub.

```bash
pip install git+https://github.com/aallan/vera.git   
```
Afterwards you should be able to print the Vera version from the terminal,

```bash
vera version   
```

this should return v0.1.8 or later. Vera 0.1.x changed several semantics the
benchmark depends on, so older compilers will fail validation.

## Running the benchmark

`vera-bench validate` checks all 60 problems and every canonical solution; run it first:

```bash
vera-bench validate
```

A single model against the Vera problems (full-spec mode) is one command:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
vera-bench run --model claude-sonnet-5
```

`vera-bench run` writes one JSONL row per problem attempt to `results/`, and has **no resume**, because it unlinks its output file at startup. It's the primitive; you don't drive a full multi-model run with it directly.

### The full sweep

A real run evaluates the whole model matrix (defined once in [`vera_bench/matrix.py`](vera_bench/matrix.py), and read by everything below) across every language target, and the workflow is shaped by the fact that LLM APIs are slow and flaky. Four scripts, used in order:

**1. Gate before you spend.** [`preflight.sh`](scripts/preflight.sh) checks every model id, provider auth, the request parameters each model accepts, and the Vera / Aver / AILANG toolchains, one problem per check. A couple of dollars against a sweep that is hours:

```bash
bash scripts/preflight.sh
```

**2. Run the sweep.** [`run_sweep.sh`](scripts/run_sweep.sh) runs the whole matrix (every model × its targets) in one terminal, provider streams concurrent. It is **idempotent**: it skips any target already on disk and clean and re-runs the rest, so a killed or rate-limited sweep is recovered simply by running it again. The expensive pro tier is opt-in:

```bash
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... MOONSHOT_API_KEY=...
SWEEP_INCLUDE_PRO=1 bash scripts/run_sweep.sh
```

Its terminal goes quiet mid-target; it pipes each run through `tee`, and the progress bar blanks when it's not on a real terminal. That's expected, not a hang; watch it with the next tool instead.

**3. Watch the scoreboard.** [`sweep_status.py`](scripts/sweep_status.py) reads the JSONL rows directly (the only reliable live signal) and separates a **transient** failure that should be re-run (rate-limit, timeout, empty content) from a **real result** that should be kept (a refusal, a compile error, a wrong answer):

```bash
SWEEP_INCLUDE_PRO=1 python scripts/sweep_status.py
```

**4. Repair transient failures surgically.** When a target is complete except for a few blips, [`rerun_failed.py`](scripts/rerun_failed.py) re-runs *only those problems* and splices them back, instead of re-running all 60 (drop `--apply` to preview):

```bash
python scripts/rerun_failed.py --model moonshot/kimi-k2.6 --mode full-spec --apply
```

Loop steps 3–4 until the scoreboard reads all-clean. See [`scripts/README.md`](scripts/README.md) for the full stage breakdown, env tunables, and the infrastructure-vs-model definition of "clean".

### Re-grading without re-running

Every result row records the path to the code the model actually wrote, under
`results/code/`. When a grading bug is found after a sweep,
[`regrade.py`](scripts/regrade.py) replays that stored code through the
evaluators and rewrites the verdicts, which turns a paid overnight re-run into
a few minutes of local subprocesses:

```bash
python scripts/regrade.py                 # census, changes nothing
python scripts/regrade.py --apply         # rewrite the verdicts
```

It re-grades every row rather than only the ones a fix was expected to help,
because grading only the latter would import every improvement while hiding any
regression the same change caused. Only verdict fields are replaced; token
counts, timings and model identity describe the original run and are carried
through untouched.

### Baselines

Canonical-solution reference runs; no model, no API key, one per comparison language:

```bash
vera-bench baselines                        # python (default)
vera-bench baselines --language typescript
vera-bench baselines --language aver
vera-bench baselines --language ailang
```

### Targeted runs

For iterating on one problem or mode rather than a full sweep:

```bash
vera-bench run --model claude-sonnet-5 --tier 1            # one tier
vera-bench run --model claude-sonnet-5 --problem VB-T1-001 # one problem
vera-bench run --model claude-sonnet-5 --mode spec-from-nl # agent writes its own contracts
vera-bench run --model claude-sonnet-5 --language python   # Python (or typescript/aver/ailang)
vera-bench run --model moonshot/kimi-k2.6 --parallel 10    # concurrent dispatch for slow models
```

Supported providers: [Anthropic](https://anthropic.com) (Claude), [OpenAI](https://openai.com) (GPT), [Kimi](https://platform.kimi.ai) (Moonshot), and [OpenRouter](https://openrouter.ai/). Set the matching key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MOONSHOT_API_KEY`, or `OPENROUTER_API_KEY`).

The Vera language reference ([SKILL.md](https://veralang.dev/SKILL.md)) is fetched from veralang.dev at run time. Use a local copy (for testing unreleased language features, say) with `--skill-md /path/to/SKILL.md`.

## Report generation

Running `vera-bench report results/` generates `results/summary.md` with a summary table, per-tier breakdowns, and per-problem detail. Each `vera-bench run` writes incremental JSONL results (one line per problem attempt), so a run that stops early is still reportable up to the problem it reached.

The headline chart comes from [`scripts/plot_results.py`](scripts/plot_results.py): **% solved** (pass@1) per model × mode over the gradeable problem set. [`scripts/README.md`](scripts/README.md) documents it plus the 16:9 talk-slide renderer.

> **There is no resume.** `vera-bench run` deletes any existing output file for that model × language × mode before it starts, so re-running an interrupted target repeats it from problem 1 rather than topping it up. Filenames carry no timestamp, so the old results are gone. Budget a full re-run for any target that does not finish.

Results files are in `.gitignore`; they are generated artefacts, not checked in.

## Prior art

VeraBench is inspired by:

- [HumanEval](https://github.com/openai/human-eval), 164 Python function completion problems
- [MBPP](https://github.com/google-research/google-research/tree/master/mbpp), 974 Python problems from natural language
- [DafnyBench](https://github.com/sun-wendy/DafnyBench), 782 Dafny verification annotation problems

DafnyBench demonstrated that tracking verification success rates over time attracts genuine research attention; success rates went from 68% to 96% across model generations in under two years. VeraBench aims to create the same longitudinal story for a language designed from scratch for LLM code generation.

## Citation

```bibtex
@software{verabench2026,
  author = {Allan, Alasdair},
  title = {VeraBench: a benchmark suite for LLM code generation in Vera},
  year = {2026},
  url = {https://github.com/aallan/vera-bench}
}
```

## License

VeraBench is licensed under the [MIT License](LICENSE).

Copyright © 2026 Alasdair Allan

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
