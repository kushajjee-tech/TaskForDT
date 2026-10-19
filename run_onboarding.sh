#!/usr/bin/env bash
# One command from "connect" to "first trusted consolidated P&L", timed.
# Usage: ./run_onboarding.sh            (mode from .env, default sample)
#        ./run_onboarding.sh --fresh    (wipe warehouse + state first, to time a brand-new onboarding)
#        SOURCE_MODE=sample ./run_onboarding.sh --fresh   (override the mode in .env)
set -uo pipefail
cd "$(dirname "$0")"
MODE_OVERRIDE="${SOURCE_MODE:-}"
[ -f .env ] && set -a && . ./.env && set +a
export SOURCE_MODE="${MODE_OVERRIDE:-${SOURCE_MODE:-sample}}"   # dbt reads it to pick the mapping seed
MODE="$SOURCE_MODE"

if [ "${1:-}" == "--fresh" ]; then
  echo "Fresh onboarding: clearing warehouse and sync state (mappings are kept)"
  rm -rf warehouse state/state.json
fi

step() { local name="$1"; shift; local t0=$(python3 -c 'import time;print(time.time())')
  echo; echo "=== $name ==="; "$@"; local rc=$?
  local t1=$(python3 -c 'import time;print(time.time())')
  python3 - "$name" "$t0" "$t1" <<'PY'
import json,sys,pathlib
p=pathlib.Path("state/.timing_tmp.json"); d=json.loads(p.read_text()) if p.exists() else {}
d[sys.argv[1]]=float(sys.argv[3])-float(sys.argv[2]); p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(d))
PY
  return $rc; }

rm -f state/.timing_tmp.json
step "1. Extract + load (QuickBooks -> raw)" python3 -m extract.extract --mode "$MODE" || exit 1
step "2. Map chart of accounts (rules + AI)" python3 -m ai.coa_mapper --mode "$MODE" || exit 1
step "3. Transform + test (dbt build)" bash -c "cd dbt && dbt build --profiles-dir . --quiet" ; DBT_RC=$?
python3 - "$MODE" <<'PY'
import json,sys,pathlib,datetime
d=json.loads(pathlib.Path("state/.timing_tmp.json").read_text())
pathlib.Path("state/onboarding_timing.json").write_text(json.dumps({"mode":sys.argv[1],
 "finished_at":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),"steps":d,"total_seconds":sum(d.values())},indent=2))
PY
echo; echo "=== 4. Platform health ==="
python3 -m health.health_report
echo; echo "=== 5. Results report ==="
python3 -m health.onboarding_report
exit $DBT_RC
