#!/usr/bin/env bash
# Idempotent v0.0.16 sweep runner — one terminal, unattended, resumable.
#
# Runs every matrix target that is MISSING or INFRASTRUCTURE-CORRUPTED, and
# SKIPS any that already exist and are clean (>=60 rows, zero infra-failure
# rows). Safe to re-run: it only does what is not yet done. Re-run it until
# it reports 0 dirty.
#
#   export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... MOONSHOT_API_KEY=...
#   bash scripts/run_sweep.sh
#
# Overnight:  nohup caffeinate -is bash scripts/run_sweep.sh > ~/sweep.out 2>&1 &
#
# Tunables (env):
#   PAR_ANTHROPIC=4  PAR_OPENAI=3  PAR_MOONSHOT=3   per-provider concurrency
#   SWEEP_RETRIES=2                                 attempts per target per pass
#   SWEEP_INCLUDE_PRO=1                             opt IN to the pro tier (~$10/target)
#
# Parallelism is lowered from the first attempt's 6/10: OpenAI rate-limited
# and Moonshot returned empty content under that load. Fable (a reasoning
# model) runs at --max-tokens 16000 to avoid thinking-budget exhaustion.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

if [ -z "${VIRTUAL_ENV:-}" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate 2>/dev/null || { echo "run: source .venv/bin/activate"; exit 1; }
fi
mkdir -p results/logs

VV=$(vera version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 | tr . -)
[ -z "$VV" ] && { echo "cannot read 'vera version'"; exit 1; }

PAR_ANTHROPIC=${PAR_ANTHROPIC:-4}
PAR_OPENAI=${PAR_OPENAI:-3}
PAR_MOONSHOT=${PAR_MOONSHOT:-3}
RETRIES=${SWEEP_RETRIES:-2}
INCLUDE_PRO=${SWEEP_INCLUDE_PRO:-1}

par () {
  case "$1" in
    claude-*)               echo "$PAR_ANTHROPIC" ;;
    gpt-*|openai-pro/*)      echo "$PAR_OPENAI" ;;
    moonshot/*)             echo "$PAR_MOONSHOT" ;;
    *)                      echo 3 ;;
  esac
}

# clean := file exists, >=60 rows, and no row carries an INFRASTRUCTURE
# error. A model that compiled-then-failed at runtime is a real result and
# does NOT make a file dirty; a rate-limit / empty-content / timeout does.
is_clean () {
  local f
  f=$(ls -t $1 2>/dev/null | head -1)
  [ -z "$f" ] && return 1
  python - "$f" <<'PY'
import json, sys, re
infra = re.compile(
    r"API error|rate.?limit|429|timed out|timeout|killed by signal|auth|"
    r"connection|overloaded|empty content|no text block|503|529", re.I)
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
bad = sum(1 for r in rows if r.get("error_message") and infra.search(r["error_message"]))
sys.exit(0 if len(rows) >= 60 and bad == 0 else 1)
PY
}

skip_n=0; ran_n=0; dirty=()

do_target () {  # MODEL LABEL GLOB [run args...]
  local M=$1 LBL=$2 GLOB=$3; shift 3
  if is_clean "$GLOB"; then
    printf '  skip   %-26s %-8s (clean)\n' "$M" "$LBL"; skip_n=$((skip_n+1)); return
  fi
  local P S EXTRA a; P=$(par "$M"); S=${M//\//-}; EXTRA=""
  [ "$M" = claude-fable-5 ] && EXTRA="--max-tokens 16000"
  for a in $(seq 1 "$RETRIES"); do
    printf '>>>>   %-26s %-8s attempt %s (parallel %s%s)\n' \
      "$M" "$LBL" "$a" "$P" "${EXTRA:+, $EXTRA}"
    # shellcheck disable=SC2086
    vera-bench run --model "$M" --parallel "$P" $EXTRA "$@" \
      2>&1 | tee "results/logs/sweep-${S}-${LBL}.log" | tail -2
    if is_clean "$GLOB"; then
      printf '  ok     %-26s %-8s\n' "$M" "$LBL"; ran_n=$((ran_n+1)); return
    fi
    printf '  dirty  %-26s %-8s (attempt %s) — retrying\n' "$M" "$LBL" "$a"
    sleep 5
  done
  printf '  STILL DIRTY after %s attempts: %s %s — see results/logs/sweep-%s-%s.log\n' \
    "$RETRIES" "$M" "$LBL" "$S" "$LBL"
  dirty+=("$M/$LBL")
}

core () {  # MODEL
  local M=$1 S=${1//\//-}
  do_target "$M" vera    "results/${S}-bench-0-0-16-vera-${VV}.jsonl"
  do_target "$M" vera-nl "results/${S}-spec-from-nl-bench-0-0-16-vera-${VV}.jsonl" --mode spec-from-nl
  do_target "$M" python  "results/${S}-python-bench-0-0-16.jsonl"      --language python
  do_target "$M" ts      "results/${S}-typescript-bench-0-0-16.jsonl"  --language typescript
}
ztd () {  # MODEL
  local M=$1 S=${1//\//-}
  do_target "$M" aver   "results/${S}-aver-bench-0-0-16-aver-*.jsonl"      --language aver
  do_target "$M" ailang "results/${S}-ailang-bench-0-0-16-ailang-*.jsonl"  --language ailang
}

echo "== sweep vs vera $VV (bench 0-0-16) — anthropic/$PAR_ANTHROPIC openai/$PAR_OPENAI moonshot/$PAR_MOONSHOT, $RETRIES attempts/target =="

# sonnet-5 ran as the canary; kept for idempotence (skips if clean).
core claude-sonnet-5
core claude-opus-4-8;    ztd claude-opus-4-8
core claude-fable-5;     ztd claude-fable-5
core gpt-5.6-terra
core gpt-5.6-sol;        ztd gpt-5.6-sol
core moonshot/kimi-k2.6
core moonshot/kimi-k3;   ztd moonshot/kimi-k3
[ "$INCLUDE_PRO" = 1 ] && core openai-pro/gpt-5.6-sol   # pro last; checkpoint passed

echo
echo "== pass complete: $skip_n already-clean, $ran_n newly-run, ${#dirty[@]} still dirty =="
if [ "${#dirty[@]}" -gt 0 ]; then
  printf '   dirty: %s\n' "${dirty[*]}"
  echo "   Re-run the script to retry them; if one is stubborn, drop its provider's PAR_* and re-run."
  exit 1
fi
echo "   All matrix targets clean."
