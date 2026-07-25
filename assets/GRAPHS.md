# The v0.0.16 graphs

What each chart says, and why it matters. The commands regenerate them from
the JSONL rows in `results/`.

## Summary

Vera now edges Python and TypeScript at the frontier, 99.0% against 98.0% and
98.4%. That headline is the least interesting number here. It is a margin of
about one problem, on a metric that has run out of room; eight of the nine
models score 100% in at least one language.

The findings worth the time are underneath it. Models refuse to write code in
the languages they know and never in the ones they don't. Vera beats Aver on
every model tested, which is the closest thing to a controlled experiment in
language design the benchmark contains. And the newest Anthropic flagship is
the first to write Vera better than it writes Python.

## The documentation chart (results-graph.png)

At the top of the range the languages have converged. Vera averages 99.0%
across the nine models, TypeScript 98.4%, Python 98.0%, and the spread from
best to worst language is smaller than the spread between two runs of the same
model. Frontier models can now write a language they have never seen about as
well as they write the two they have seen most. That is the result; the
ordering within it is close to noise.

```bash
python scripts/plot_results.py
```

## Where we started (results-graph_v0.0.7.png and results-graph_v0.0.9.png)

Nine months ago the answer was the opposite. In the v0.0.7 sweep Claude
Sonnet 4 solved 17 percentage points fewer problems in Vera than in Python,
GPT-4o 15 fewer, Claude Opus 4 8 fewer. Only Kimi K2.5 came out ahead. Read
against the current chart, this is the strongest evidence in the repository
that the early gap was a training-data effect rather than anything about the
language: the language barely changed, the models did, and the deficit
closed and then reversed.

```bash
python scripts/plot_results.py --version 0.0.7
python scripts/plot_results.py --version 0.0.9
```

## Where Vera actually wins (vera-bench_slide_delta.png)

Vera beats Python for four of the nine models, ties three and loses two, so
the advantage is real but it is not uniform. It is also not spread evenly:
Claude Fable 5 and Claude Opus 5 account for almost all of it, at +6 and +6
against Python. Both are the newest models from one vendor, and both are
models that refused to answer problems in Python. The advantage, where it
exists, sits at the frontier.

```bash
python scripts/plot_slide.py --version 0.0.16 --type delta
```

## Capability is not the variable (vera-bench_slide_tiers.png and vera-bench_slide_all-modes.png)

Splitting by capability tier shows how little capability now explains.
Claude Sonnet 5, Kimi K2.6 and GPT-5.6 Terra are the workhorse models, and
they solve 97% to 100% of the gradeable problems in Vera. Writing a
zero-training-data language used to be a frontier trick; it is now something
the mid-tier does. Where the tiers still separate is the spec-from-NL mode,
where the model writes its own contracts before writing any code, and
Sonnet 5 drops to 89%.

```bash
python scripts/plot_slide.py --version 0.0.16 --type tiers
python scripts/plot_slide.py --version 0.0.16 --type all-modes
```

## Training data is not the variable either (vera-bench_slide_ztd.png)

Vera, Aver and AILANG appear in no model's training data, so every point on
this chart was earned from a document in the prompt. Vera averages 98.8%
across the five models that ran all three, ahead of Python's 98.0% on the
same five. AILANG manages 99.4% and Aver trails at 93.2%. Whether a model
can write a language turns out to have very little to do with how much of
that language it has read, which is the premise the whole benchmark was
built to test.

```bash
python scripts/plot_slide.py --version 0.0.16 --type ztd
```

## Naming things is the variable (vera-bench_slide_ztd-vera-aver.png)

This is the closest the benchmark gets to a controlled experiment. Vera and
Aver are both zero-training-data languages, both statically typed, both
learned from a single document in the prompt, so neither gets the advantage
of familiarity. The design choice that separates them is that Vera has no
variable names at all, using De Bruijn indices where Aver uses ordinary
bindings.

Vera wins on all five models: 100 against 94, 94 against 92, 100 against 94,
100 against 92, 100 against 94. Not one model does better with names than
without them. Removing variable names, the decision that reads as the most
hostile to human authors, is the decision the models reward.

```bash
python scripts/plot_slide.py --version 0.0.16 --type ztd --ztd-modes "Vera,Aver"
```

## Thinking longer does not help (vera-bench_slide_reasoning.png)

GPT-5.6 Sol ran twice, at standard and at pro reasoning, same problems, same
prompt, deliberation the only thing that changes. The deltas are 0, -2, 0
and 0. Whatever is stopping these models from solving the last two or three
problems, more thinking time is not the answer to it, and that holds in
Python as firmly as it does in Vera.

```bash
python scripts/plot_slide.py --version 0.0.16 --type reasoning
```

## Models refuse in the languages they know (vera-bench_slide_refusal.png)

Five refusals in the whole sweep. Every one of them in Python or TypeScript;
none at all in Vera. In each case the same model went on to solve
the same problem in four or five other languages, so this is about what the
models were willing to write and not about what they could write. The
refused problems include computing a divided by b and returning -1 on
division by zero, and finding the largest of the integers 1 through n.

All five come from two models, Claude Fable 5 and Claude Opus 5. The vendor
does not explain that. Two other Anthropic models ran the same sweep, Claude
Opus 4.8 and Claude Sonnet 5, and neither refused anything.

What separates the pair that did is that both ship cyber classifiers.
Anthropic's [Opus 5 announcement](https://www.anthropic.com/news/claude-opus-5)
describes that model's as "proportionally less restrictive than those on
Fable 5", and expects them to intervene far less often. The two models
carrying the classifiers are precisely the two that refused, and they refused
in the order the classifiers imply: Fable 5 three times, Opus 5 twice, the
other two not at all.

So the reading is that the strictest safety tuning is also the most prone to
false positives, and that those false positives only fire in the languages a
model has actually read. A language absent from the training data inherits
none of them. Five refusals cannot test how much less often one classifier
fires than another, so this is a pattern rather than a finding.

```bash
python scripts/plot_narrative.py --version 0.0.16 --type refusal
```

## The direction of travel (vera-bench_slide_generation.png and vera-bench_slide_generation-controlled.png)

Across three Anthropic flagships, Vera goes 89, 94, 100 and spec-from-NL goes
81, 94, 100, while Python goes 94, 100, 94 and TypeScript 100, 100, 94. Each
new model writes Vera better than the last, and the two mainstream languages
have stopped improving.

The 4.8 to 5 step is the one to trust, because it is the only one where
nothing but the model changed: +6 for Vera, +6 for spec-from-NL, -6 for
Python and -6 for TypeScript. Claude Opus 5 is the first model in this
benchmark that writes Vera better than it writes Python. The earlier step
spans a compiler, a stdlib and a SKILL.md revision, so it measures Vera and
the models improving together.

```bash
python scripts/plot_narrative.py --version 0.0.16 --type generation
python scripts/plot_narrative.py --version 0.0.16 --type generation --pair-only
```

## The benchmark is running out (vera-bench_slide_saturation.png)

Every model against every language, one dot each. The whole field sits
between 89% and 100%, most of it against the ceiling, and with 36 gradeable
problems a single problem moves a score by 2.8 points. Most of the gaps in
the delta chart are therefore one or two problems wide. That is a fact about
the problem set. At this difficulty it can no longer separate the models, and
the next version needs harder ones.

```bash
python scripts/plot_narrative.py --version 0.0.16 --type saturation
```

## What the headline metric misses (vera-bench_slide_coverage.png)

24 of the 60 problems have no test cases, because 20 of them take a list,
tree, array or ADT as an argument and `vera run` passes arguments on a
command line. Those 24 are concentrated in the ADT, match and effect tiers,
which is exactly the machinery Vera's contracts and prover exist to check. So
pass@1, the number every chart here leads with, is blind to the 40% of the
problem set where Vera does the thing it was built to do, and it grades
everyone on the subset that suits Python best. Vera still checks and verifies
all 24, at 100% and 100% across the nine models.

```bash
python scripts/plot_narrative.py --version 0.0.16 --type coverage
```
