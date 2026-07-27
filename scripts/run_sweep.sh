#!/usr/bin/env bash
# Idempotent full-matrix sweep runner — one terminal, unattended, resumable.
#
# Runs every matrix target that is MISSING or hit a TRANSIENT infrastructure
# fault, and SKIPS any already on disk and clean. "Clean" reuses the SAME
# classifier as scripts/sweep_status.py: a file is dirty only if it has <60
# rows or carries a genuine transient fault (rate-limit, timeout, connection,
# empty content). A refusal, a compile/runtime error, or a finish_reason=length
# truncation is a REAL result and leaves the file clean — so the sweep never
# futilely re-runs a deterministic failure. Length walls are prevented up front
# by giving the reasoning models a bigger --max-tokens; repair a stray dirty
# target per-problem with scripts/rerun_failed.py instead of re-running all 60.
#
#   export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... MOONSHOT_API_KEY=...
#   bash scripts/run_sweep.sh                     # everything except pro
#   SWEEP_INCLUDE_PRO=1 bash scripts/run_sweep.sh # opt in to the pro tier
#
# Overnight:  nohup caffeinate -is bash scripts/run_sweep.sh > ~/sweep.out 2>&1 &
#
# The model lineup, providers, and ztd (aver/ailang) subset all come from
# vera_bench/matrix.py — the same registry preflight.sh and plot_results.py
# read, so nothing drifts. Provider streams run concurrently; models within a
# provider run serially (per-provider rate limits).
#
# Tunables (env):
#   PAR_ANTHROPIC=4  PAR_OPENAI=3  PAR_MOONSHOT=3   per-provider concurrency
#   SWEEP_RETRIES=2                                 attempts per target per pass
#   SWEEP_INCLUDE_PRO=0                             opt IN to the pro tier (~$10/target)
#   MAX_TOKENS_MOONSHOT=32000                       budget for the reasoning kimi models

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

if [ -z "${VIRTUAL_ENV:-}" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate 2>/dev/null || { echo "run: source .venv/bin/activate"; exit 1; }
fi
mkdir -p results/logs

# Every result filename carries these two versions, so both are read from
# the code that WRITES them rather than re-derived here. `vera-bench run`
# records `vera_bench.__version__` and `VeraRunner.version()` verbatim, so
# a prerelease — `0.0.19rc1`, `0.1.9-dev` — has to survive intact: a
# `[0-9]+\.[0-9]+\.[0-9]+` match keeps only the numeric head and would
# predict a file the CLI never writes. That is the failure this contract
# exists to prevent; spelling the bench version out once already made
# every successful target read as dirty, and the whole matrix was paid
# for twice before it reported total failure over good data.
# Asking VeraRunner rather than the shell's own `vera` also settles WHICH
# compiler is meant: it honours $VERA_PATH ahead of $PATH, exactly as the
# grading run does, so the predicted name can no longer describe a
# different binary than the one that produced the results.
_VERSIONS=$(python - <<'PY'
import vera_bench

try:
    from vera_bench.vera_runner import VeraRunner

    runner = VeraRunner()
    vera_version, vera_bin = runner.version(), runner.vera
except Exception:  # vera absent from PATH entirely
    vera_version, vera_bin = "unknown", "<not found>"
print(vera_bench.__version__, vera_version, vera_bin)
PY
) || _VERSIONS=""
read -r BENCH_VER VERA_VER VERA_BIN <<<"$_VERSIONS"
if [ -z "$BENCH_VER" ]; then
  echo "FATAL: could not determine vera-bench version" >&2
  exit 1
fi
# `unknown` is what VeraRunner reports when the compiler will not run. It
# is omitted from filenames, so a sweep started on it would predict names
# that never match — and the usual cause is a same-named binary earlier on
# PATH, which is worth naming rather than leaving to be guessed at.
if [ -z "$VERA_VER" ] || [ "$VERA_VER" = unknown ]; then
  echo "FATAL: could not read 'vera version' from ${VERA_BIN:-<not found>}" >&2
  echo "       set VERA_PATH if another 'vera' is shadowing the compiler" >&2
  exit 1
fi

PAR_ANTHROPIC=${PAR_ANTHROPIC:-4}
PAR_OPENAI=${PAR_OPENAI:-3}
PAR_MOONSHOT=${PAR_MOONSHOT:-3}
RETRIES=${SWEEP_RETRIES:-2}
INCLUDE_PRO=${SWEEP_INCLUDE_PRO:-0}
MAX_TOKENS_MOONSHOT=${MAX_TOKENS_MOONSHOT:-32000}

# One status line per finished target ("skip|ok|dirty <model>/<label>"), so the
# end-of-run tally survives the concurrent provider subshells (which cannot
# write the parent's variables).
STATUS_FILE=$(mktemp "${TMPDIR:-/tmp}/vb-sweep.XXXXXX")
trap 'rm -f "$STATUS_FILE"' EXIT

par () {
  case "$1" in
    claude-*)            echo "$PAR_ANTHROPIC" ;;
    gpt-*|openai-pro/*)  echo "$PAR_OPENAI" ;;
    moonshot/*)          echo "$PAR_MOONSHOT" ;;
    *)                   echo 3 ;;
  esac
}

# Reasoning models spend output budget "thinking" and truncate
# (finish_reason=length) before emitting code if the budget is the 4096
# default. fable and the kimi models are the reasoning ones; pro gets its own
# 16000 floor inside the client, so it needs nothing here.
extra_args () {
  case "$1" in
    claude-fable-5) echo "--max-tokens 16000" ;;
    moonshot/*)     echo "--max-tokens $MAX_TOKENS_MOONSHOT" ;;
    *)              echo "" ;;
  esac
}

# clean := newest file for the glob exists, has >=60 rows, and carries no
# TRANSIENT fault. classify() (shared with sweep_status.py) is the single
# source of truth for what "transient" means — refusals, length walls and
# compile/runtime errors are real results and do NOT make a file dirty.
is_clean () {
  local f
  f=$(ls -t $1 2>/dev/null | head -1)
  [ -z "$f" ] && return 1
  python - "$f" <<'PY'
import glob, json, sys
sys.path.insert(0, "scripts")
from sweep_status import classify

rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
# Coverage is measured in unique problem ids, not rows: one problem can emit
# two rows (attempt 1 + a fix), so a partial run can reach 60 rows while
# missing problems. Require every problem present.
solved = {r["problem_id"] for r in rows if r.get("problem_id")}
expected = len(glob.glob("problems/**/VB_*.json", recursive=True)) or 60
transient = sum(
    1 for r in rows
    if r.get("error_message") and classify(r["error_message"]) == "transient"
)
sys.exit(0 if len(solved) >= expected and transient == 0 else 1)
PY
}

do_target () {  # MODEL LABEL GLOB [run args...]
  local M=$1 LBL=$2 GLOB=$3; shift 3
  if is_clean "$GLOB"; then
    printf '  skip   %-26s %-8s (clean)\n' "$M" "$LBL"
    echo "skip $M/$LBL" >> "$STATUS_FILE"; return
  fi
  local P S EXTRA a; P=$(par "$M"); S=${M//\//-}; EXTRA=$(extra_args "$M")
  for a in $(seq 1 "$RETRIES"); do
    printf '>>>>   %-26s %-8s attempt %s (parallel %s%s)\n' \
      "$M" "$LBL" "$a" "$P" "${EXTRA:+, $EXTRA}"
    # shellcheck disable=SC2086
    vera-bench run --model "$M" --parallel "$P" $EXTRA "$@" \
      2>&1 | tee "results/logs/sweep-${S}-${LBL}.log" | tail -2
    if is_clean "$GLOB"; then
      printf '  ok     %-26s %-8s\n' "$M" "$LBL"
      echo "ok $M/$LBL" >> "$STATUS_FILE"; return
    fi
    printf '  dirty  %-26s %-8s (attempt %s) — retrying\n' "$M" "$LBL" "$a"
    sleep 5
  done
  printf '  STILL DIRTY after %s attempts: %s %s — see results/logs/sweep-%s-%s.log\n' \
    "$RETRIES" "$M" "$LBL" "$S" "$LBL"
  echo "dirty $M/$LBL" >> "$STATUS_FILE"
}

# The filename `vera-bench run` will write, asked of the one function
# that builds it (vera_bench/results_path.py) rather than spelled out
# again here. Re-deriving it is what broke: this script waited on a
# name the CLI never wrote, so every finished target read as dirty.
# A subprocess per target is free against an LLM call.
result_file () {  # MODEL [--language L] [--mode M] ...
  local M=$1; shift
  python -m vera_bench.results_path --model "$M" --bench-version "$BENCH_VER" "$@"
}

core () {  # MODEL
  local M=$1
  do_target "$M" vera \
    "results/$(result_file "$M" --vera-version "$VERA_VER")"
  do_target "$M" vera-nl \
    "results/$(result_file "$M" --mode spec-from-nl --vera-version "$VERA_VER")" \
    --mode spec-from-nl
  do_target "$M" python \
    "results/$(result_file "$M" --language python)"      --language python
  do_target "$M" ts \
    "results/$(result_file "$M" --language typescript)"  --language typescript
}
ztd () {  # MODEL
  local M=$1
  # aver/ailang carry their own compiler version, which the sweep does not
  # know up front — so that one segment is a wildcard, but the name around
  # it is still built by results_path rather than spelled out here.
  do_target "$M" aver \
    "results/$(result_file "$M" --language aver --aver-version '*')"      --language aver
  do_target "$M" ailang \
    "results/$(result_file "$M" --language ailang --ailang-version '*')"  --language ailang
}

# Canonical lineup, straight from the registry: "provider<TAB>id<TAB>ztd", with
# the pro tier filtered out unless opted in.
models_tsv () {
  python - "$INCLUDE_PRO" <<'PY'
import sys
from vera_bench.matrix import MODELS

include_pro = sys.argv[1] == "1"
for m in MODELS:
    if m.id.startswith("openai-pro/") and not include_pro:
        continue
    print(f"{m.provider}\t{m.id}\t{1 if m.ztd else 0}")
PY
}

# One provider's models, serially (respects that provider's rate limit).
run_provider () {  # PROVIDER
  trap - EXIT  # a stream's own exit must not wipe the shared status file
  local want=$1 prov id ztd_flag
  while IFS=$'\t' read -r prov id ztd_flag; do
    [ "$prov" = "$want" ] || continue
    core "$id"
    [ "$ztd_flag" = 1 ] && ztd "$id"
  done <<< "$MODELS_TSV"
}

MODELS_TSV=$(models_tsv)
[ -z "$MODELS_TSV" ] && { echo "matrix produced no models"; exit 1; }

echo "== sweep vs vera $VERA_VER (bench $BENCH_VER) — anthropic/$PAR_ANTHROPIC openai/$PAR_OPENAI moonshot/$PAR_MOONSHOT, ${RETRIES} attempts/target, pro=$INCLUDE_PRO =="

# Provider streams concurrent; models within a provider serial.
for prov in $(printf '%s\n' "$MODELS_TSV" | cut -f1 | sort -u); do
  run_provider "$prov" &
done
wait

echo
skip_n=$(grep -c '^skip '  "$STATUS_FILE" || true)
ran_n=$(grep -c  '^ok '    "$STATUS_FILE" || true)
dirty_n=$(grep -c '^dirty ' "$STATUS_FILE" || true)
echo "== pass complete: $skip_n already-clean, $ran_n newly-run, $dirty_n still dirty =="
if [ "$dirty_n" -gt 0 ]; then
  grep '^dirty ' "$STATUS_FILE" | sed 's/^dirty /   dirty: /'
  echo "   Transient? re-run the script. Length/other? scripts/rerun_failed.py --apply."
  exit 1
fi
echo "   All matrix targets clean."
