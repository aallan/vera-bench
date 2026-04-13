# CLAUDE.md — VeraBench

VeraBench is a HumanEval/MBPP-style benchmark for [Vera](https://github.com/aallan/vera), a programming language designed for LLMs. It measures whether LLMs write better code in Vera than in Python, TypeScript, or other comparison languages (currently also [Aver](https://github.com/pchj/aver-lang)).

## Quick orientation

- **This repo** is the benchmark harness and problem set. It treats `vera` as a black-box CLI tool.
- **The Vera repo** (https://github.com/aallan/vera) is the compiler. Do not modify it from here.
- **DESIGN.md** has the design rationale: prior art, tier definitions, key decisions.
- **ROADMAP.md** has forward-looking milestones and open issues.
- **BRIEFING.md** is the original bootstrap document (kept for historical reference).
- **SKILL.md** is fetched from `https://veralang.dev/SKILL.md` at runtime (no local cache). Override with `--skill-md /path/to/local/SKILL.md`.
- **Aver's llms.txt** is fetched from `https://averlang.dev/llms.txt` at runtime (equivalent of SKILL.md for Aver).

## Vera installation

```bash
pip install git+https://github.com/aallan/vera.git
vera version   # should print vera 0.0.103 or later
```

## Problem structure

Problems live in `problems/tier{1-5}/` as JSON files. Canonical solutions live in `solutions/{vera,python,typescript,aver}/`. Each problem JSON has: `id`, `tier`, `title`, `description`, `description_neutral`, `signature`, `contracts`, `entry_point`, `tags`, `test_cases`, `vera_check_must_pass`, `vera_verify_tier1`, `notes`.

### `description` vs `description_neutral`

- **`description`** — Vera-specific problem description (references Vera types, slot references, contracts). Used for Vera full-spec and spec-from-NL prompts.
- **`description_neutral`** — Language-agnostic description. Used for Python, TypeScript, Aver, and any future comparison language. Equivalent in purpose to spec-from-NL descriptions — the model must infer its own language-specific constructs from the natural language description.

### The five tiers

1. **Pure arithmetic** — basic syntax, slot references, simple contracts
2. **String/array** — built-in function discovery (`domain_verb` naming)
3. **ADTs + match** — data type definition, exhaustive match, De Bruijn in match arms
4. **Recursion + termination** — `decreases` clauses, Z3 verification
5. **Multi-function + effects** — IO, State, Exn handlers, effect propagation

### Validation

Every canonical solution MUST pass:
```bash
vera check solutions/vera/VB-T1-001_absolute_value.vera   # must exit 0
vera verify solutions/vera/VB-T1-001_absolute_value.vera   # check tier breakdown
```

For problems with `test_cases`, also verify:
```bash
vera run solutions/vera/VB-T1-001_absolute_value.vera --fn absolute_value -- -42
# should output: 42
```

## Key Vera gotchas

- **De Bruijn indices**: `@Int.0` is the *nearest* (rightmost) Int binding. In `fn f(@Int, @Int -> @Int)`, `@Int.0` = second param, `@Int.1` = first param.
- **Every function** needs `requires()`, `ensures()`, `effects()`. No exceptions.
- **Braces are mandatory** on if/else branches: `if x then { a } else { b }`.
- **No elif** — nest if-then-else.
- **Recursive functions** need `decreases(expr)` or the checker rejects them.
- **effects(pure)** is required for functions with no side effects. Omitting it is an error.
- **Match arms** introduce new bindings: inside `Cons(@Int, @List)`, `@Int.0` refers to the matched head, not any outer parameter.
- **String contracts** fall to Tier 3 (runtime) — `string_length` is not SMT-verifiable. Set `vera_verify_tier1: false` for problems with string contracts.
- **State handlers**: `put`/`get` must be inlined in the `in { ... }` block. Calling a separate function with `effects(<State<T>>)` from inside a handler body causes a WASM codegen error.
- **`Exn<String>` doesn't work** — use `Exn<Int>` for exception values.
- **Bare `None`/`Err`** can fail type inference — use typed let bindings.

## Test case bool gotcha

`vera run` outputs booleans as `1`/`0` (WASM i32), not `true`/`false`. Test cases in problem JSONs use these integer values. When comparing against Python or TypeScript baselines:

- **Python**: String `"true"`/`"false"` in expected values must be normalised to Python `True`/`False` (see `_build_python_wrapper` in `baseline_runner.py`).
- **TypeScript**: Integer `1`/`0` expected values must use loose equality (`==` not `===`) because TypeScript returns native `boolean` and `true === 1` is `false` in strict mode.

Both issues have caused false baseline failures (VB-T4-003 for Python, VB-T1-006 for TypeScript).

## Comparison languages

### Adding a new comparison language

The pattern for adding a new language is established by the Python, TypeScript, and Aver implementations:

1. **Prompt builder** (`prompts.py`) — `build_{lang}_prompt()` that uses `description_neutral` + the language's reference doc
2. **Code evaluator** (`runner.py`) — `_evaluate_{lang}_code()` that writes code to a temp file, runs the compiler/interpreter, and checks output
3. **Baseline runner** (`baseline_runner.py`) — `run_{lang}_baseline()` for canonical solutions
4. **CLI integration** (`cli.py`) — add to `--language` choices
5. **Canonical solutions** (`solutions/{lang}/`) — one per problem
6. **Reference doc** — fetched at runtime (SKILL.md for Vera, llms.txt for Aver)

### Aver

[Aver](https://github.com/pchj/aver-lang) is a Haskell-inspired language with strong typing, similar zero-training-data properties to Vera. Its reference doc (`llms.txt`) is fetched from `https://averlang.dev/llms.txt`. The `aver` command must be on `$PATH`.

### Tier 5 cross-language caveat

Tier 5 problems test algebraic effect handlers in Vera (`State`, `Exn`, `IO`). Other languages solve these with native idioms (`try/except` in Python, `try/catch` in TypeScript, etc.). Cross-language T5 comparison is apples-to-oranges. See issue [#50](https://github.com/aallan/vera-bench/issues/50).

## Coding conventions

- Python 3.11+, type hints everywhere.
- `ruff` for linting.
- `click` for CLI.
- `rich` for terminal output.
- JSONL for results files.
- Subprocess calls to `vera` (and `aver`, `python`, `npx tsx`) with timeouts.

## Commands

```bash
vera-bench validate                    # check all problem JSONs + canonical solutions
vera-bench run --model MODEL           # run benchmark
vera-bench run --model MODEL --tier N  # run one tier
vera-bench run --model MODEL --language python      # Python LLM generation
vera-bench run --model MODEL --language typescript   # TypeScript LLM generation
vera-bench run --model MODEL --language aver         # Aver LLM generation
vera-bench baselines                   # run canonical Python baselines
vera-bench baselines --language typescript  # TypeScript baselines
vera-bench baselines --language aver       # Aver baselines
vera-bench report results/DIR/         # generate report
```
