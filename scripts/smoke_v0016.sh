#!/usr/bin/env bash
# v0.0.16 pre-sweep smoke gate (S0-S5).
#
# Run from the repo root with the three provider keys exported:
#
#   export ANTHROPIC_API_KEY=...
#   export OPENAI_API_KEY=...
#   export MOONSHOT_API_KEY=...
#   bash scripts/smoke_v0016.sh              # all stages
#   bash scripts/smoke_v0016.sh s2 s3        # only these stages
#
# Stage selection exists because these calls cost money: a stage that
# already passed should not be paid for twice on a re-run.
#
# SMOKE_SKIP_MODELS is a space-separated list of S1 models to skip, for
# the same reason:
#
#   SMOKE_SKIP_MODELS="claude-fable-5" bash scripts/smoke_v0016.sh
#
# Cost: roughly $1-2. Every LLM call is a SINGLE problem, and most use
# the Python target (no ~28k-token SKILL.md prefix). Output goes to a
# scratch dir, never results/, so it cannot pollute a real sweep.
#
# Each stage writes to its own subdirectory. This is load-bearing, not
# tidiness: result filenames carry no timestamp (cli.py:258-270) and
# `run` UNLINKS an existing file (cli.py:273-274), so two stages that
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

pass=0; fail=0
note() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
ok()   { printf '  ok    %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }
skip() { printf '  --    %s (skipped)\n' "$1"; }

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
for m in gpt-5.6-sol gpt-5.6-terra; do
  grep -qx "$m" <<<"$oai" && ok "openai: $m" || bad "openai: $m NOT LISTED"
done
for m in kimi-k3 kimi-k2.6; do
  grep -qx "$m" <<<"$msh" && ok "moonshot: $m" || bad "moonshot: $m NOT LISTED"
done
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
MODELS=(
  claude-fable-5 claude-opus-4-8 claude-sonnet-5
  gpt-5.6-sol gpt-5.6-terra openai-pro/gpt-5.6-sol
  moonshot/kimi-k3 moonshot/kimi-k2.6
)
for m in "${MODELS[@]}"; do
  if [[ " $SKIP_MODELS " == *" $m "* ]]; then skip "$m"; continue; fi
  log="$SMOKE/log-s1-${m//\//-}.txt"
  if $VB run --model "$m" --problem VB-T1-001 --language python \
        --output-dir "$SMOKE/s1" >"$log" 2>&1; then
    ok "$m"
  else
    bad "$m — $(grep -iE 'error|Traceback|unsupported|invalid' "$log" | head -1 | cut -c1-140)"
  fi
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
$VB run --model gpt-5.6-sol --problem VB-T1-001 \
   --output-dir "$SMOKE/s2/default" >"$SMOKE/log-s2-default.txt" 2>&1
$VB run --model openai-pro/gpt-5.6-sol --problem VB-T1-001 \
   --output-dir "$SMOKE/s2/pro" >"$SMOKE/log-s2-pro.txt" 2>&1
$PY - "$SMOKE/s2" <<'PY'
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
for lbl, r in (("default", base), ("pro", pro)):
    print(f"  {lbl:<8}: model={r['model']!r} wall={r['wall_time_s']:.1f}s "
          f"out_tok={r['output_tokens']} check={r['check_pass']}")
w = pro["wall_time_s"] / max(base["wall_time_s"], 0.01)
t = pro["output_tokens"] / max(base["output_tokens"], 1)
print(f"  ratio   : wall x{w:.1f}   out_tok x{t:.1f}")
print("  VERDICT : " + ("pro ENGAGED — distinct cost/latency signature"
      if w > 1.4 or t > 1.4 else
      "*** pro may be SILENTLY IGNORED — indistinguishable from default ***"))
print(f"  model field distinguishable in JSONL: "
      f"{'yes' if pro['model'] != base['model'] else 'NO — charts cannot tell them apart'}")
if pro["wall_time_s"] > 100:
    print(f"  WARNING : {pro['wall_time_s']:.0f}s is near the 120s client timeout")
PY
fi

# ---------------------------------------------------------------- S3
# Prompt caching. This is the SECOND call sharing the ~28k SKILL.md
# system prefix (S2's default run was the first), so a working cache
# should report cached_tokens > 0 here and 0 there.
if want s3; then
note "S3  cache accounting (2nd call on the same 28k prefix)"
$VB run --model gpt-5.6-sol --problem VB-T1-002 \
   --output-dir "$SMOKE/s3" >"$SMOKE/log-s3.txt" 2>&1
$PY - "$SMOKE" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
def show(label, sub):
    for f in sorted((d / sub).rglob("*.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip(): continue
            r = json.loads(line)
            i, c = r.get("input_tokens", 0), r.get("cached_tokens", 0)
            pct = (100 * c / i) if i else 0
            print(f"  {label:<12} {r['model'][:26]:<26} input={i:>6} "
                  f"cached={c:>6} ({pct:.0f}%)")
show("S2 1st call", "s2/default")
show("S3 2nd call", "s3")
print("  (OpenAI auto-caches prompts >=1024 tokens; a 0 on the 2nd call means")
print("   either the prefix differs per problem or cached_tokens isn't plumbed)")
print("\n  --- all providers, S1 rows ---")
show("S1", "s1")
PY
fi

# ---------------------------------------------------------------- S5
# Canary: every target path end-to-end on one cheap model. Proves the
# vera-HEAD / aver-0.27 / ailang toolchains all work through the
# harness before 40 target-runs depend on them.
if want s5; then
note "S5  all six targets, one problem, one model"
run_target () {  # label, extra args...
  local lbl=$1; shift
  if $VB run --model claude-sonnet-5 --problem VB-T1-001 "$@" \
        --output-dir "$SMOKE/s5" >"$SMOKE/log-s5-$lbl.txt" 2>&1; then
    ok "canary $lbl"
  else
    bad "canary $lbl — $(grep -iE 'error' "$SMOKE/log-s5-$lbl.txt" | head -1 | cut -c1-120)"
  fi
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
