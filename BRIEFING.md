# VeraBench: Briefing Document for Claude Code

This document provides everything a Claude Code instance needs to bootstrap the `vera-bench` repository — the benchmark suite for Vera (GitHub issue [aallan/vera#225](https://github.com/aallan/vera/issues/225)).

---

## 1. What This Is

VeraBench is a HumanEval/MBPP-style benchmark adapted for Vera, a programming language designed for LLMs to write. The benchmark measures whether LLMs write better code in Vera than in existing languages — the core thesis of the entire Vera project.

The benchmark lives in its own repository (`aallan/vera-bench`), separate from the compiler (`aallan/vera`). It treats `vera` as a black-box CLI tool: `vera check`, `vera verify`, `vera run`. No compiler internals are imported.

### Why separate repos

- The benchmark is a **research artifact** with its own publication trajectory, citation, and versioning. "VeraBench v1.0 evaluated against vera v0.0.103" needs to be a clean sentence.
- The **software is structurally different**: the compiler is parse→typecheck→verify→compile; the benchmark is prompt→call-LLM-API→capture-output→run-vera-subprocess→collect-metrics.
- Different **dependency trees**: the benchmark needs LLM API clients (anthropic, openai, etc.), the compiler doesn't. The benchmark's CI calls LLM APIs (expensive, slow) — keep that out of compiler CI.
- Different **contributor profiles**: researchers running evaluations vs. people submitting compiler patches.

### Prior art

| Benchmark | Problems | Language | Task | Key metric |
|-----------|----------|----------|------|------------|
| **HumanEval** (OpenAI, 2021) | 164 | Python | Function completion from docstring | pass@k |
| **MBPP** (Google, 2021) | 974 | Python | Function from NL description + 3 tests | pass@1 |
| **DafnyBench** (Loughridge et al., 2024) | 782 | Dafny | Fill in verification annotations | success rate, with retry on error feedback |
| **VerifyThisBench** (Deng et al., 2025) | ~150 | Dafny/Lean/Coq | End-to-end: spec + code + proof from NL | success rate after N feedback rounds |
| **CLEVER** (Thakur et al., 2025) | 161 | Lean | Spec equivalence + implementation correctness | pass@k-seconds |
| **VERINA** (Ye et al., 2025) | 189 | Lean | Spec + code + proof generation | pass@1 per subtask |

**The DafnyBench trajectory is the model to follow.** In June 2024, Claude 3 Opus achieved 68% on DafnyBench. By early 2026, Claude Opus 4.1 reached 89% and newer models hit 96%. Tracking this trajectory over model releases attracted genuine research attention. VeraBench should create the same longitudinal story for Vera.

**Key design lessons from prior benchmarks:**

- HumanEval: JSONL format with `task_id`, `prompt`, `canonical_solution`, `test`, `entry_point`. Simple, widely adopted. Problems are hand-crafted to avoid training data contamination.
- MBPP: Each problem has `text` (NL description), `code` (solution), `test_list` (3 assert statements). Entry-level difficulty with natural language prompts.
- DafnyBench: `ground_truth/` and `hints_removed/` directories. Evaluation = ask model to reconstruct hints, check if Dafny verifier passes. Retry with error feedback. Measures success rate vs. program length and annotation quantity.
- DafnyBench limitation (noted in their paper): does **not** assess translation from natural language to formal specs — only hint reconstruction. VeraBench should do both.

---

## 2. What Vera Is (The Minimum You Need)

Vera is a statically typed, purely functional language with:

- **Typed slot references** (`@T.n`) instead of variable names — De Bruijn indices. `@Int.0` is the nearest `Int` binding, `@Int.1` is the next one out.
- **Mandatory contracts** — every function has `requires()`, `ensures()`, `effects()`.
- **Algebraic effects** — `IO`, `Http`, `State<T>`, `Exn<T>`, `Async`, `Inference` (LLM calls).
- **Three verification tiers** — Tier 1: Z3 proves the contract statically. Tier 3: contract compiled as runtime check. (Tier 2 specified but not yet implemented.)
- **122 built-in functions** following predictable `domain_verb` naming (e.g. `string_length`, `array_map`, `json_parse`).
- **ADTs + exhaustive match** — `data List<T> { Nil, Cons(T, List<T>) }`.
- **Termination proofs** — recursive functions need `decreases(@T.n)`.

### Vera toolchain commands relevant to the benchmark

```bash
vera check file.vera              # Parse + type-check → exit 0 if OK
vera check --json file.vera       # JSON diagnostics with error codes
vera verify file.vera             # Type-check + Z3 contract verification
vera verify --json file.vera      # JSON with tier1_verified/tier3_runtime counts
vera run file.vera                # Compile + execute
vera run file.vera --fn f -- 42   # Call specific function with argument
vera test file.vera               # Contract-driven testing via Z3 + WASM
vera fmt --check file.vera        # Check canonical formatting
```

### Vera function anatomy

```vera
public fn safe_divide(@Int, @Int -> @Int)
  requires(@Int.1 != 0)                    -- precondition
  ensures(@Int.result == @Int.0 / @Int.1)  -- postcondition
  effects(pure)                             -- effect declaration
{
  @Int.0 / @Int.1                           -- body
}
```

### The SKILL.md

The compiler repo contains `SKILL.md` (65KB) — the complete language reference that agents use when writing Vera. The benchmark harness feeds this to the LLM as context. It is also served at `https://veralang.dev/SKILL.md`.

### Known limitations to avoid in benchmark problems

- `vera test` can only generate inputs for `Int`, `Nat`, `Bool`, `Byte` parameters (not String, Float64, or compound types) — issue #169.
- Bare `None`/`Err` in generic call positions can fail type inference — issue #293. Work around with `let` bindings.
- `Exn<String>` handler tag fails (use `Exn<Int>` instead) — issue #416.
- Nested `handle[State<T>]` of the same type share state — issue #417.
- `map_new()` / `set_new()` need type context.

---

## 3. The Five Difficulty Tiers

Each tier is designed to test specific aspects of LLM code generation that are unique to Vera.

### Tier 1: Pure Arithmetic

**What it tests:** Can the agent produce syntactically valid Vera? Does it understand `@T.n` slot references, mandatory contracts, and `effects(pure)`?

**Problem shape:** 1–2 parameters, simple arithmetic, contracts that Z3 can verify (Tier 1 verification).

**Example problems:**
- `absolute_value`: `@Int -> @Nat`, ensures `@Nat.result >= 0`.
- `clamp`: `@Int, @Int, @Int -> @Int`, requires `@Int.1 <= @Int.2`, ensures result in range.
- `max_of_three`: `@Int, @Int, @Int -> @Int`, ensures result >= all three inputs.
- `is_positive`: `@Int -> @Bool`, ensures `@Bool.result == (@Int.0 > 0)`.
- `safe_modulo`: `@Int, @Int -> @Int`, requires `@Int.1 != 0`.
- `signum`: `@Int -> @Int`, ensures result is -1, 0, or 1.
- `sum_to_n`: `@Nat -> @Nat`, with `decreases` clause.
- `distance`: `@Int, @Int -> @Nat`, ensures `@Nat.result == abs(@Int.0 - @Int.1)`.

**What distinguishes Vera from Python here:** The agent must get the slot indices right (e.g. in `add(@Int, @Int -> @Int)`, `@Int.1` is the first param, `@Int.0` is the second — rightmost is 0). Must include `requires`/`ensures`/`effects`. Must use `if ... then { ... } else { ... }` (braces mandatory).

### Tier 2: String and Array Manipulation

**What it tests:** Can the agent discover the right built-in function names? Vera uses `domain_verb` naming: `string_length`, `string_concat`, `string_slice`, `array_map`, `array_filter`, `array_fold`. An agent that guesses `len()` or `str.concat()` will fail.

**Example problems:**
- `is_palindrome`: `@String -> @Bool`, using `string_length`, `string_slice`, `string_reverse` (note: check if `string_reverse` exists — it may need to be built from `string_slice`).
- `word_count`: `@String -> @Nat`, using `string_split`.
- `sum_array`: `@Array<Int> -> @Int`, using `array_fold`.
- `filter_positives`: `@Array<Int> -> @Array<Int>`, using `array_filter`.
- `reverse_array`: `@Array<Int> -> @Array<Int>`, build from `array_slice` and indexing.
- `join_strings`: `@Array<String>, @String -> @String`, using `string_join`.
- `contains_substring`: `@String, @String -> @Bool`, using `string_contains`.
- `unique_elements`: `@Array<Int> -> @Array<Int>`, using `Set` operations.
- `map_to_strings`: `@Array<Int> -> @Array<String>`, using `array_map` and `int_to_string` (note: it's `to_string`, not `int_to_string`... **double-check SKILL.md**).
- `count_if`: `@Array<Int> -> @Nat`, count elements satisfying a predicate using `array_filter` + `array_length`.

**What distinguishes Vera here:** Built-in function names are predictable but not identical to any other language. The agent needs to have read and internalised the SKILL.md naming conventions.

### Tier 3: ADTs and Pattern Matching

**What it tests:** Can the agent define custom data types, write exhaustive match expressions, and correctly use De Bruijn indices inside match arms (where new bindings shift the indices)?

**Example problems:**
- `list_length`: Define `data List<T> { Nil, Cons(T, List<T>) }`, compute length with `decreases`.
- `list_sum`: Sum a `List<Int>`.
- `list_map`: Map a function over a `List<T>` (requires `forall<A, B>`).
- `tree_depth`: Define `data Tree<T> { Leaf(T), Branch(Tree<T>, Tree<T>) }`, compute depth.
- `tree_sum`: Sum all values in a `Tree<Int>`.
- `option_chain`: `@Option<Option<Int>> -> @Option<Int>`, flatten nested options.
- `list_filter`: Filter a `List<Int>` by predicate.
- `eval_expr`: Define `data Expr { Lit(Int), Add(Expr, Expr), Neg(Expr) }`, evaluate to `Int`.
- `zip_lists`: `@List<Int>, @List<String> -> @List<Tuple<Int, String>>` (or use a custom Pair ADT).
- `find_first`: `@List<Int> -> @Option<Int>`, return first element matching a predicate.

**What distinguishes Vera here:** Inside a `match` arm like `Cons(@Int, @List<Int>) -> ...`, the matched bindings introduce new slots. The `@Int.0` inside the arm refers to the matched `Int` from `Cons`, not any parameter. This is where De Bruijn indices genuinely test the model's understanding.

### Tier 4: Recursive Functions with Termination Proofs

**What it tests:** Can the agent write provably terminating recursive functions? The `decreases` clause must name an expression that gets strictly smaller on each recursive call. This is the first tier where Z3 verification matters for the benchmark (verify rate).

**Example problems:**
- `fibonacci`: `@Nat -> @Nat` with `decreases(@Nat.0)`.
- `gcd`: `@Nat, @Nat -> @Nat` with Euclidean algorithm, `decreases(@Nat.1)` (or appropriate measure).
- `binary_search_count`: Count occurrences in a sorted array segment, `decreases(@Int.1 - @Int.0)`.
- `merge_sort_list`: Sort a `List<Int>`, needs lexicographic `decreases`.
- `ackermann` (partial): Show that Diverge effect is needed when termination can't be proved.
- `power`: `@Nat, @Nat -> @Nat`, fast exponentiation with `decreases(@Nat.1)`.
- `flatten_tree`: `@Tree<Int> -> @List<Int>` with `decreases(@Tree<Int>.0)`.
- `mutual_recursion`: `is_even`/`is_odd` with `where` blocks and `decreases` on both.
- `insertion_sort`: Sort a `List<Int>`, with helper `insert` having its own `decreases`.
- `collatz_steps`: Requires `effects(<Diverge>)` because termination is unproven.

**What distinguishes Vera here:** No other mainstream language requires termination proofs. An agent that writes recursive code without `decreases` gets a type error. An agent that writes a wrong `decreases` expression gets a verification failure.

### Tier 5: Multi-Function Programs with Effects

**What it tests:** Cross-function contract coherence, effect tracking, and composition. A caller's effect row must be a superset of the callee's effects. The agent must understand effect propagation.

**Example problems:**
- `greeter`: Pure function builds greeting string, IO function prints it. Tests effect boundary.
- `counter`: `State<Int>` effect with `get`/`put`, old/new in contracts.
- `safe_div_with_exn`: `Exn<Int>` effect for error handling, with `handle[Exn<Int>]` to catch.
- `fetch_and_parse`: `Http.get` → `json_parse` → extract field. Tests `<Http>` effect + Result chaining.
- `config_reader`: Read environment variable with `IO.get_env`, fall back to default. Tests `<IO>` + Option handling.
- `accumulator`: Multiple functions sharing `State<Int>`, one pure helper. Tests effect coherence across call boundaries.
- `pipeline`: Pure transform → IO output → pure validation. Tests mixed effect composition.
- `error_recovery`: Try an operation, catch with `handle[Exn<Int>]`, return `Result`. Tests effect handler syntax.
- `llm_classifier` (Inference): Build prompt with pure string functions, call `Inference.complete`, parse result. Tests `<Inference>` effect (requires API key or mock).
- `multi_module`: Two-file program with `module`/`import`. Tests cross-module contract checking.

**What distinguishes Vera here:** Every other language lets you call `print()` from a "pure" function. In Vera, forgetting `effects(<IO>)` on any function in the call chain is a type error. The agent must reason about effect propagation across the entire program.

---

## 4. Problem Definition Format

Each problem is a JSON file. This format is designed to support the three metrics (check rate, verify rate, fix-from-error rate) and the cross-language baselines.

```json
{
  "id": "VB-T1-001",
  "tier": 1,
  "title": "Absolute Value",
  "description": "Write a Vera function that computes the absolute value of an integer. The function should take a single Int parameter and return a Nat (non-negative integer). The postcondition should guarantee the result is non-negative and equals either the input or its negation.",
  "signature": "public fn absolute_value(@Int -> @Nat)",
  "contracts": {
    "requires": "true",
    "ensures": ["@Nat.result >= 0", "@Nat.result == @Int.0 || @Nat.result == -@Int.0"],
    "effects": "pure"
  },
  "tags": ["arithmetic", "postcondition", "conditional"],
  "canonical_solution": {
    "vera": "public fn absolute_value(@Int -> @Nat)\n  requires(true)\n  ensures(@Nat.result >= 0)\n  ensures(@Nat.result == @Int.0 || @Nat.result == -@Int.0)\n  effects(pure)\n{\n  if @Int.0 >= 0 then {\n    @Int.0\n  } else {\n    -@Int.0\n  }\n}",
    "python": "def absolute_value(x: int) -> int:\n    \"\"\"Return the absolute value of x.\n    Postcondition: result >= 0 and (result == x or result == -x)\n    \"\"\"\n    if x >= 0:\n        return x\n    else:\n        return -x",
    "typescript": "function absoluteValue(x: number): number {\n  // Postcondition: result >= 0 and (result === x || result === -x)\n  if (x >= 0) {\n    return x;\n  } else {\n    return -x;\n  }\n}"
  },
  "test_inputs": [0, 1, -1, 42, -42, 2147483647],
  "expected_outputs": [0, 1, 1, 42, 42, 2147483647],
  "vera_check_must_pass": true,
  "vera_verify_tier1": true,
  "notes": "Tests basic conditional, slot references, and Nat return type. The Nat type is a refinement of Int (non-negative). Z3 should verify both ensures clauses at Tier 1."
}
```

### Field semantics

| Field | Purpose |
|-------|---------|
| `id` | Unique ID. Format: `VB-T{tier}-{number}`, e.g. `VB-T1-001`. |
| `tier` | Difficulty tier (1–5). |
| `title` | Human-readable problem name. |
| `description` | Natural language problem description. This is what gets fed to the LLM as the prompt (along with the SKILL.md). |
| `signature` | The function signature the LLM should implement. Included in the prompt. |
| `contracts` | The contracts the solution must satisfy. May be included in the prompt (full-spec mode) or omitted (spec-from-NL mode). |
| `tags` | Categorisation tags for analysis. |
| `canonical_solution.vera` | Reference Vera solution that passes `vera check`, `vera verify`, and `vera run`. |
| `canonical_solution.python` | Equivalent Python solution for baseline comparison. |
| `canonical_solution.typescript` | Equivalent TypeScript solution for baseline comparison. |
| `test_inputs` | Concrete inputs for `vera run --fn`. |
| `expected_outputs` | Expected outputs corresponding to test_inputs. |
| `vera_check_must_pass` | Whether `vera check` should pass (always true for valid problems). |
| `vera_verify_tier1` | Whether Z3 should verify all contracts at Tier 1 (true for tiers 1–2, often false for tiers 3–5). |
| `notes` | Implementation notes for benchmark maintainers. |

---

## 5. Metrics

For each problem × model combination, collect:

### Primary metrics

1. **check@1** — Does the first attempt pass `vera check`? (Binary: 0 or 1)
2. **verify@1** — Does the first attempt pass `vera verify` with all contracts at Tier 1? (Binary)
3. **fix@1** — Given the error message from a failed `vera check`, does the model fix it in one turn? (Binary)
4. **run_correct** — Does `vera run --fn f -- <input>` produce the expected output for all test inputs? (Binary)

### Aggregate metrics

- **check_rate** — Fraction of problems passing `vera check` on first attempt, per tier and overall.
- **verify_rate** — Fraction of Tier-1-verifiable problems actually verified, per tier.
- **fix_rate** — Fraction of failed problems fixed in one retry with error feedback.
- **tier_breakdown** — For each solution: how many contracts are Tier 1 vs. Tier 3?

### Cross-language baselines

For each problem, also run:
- **Python**: Execute with `pytest` or `assert` statements. Measure pass@1.
- **TypeScript**: Execute with `ts-node` or `bun`. Measure pass@1.

The interesting comparison is: given the same NL description, does the model produce correct code more or less often in Vera vs. Python/TypeScript? The hypothesis is that Vera's mandatory contracts catch bugs that would pass silently in Python.

### Reporting

Results are stored as JSONL:

```json
{"problem_id": "VB-T1-001", "model": "claude-opus-4-20250514", "language": "vera", "attempt": 1, "check_pass": true, "verify_pass": true, "verify_tier1": 2, "verify_tier3": 0, "run_correct": true, "generation_tokens": 187, "wall_time_s": 3.2, "timestamp": "2026-03-29T12:00:00Z"}
```

---

## 6. Harness Architecture

### Prompt construction

The harness constructs a prompt for each problem:

```
System: You are an expert Vera programmer. Write valid Vera code that compiles and verifies.

[SKILL.md contents — or a curated subset for smaller context windows]

User: {problem.description}

The function signature is:
{problem.signature}

Write a complete Vera function (including requires, ensures, effects, and body). Output only the Vera code, no explanation.
```

For Tier 3+ problems that define ADTs, the prompt includes the `data` declaration.

For fix-from-error attempts:

```
User: The code you wrote produced this error:

{error_output}

Fix the code. Output only the corrected Vera code.
```

### Execution pipeline

For each problem × model:

1. **Generate**: Call LLM API → extract Vera code from response.
2. **Write**: Save to `{problem_id}.vera` in a temp directory.
3. **Format check**: Run `vera fmt --check` (optional, for style conformance).
4. **Check**: Run `vera check --json {file}` → record check_pass, parse diagnostics.
5. **Verify**: If check passed, run `vera verify --json {file}` → record verify_pass, tier breakdown.
6. **Run**: If check passed, for each test input: `vera run {file} --fn {entry_point} -- {input}` → compare output to expected.
7. **Fix attempt**: If check failed, feed error message back to model, get fix, repeat steps 2–6 once.

### Baseline execution

- **Python**: Write solution to `.py`, run `python -c "from solution import f; assert f(input) == expected"`.
- **TypeScript**: Write solution to `.ts`, run with `bun` or `ts-node`, check assertions.

### Safety

All code runs in subprocesses with timeouts. Vera compiles to WASM which runs in wasmtime's sandbox — no ambient file/network access unless effects are declared.

---

## 7. Repository Structure

```
vera-bench/
├── README.md                    # Overview, installation, usage
├── LICENSE                      # Apache 2.0 (matching DafnyBench)
├── pyproject.toml               # Python package with CLI entry point
├── CITATION.cff                 # Citation metadata
│
├── problems/                    # Problem definitions
│   ├── tier1/
│   │   ├── VB-T1-001_absolute_value.json
│   │   ├── VB-T1-002_clamp.json
│   │   └── ...
│   ├── tier2/
│   ├── tier3/
│   ├── tier4/
│   └── tier5/
│
├── solutions/                   # Canonical solutions (one per problem)
│   ├── vera/
│   │   ├── VB-T1-001_absolute_value.vera
│   │   └── ...
│   ├── python/
│   │   ├── VB-T1-001_absolute_value.py
│   │   └── ...
│   └── typescript/
│       ├── VB-T1-001_absolute_value.ts
│       └── ...
│
├── vera_bench/                  # Harness package
│   ├── __init__.py
│   ├── cli.py                   # CLI: vera-bench run, vera-bench report
│   ├── runner.py                # Orchestrate: generate → check → verify → run
│   ├── prompts.py               # Prompt construction from problem definitions
│   ├── models.py                # LLM API abstraction (Anthropic, OpenAI, etc.)
│   ├── vera_runner.py           # Subprocess calls to vera check/verify/run
│   ├── baseline_runner.py       # Python and TypeScript execution
│   ├── metrics.py               # Metric computation and aggregation
│   └── report.py                # Generate markdown/HTML/CSV reports
│
├── results/                     # Versioned result snapshots
│   ├── v1.0_vera-0.0.103/
│   │   ├── claude-opus-4.jsonl
│   │   ├── claude-sonnet-4.jsonl
│   │   ├── gpt-4o.jsonl
│   │   └── summary.md
│   └── ...
│
├── analysis/                    # Notebooks and scripts for paper figures
│   └── plots.ipynb
│
├── context/                     # SKILL.md snapshots for reproducibility
│   ├── SKILL_v0.0.103.md
│   └── ...
│
├── scripts/
│   ├── validate_problems.py     # Check all problem JSONs are well-formed
│   ├── validate_solutions.py    # Run all canonical solutions through vera
│   └── generate_baselines.py    # Generate Python/TS solutions from Vera ones
│
└── tests/
    ├── test_runner.py
    ├── test_prompts.py
    └── test_metrics.py
```

---

## 8. Problem Counts (Target)

| Tier | Count | Rationale |
|------|-------|-----------|
| Tier 1: Pure arithmetic | 15 | Easy wins — establishes baseline syntax competence |
| Tier 2: String/array | 15 | Tests built-in discovery — the `domain_verb` naming convention |
| Tier 3: ADTs + match | 12 | Tests De Bruijn indices in match arms — the core Vera innovation |
| Tier 4: Recursion + termination | 10 | Tests `decreases` clauses — unique to verified languages |
| Tier 5: Multi-function + effects | 8 | Tests effect coherence — Vera's effect system vs. unchecked side effects |
| **Total** | **60** | Comparable to HumanEval's 164, but each problem is more complex |

Start with 10 problems per tier (50 total) for v1.0. Expand to 60+ for v1.1.

---

## 9. CLI Interface

```bash
# Run benchmark against a specific model
vera-bench run --model claude-opus-4-20250514 --vera-version 0.0.103

# Run a single tier
vera-bench run --model claude-opus-4-20250514 --tier 1

# Run a single problem
vera-bench run --model claude-opus-4-20250514 --problem VB-T1-001

# Run baselines only (Python + TypeScript)
vera-bench baselines --model claude-opus-4-20250514

# Generate report from results
vera-bench report results/v1.0_vera-0.0.103/

# Validate all problem definitions and canonical solutions
vera-bench validate
```

Environment variables:
- `ANTHROPIC_API_KEY` — for Claude models
- `OPENAI_API_KEY` — for OpenAI models
- `VERA_PATH` — path to `vera` binary (default: looks in PATH)
- `VERA_BENCH_RESULTS` — output directory (default: `results/`)

---

## 10. Implementation Priorities

### Phase 1: Scaffold (do first)

1. Create repo structure.
2. Define JSON schema for problem definitions.
3. Write 3 problems per tier (15 total) with canonical Vera solutions.
4. Validate all canonical solutions pass `vera check` and `vera verify`.
5. Write `vera_runner.py` — subprocess wrapper for `vera check --json`, `vera verify --json`, `vera run`.

### Phase 2: Harness

6. Write `prompts.py` — construct prompts from problem JSON + SKILL.md.
7. Write `models.py` — LLM API abstraction (start with Anthropic API).
8. Write `runner.py` — the generate→check→verify→run→fix pipeline.
9. Write `metrics.py` — compute check_rate, verify_rate, fix_rate per tier.
10. Write `cli.py` — CLI entry point.

### Phase 3: Baselines

11. Write canonical Python and TypeScript solutions for all problems.
12. Write `baseline_runner.py` — execute Python/TS solutions.
13. Add cross-language comparison to reports.

### Phase 4: First Run

14. Run against Claude Opus 4, Claude Sonnet 4, GPT-4o.
15. Generate results and analysis.
16. Write README with results table.

### Phase 5: Polish

17. Expand to 50+ problems.
18. Add Hugging Face dataset export.
19. Write CITATION.cff.
20. CI: validate problems + solutions on every PR.

---

## 11. Key Design Decisions

**Problem descriptions are natural language, not code stubs.** Unlike HumanEval (which gives a Python function signature + docstring), VeraBench gives a natural language description + the Vera function signature + optionally the contracts. This tests the full pipeline: NL understanding → Vera syntax → correct contracts → correct implementation.

**Contracts can be provided or omitted.** For Tiers 1–2, provide the contracts in the prompt — the test is whether the agent can implement the body. For Tiers 3–5, consider a "spec-from-NL" variant where the agent must also write the contracts. Track both modes.

**The SKILL.md is always provided.** Unlike benchmarks for well-known languages, Vera is not in any model's training data (43 GitHub stars). The SKILL.md is the sole source of language knowledge. This tests the model's ability to learn from documentation, not recall from training.

**Retry with error feedback is a first-class metric.** DafnyBench showed that retry success rate (error feedback → fix) is as informative as first-attempt success. Vera's error messages are designed to be agent-friendly (natural language, concrete fix suggestions). This is a competitive advantage worth measuring.

**Pin SKILL.md versions for reproducibility.** The `context/` directory stores SKILL.md snapshots. When vera v0.0.110 adds new features, the benchmark can test whether agents exploit them by comparing results with the old vs. new SKILL.md.

---

## 12. What NOT to Do

- **Don't import vera compiler internals.** The benchmark should work with any version of `vera` that has the same CLI interface. `pip install vera-lang` + subprocess calls.
- **Don't make Tier 5 problems require network access.** Mock the `Http` and `Inference` effects — check that the code compiles and the effect declarations are correct, but don't actually make HTTP/LLM calls during benchmarking.
- **Don't use problems from the vera examples/ or conformance/ directories.** Those are in the repo and therefore in training data. Write fresh problems.
- **Don't over-engineer the first version.** 50 problems, one LLM API, JSONL results, markdown report. Ship that, get data, iterate.

---

## 13. Vera Installation for the Benchmark Environment

```bash
git clone https://github.com/aallan/vera.git
cd vera
python -m venv .venv && source .venv/bin/activate
pip install -e .
vera check examples/hello_world.vera   # Verify installation
vera version                            # Should print version
```

The benchmark repo's `pyproject.toml` should list `vera-lang` (or document the installation separately) and the LLM API clients:

```toml
[project]
name = "vera-bench"
dependencies = [
    "anthropic>=0.40",
    "openai>=1.50",
    "click>=8.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = ["pytest", "ruff"]

[project.scripts]
vera-bench = "vera_bench.cli:main"
```

---

## 14. Links and References

- Vera repo: https://github.com/aallan/vera
- Vera language reference: https://veralang.dev/SKILL.md
- GitHub issue #225: https://github.com/aallan/vera/issues/225
- Vera ROADMAP: https://github.com/aallan/vera/blob/main/ROADMAP.md
- HumanEval: https://github.com/openai/human-eval
- MBPP: https://github.com/google-research/google-research/tree/master/mbpp
- DafnyBench: https://github.com/sun-wendy/DafnyBench (paper: arXiv:2406.08467)
- VerifyThisBench: https://openreview.net/pdf/b0715e58c2fe690e0c0ba80f5c9ca783df3098f5.pdf
- VERINA: https://arxiv.org/pdf/2505.23135
- CLEVER: https://arxiv.org/pdf/2505.13938
