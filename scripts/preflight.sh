#!/usr/bin/env bash
# Pre-sweep preflight gate: stages S0, S1, S2, S3, S5.
# (There is no S4 — the numbering follows the v0.0.16 plan's
# stage list, where S4 was a Moonshot-caching probe that turned
# out to need no separate call.)
#
# Run this before committing to a full sweep. A full sweep is ~52
# target-runs: 8 models x 6 LLM targets = 48, plus the 4 baseline
# runs, which happen once for the whole sweep rather than per model.
# There is no resume, so a model id that does not exist, a parameter
# the API rejects, or a toolchain that is not on PATH costs hours and
# real money to discover late. Every check here is one problem.
#
# Needs `curl` and `jq` on PATH for S0 (without jq the provider
# listings come back empty and every model reports NOT LISTED).
#
# Run from the repo root with the three provider keys exported:
#
#   export ANTHROPIC_API_KEY=...
#   export OPENAI_API_KEY=...
#   export MOONSHOT_API_KEY=...
#   bash scripts/preflight.sh              # all stages
#   bash scripts/preflight.sh s2 s3        # only these stages
#
# Stage selection exists because these calls cost money: a stage that
# already passed should not be paid for twice on a re-run.
#
# SMOKE_SKIP_MODELS is a space-separated list of S1 models to skip, for
# the same reason:
#
#   SMOKE_SKIP_MODELS="claude-fable-5" bash scripts/preflight.sh
#
# The model list is NOT duplicated here — it is read from
# run_full_benchmark.py, so the gate always checks the matrix that is
# actually configured. Targets bash 3.2 (macOS system bash): no
# mapfile, no associative arrays.
#
# Cost: roughly $1-2. Every LLM call is a SINGLE problem, and most use
# the Python target (no ~28k-token SKILL.md prefix). Output goes to a
# scratch dir, never results/, so it cannot pollute a real sweep.
#
# Each stage writes to its own subdirectory. This is load-bearing, not
# tidiness: result filenames carry no timestamp (the `parts`/`_ver_slug`
# block in vera_bench/cli.py) and `run` UNLINKS an existing file (the
# "Truncate stale results" step), so two stages that
# run the same model+language+mode would silently overwrite each other.
#
# Nothing here prints a key. The report at the end is safe to paste.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

SMOKE="/tmp/vb-smoke-$(date +%F-%H%M)"
mkdir -p "$SMOKE"/{s1,s2,s3,s5}
VB=".venv/bin/vera-bench"
PY=".venv/bin/python"
export VERA_PATH="$PWD/.venv/bin/vera"
export PATH="$PWD/.venv/bin:$PATH"

STAGES="${*:-s0 s1 s2 s3 s5}"
want() { [[ " $STAGES " == *" $1 "* ]]; }
SKIP_MODELS="${SMOKE_SKIP_MODELS:-}"

# The reasoning-budget pair (S2) and the canary model (S5). Unlike the
# S1 list these are roles, not the whole matrix, so they are named here:
# S2 needs two entries that differ ONLY in reasoning mode, and S5 wants
# the cheapest model that exercises all six target languages.
REASON_BASE="${PREFLIGHT_REASON_BASE:-gpt-5.6-sol}"
REASON_PRO="${PREFLIGHT_REASON_PRO:-openai-pro/gpt-5.6-sol}"
CANARY="${PREFLIGHT_CANARY:-claude-sonnet-5}"

pass=0; fail=0
note() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
ok()   { printf '  ok    %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }
skip() { printf '  --    %s (skipped)\n' "$1"; }
# Each vera-bench call is redirected to a log, so without this the
# script looks hung during a slow model — fable thinks, and pro
# deliberates against a 16000-token budget. Overwritten by the verdict.
busy() { printf '  ...   %s\r' "$1"; }

# Exit code is NOT success. `vera-bench run` records an API error as a
# JSONL row and still exits 0 — that is deliberate (a transient error
# costs one problem, not the whole sweep), but it means a smoke check
# that reads $? reports "ok" for a model that never answered. Both
# fable-tier models passed that way on 2026-07-23. Judge the rows.
verdict () {  # label, results-dir, logfile
  local lbl=$1 dir=$2 log=$3
  local err
  # 2>&1: without it a traceback goes to stderr, $err is empty, and the
  # verdict falls through to "ok" — the judge failing silently is exactly
  # the failure mode this function was written to eliminate. A truncated
  # JSONL line (the signature of a killed run) reaches here as a
  # JSONDecodeError, and must read as FAIL rather than pass.
  err=$($PY - "$dir" 2>&1 <<'PY'
import json, pathlib, sys
for f in sorted(pathlib.Path(sys.argv[1]).rglob("*.jsonl")):
    for n, line in enumerate(f.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"corrupt row {f.name}:{n} — {e}"); raise SystemExit
        if r.get("error_message"):
            print(r["error_message"][:150]); raise SystemExit
PY
)
  if [ -n "$err" ]; then bad "$lbl — $err"
  elif [ ! -d "$dir" ] || [ -z "$(find "$dir" -name '*.jsonl' 2>/dev/null)" ]; then
    bad "$lbl — no result row ($(grep -iE 'error|Traceback' "$log" | head -1 | cut -c1-100))"
  else ok "$lbl"; fi
}

note "keys present (values never printed)"
for k in ANTHROPIC_API_KEY OPENAI_API_KEY MOONSHOT_API_KEY; do
  if [ -n "${!k:-}" ]; then ok "$k set"; else bad "$k MISSING — export it and re-run"; fi
done
[ "$fail" -gt 0 ] && { echo; echo "Stopping: export the missing key(s) first."; exit 1; }

note "toolchain"
echo "  vera-bench $($VB --version 2>&1 | tail -1)"
echo "  vera       $(vera version 2>&1 | head -1)"
echo "  aver       $(aver --version 2>&1 | head -1)"
echo "  ailang     $(ailang --version 2>&1 | head -1)"   # 7-line banner

# ---------------------------------------------------------------- S0
# Do the IDs exist? Free — no tokens spent. This is the cheapest place
# to discover that a planned model ID is wrong.
if want s0; then
note "S0  model IDs exist (provider /v1/models)"
oai=$(curl -s https://api.openai.com/v1/models \
        -H "Authorization: Bearer $OPENAI_API_KEY" | jq -r '.data[].id' 2>/dev/null)
msh=$(curl -s https://api.moonshot.ai/v1/models \
        -H "Authorization: Bearer $MOONSHOT_API_KEY" | jq -r '.data[].id' 2>/dev/null)
# Derived from the same MODELS table as S1, via run_full_benchmark's own
# _detect_provider, so a model added to the sweep is gated here too.
# Routing prefixes are stripped: the provider lists bare ids, and both
# Sol entries collapse to the same one. Only OpenAI and Moonshot are
# queried here; Anthropic ids are left to S1, which exercises them
# against the real endpoint anyway. (Anthropic does publish
# GET /v1/models — adding it here would close the gap for the three
# Claude entries.)
while IFS='|' read -r provider bare; do
  [ -z "$bare" ] && continue
  case "$provider" in
    openai)   grep -qxF "$bare" <<<"$oai" && ok "openai: $bare" \
                || bad "openai: $bare NOT LISTED" ;;
    moonshot) grep -qxF "$bare" <<<"$msh" && ok "moonshot: $bare" \
                || bad "moonshot: $bare NOT LISTED" ;;
  esac
done < <($PY -c "
import sys; sys.path.insert(0, 'scripts')
from run_full_benchmark import MODELS, _detect_provider
seen = set()
for group in MODELS.values():
    for _label, model_id in group:
        provider = _detect_provider(model_id)
        bare = model_id.split('/')[-1]
        if (provider, bare) in seen:
            continue
        seen.add((provider, bare))
        print(f'{provider}|{bare}')
")
echo "  --- OpenAI ids matching 5.6 (substitution candidates) ---"
grep -i "5\.6" <<<"$oai" | sed 's/^/      /'
echo "  --- Moonshot ids matching k3/k2 ---"
grep -iE "k3|k2" <<<"$msh" | sed 's/^/      /'
fi

# ---------------------------------------------------------------- S1
# Auth + ID acceptance + the max_tokens vs max_completion_tokens
# question. Python target = no big prefix, so these are the cheapest
# real calls that still exercise the whole client path.
if want s1; then
note "S1  one problem per model (python target)"
# Single source of truth: whatever the sweep is configured to run is
# what gets gated. A hardcoded copy here would drift and quietly stop
# checking a model that the sweep still uses.
MODELS=()
while IFS= read -r m; do
  [ -n "$m" ] && MODELS+=("$m")
done < <($PY -c "
import sys; sys.path.insert(0, 'scripts')
from run_full_benchmark import MODELS
for group in MODELS.values():
    for _label, model_id in group:
        print(model_id)
")
if [ "${#MODELS[@]}" -eq 0 ]; then
  bad "could not read MODELS from scripts/run_full_benchmark.py"
else
  echo "  (${#MODELS[@]} models from run_full_benchmark.py)"
fi
for m in ${MODELS[@]+"${MODELS[@]}"}; do
  if [[ " $SKIP_MODELS " == *" $m "* ]]; then skip "$m"; continue; fi
  slug="${m//\//-}"
  log="$SMOKE/log-s1-$slug.txt"
  busy "$m"
  # Per-model dir so verdict() judges only this model's rows.
  $VB run --model "$m" --problem VB-T1-001 --language python \
     --output-dir "$SMOKE/s1/$slug" >"$log" 2>&1
  verdict "$m" "$SMOKE/s1/$slug" "$log"
done
fi

# ---------------------------------------------------------------- S2
# Does pro mode actually ENGAGE, or is the parameter silently accepted
# and ignored? Same model, same problem, same prompt — the only
# variable is the reasoning budget, so a null result here means the
# Responses-API migration becomes the verified fix.
# Separate dirs: both calls produce the same filename otherwise.
if want s2; then
note "S2  reasoning budget actually engages"
busy "$REASON_BASE (standard)"
$VB run --model "$REASON_BASE" --problem VB-T1-001 \
   --output-dir "$SMOKE/s2/default" >"$SMOKE/log-s2-default.txt" 2>&1
busy "$REASON_PRO — deliberating"
$VB run --model "$REASON_PRO" --problem VB-T1-001 \
   --output-dir "$SMOKE/s2/pro" >"$SMOKE/log-s2-pro.txt" 2>&1
printf '%-60s\r' " "
if $PY - "$SMOKE/s2" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
def row(sub):
    fs = sorted((d / sub).glob("*.jsonl"))
    if not fs: return None
    ls = [json.loads(x) for x in fs[0].read_text().splitlines() if x.strip()]
    return ls[0] if ls else None
base, pro = row("default"), row("pro")
if not base or not pro:
    print("  FAIL  missing one half of the pair — see log-s2-*.txt"); raise SystemExit
# An errored call reports wall=0.0 and out_tok=0, which the ratio test
# below would read as "pro looks identical to default" — the exact
# wrong conclusion. It said that on 2026-07-23 when pro was in fact
# 400-ing. Check for errors first.
failed = False
for lbl, r in (("default", base), ("pro", pro)):
    if r.get("error_message"):
        print(f"  FAIL  {lbl} errored: {r['error_message'][:200]}")
        failed = True
if failed:
    print("  VERDICT : inconclusive — fix the error above, then re-run s2")
    raise SystemExit(1)
for lbl, r in (("default", base), ("pro", pro)):
    print(f"  {lbl:<8}: model={r['model']!r} wall={r['wall_time_s']:.1f}s "
          f"out_tok={r['output_tokens']} check={r['check_pass']}")
w = pro["wall_time_s"] / max(base["wall_time_s"], 0.01)
t = pro["output_tokens"] / max(base["output_tokens"], 1)
print(f"  ratio   : wall x{w:.1f}   out_tok x{t:.1f}")
engaged = w > 1.4 or t > 1.4
print("  VERDICT : " + ("pro ENGAGED — distinct cost/latency signature"
      if engaged else
      "*** pro may be SILENTLY IGNORED — indistinguishable from default ***"))
print(f"  model field distinguishable in JSONL: "
      f"{'yes' if pro['model'] != base['model'] else 'NO — charts cannot tell them apart'}")
if pro["wall_time_s"] > 100:
    print(f"  WARNING : {pro['wall_time_s']:.0f}s is near the 120s client timeout")
raise SystemExit(0 if engaged else 1)
PY
then ok "S2 reasoning budget engages"
else bad "S2 — pro indistinguishable from default (see verdict above)"
fi
fi

# ---------------------------------------------------------------- S3
# Prompt caching. This is the SECOND call sharing the ~28k SKILL.md
# system prefix (S2's default run was the first), so a working cache
# should report cached_tokens > 0 here and 0 there.
if want s3; then
note "S3  cache accounting (2nd call on the same ~29k prefix)"
# One model per provider. A cache probe needs BOTH a prompt over the
# provider's minimum (the ~29k SKILL.md prefix, i.e. a Vera target) and a
# repeat call against it. Neither S1 nor S5 gives that to every provider:
# S1 uses the 70-token Python target, which cannot cache at all, and S5
# only runs the canary. Probing a single model here left Moonshot
# unmeasured through the whole v0.0.16 gate, and Anthropic measured only
# by accident (S5 runs vera-full then vera-nl, which share the prefix).
MOONSHOT_PROBE="${PREFLIGHT_MOONSHOT:-moonshot/kimi-k3}"
CACHE_PROBE="${PREFLIGHT_CACHE_PROBE:-$REASON_BASE $CANARY $MOONSHOT_PROBE}"
for m in $CACHE_PROBE; do
  slug="${m//\//-}"
  busy "cache probe: $m (2 calls)"
  # Two different problems so the user half differs while the system
  # prefix is identical — that is what makes the second call a cache hit
  # rather than an exact-request replay.
  $VB run --model "$m" --problem VB-T1-001 \
     --output-dir "$SMOKE/s3/$slug/warm" >"$SMOKE/log-s3-$slug-1.txt" 2>&1
  $VB run --model "$m" --problem VB-T1-002 \
     --output-dir "$SMOKE/s3/$slug/probe" >"$SMOKE/log-s3-$slug-2.txt" 2>&1
done
$PY - "$SMOKE/s3" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
def row(path):
    for f in sorted(path.rglob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                return json.loads(line)
    return None
print(f"  {'model':<26} {'call':<6} {'input':>7} {'cached':>7}  {'%':>4}")
unproven = []
for slug in sorted(p.name for p in d.iterdir() if p.is_dir()):
    second = None
    for call in ("warm", "probe"):
        r = row(d / slug / call)
        if not r:
            print(f"  {slug[:26]:<26} {call:<6}  (no result row)")
            continue
        i, c = r.get("input_tokens", 0), r.get("cached_tokens", 0)
        print(f"  {r['model'][:26]:<26} {call:<6} {i:>7} {c:>7}  "
              f"{100*c/i if i else 0:>3.0f}%")
        if call == "probe":
            second = (r["model"], i, c)
    # An absent probe row is a failure to measure, not a pass. Leaving
    # `second` unset would drop the model out of `unproven` entirely and
    # let the all-clear print — the gate reporting success for a check
    # that never ran.
    if second is None:
        unproven.append(f"{slug} (no probe result)")
    elif second[1] and second[2] == 0:
        unproven.append(second[0])
print()
if unproven:
    print(f"  NOTE: no cache hit observed on the 2nd call for {unproven}.")
    print("        Either the provider does not cache this prefix, or our")
    print("        cached_tokens read is wrong for that provider. Both")
    print("        matter for cost estimates — worth chasing before a sweep.")
else:
    print("  All probed providers reported a cache hit on the 2nd call.")
PY
fi

# ---------------------------------------------------------------- S5
# Canary: every target path end-to-end on one cheap model. Proves the
# vera-HEAD / aver-0.27 / ailang toolchains all work through the
# harness before the whole sweep depends on them.
if want s5; then
note "S5  all six targets, one problem, one model"
run_target () {  # label, extra args...
  local lbl=$1; shift
  local log="$SMOKE/log-s5-$lbl.txt"
  busy "canary $lbl"
  $VB run --model "$CANARY" --problem VB-T1-001 "$@" \
     --output-dir "$SMOKE/s5/$lbl" >"$log" 2>&1
  verdict "canary $lbl" "$SMOKE/s5/$lbl" "$log"
}
run_target vera-full
run_target vera-nl      --mode spec-from-nl
run_target python       --language python
run_target typescript   --language typescript
run_target aver         --language aver
run_target ailang       --language ailang
fi

# ------------------------------------------------------------- REPORT
note "RESULT FILENAMES  (verify plot_results file_prefix values against these)"
find "$SMOKE" -name '*.jsonl' | sed "s|$SMOKE/||" | sort | sed 's/^/  /'

note "PER-ROW SUMMARY"
$PY - "$SMOKE" <<'PY'
import json, pathlib, sys
for f in sorted(pathlib.Path(sys.argv[1]).rglob("*.jsonl")):
    for line in f.read_text().splitlines():
        if not line.strip(): continue
        r = json.loads(line)
        err = (r.get("error_message") or "")[:64]
        print(f"  {r['problem_id']} {r['language']:<11} "
              f"chk={'Y' if r['check_pass'] else 'n'} "
              f"run={str(r.get('run_correct')):<5} "
              f"{r['model'][:32]:<32} {err}")
PY

printf '\n\033[1m== SMOKE COMPLETE — %d ok, %d failed\033[0m\n' "$pass" "$fail"
echo "Logs + JSONL: $SMOKE"
echo
echo "Paste from '== S0' downwards. It contains no credentials."

# Exit status must reflect the verdict. Without this the gate could
# print "pro may be SILENTLY IGNORED" — the one finding that
# invalidates the headline slide — and still exit 0, so a chained
# `preflight.sh && run_full_benchmark.py` would sail straight past it.
exit $([ "$fail" -eq 0 ] && echo 0 || echo 1)
