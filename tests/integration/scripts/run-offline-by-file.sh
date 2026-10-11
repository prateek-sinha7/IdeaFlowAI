#!/bin/sh
# Offline integration suite, ONE test file at a time, 5s pause before each,
# running total after every file.
#
#   sh tests/integration/scripts/run-offline-by-file.sh                  # all files
#   sh tests/integration/scripts/run-offline-by-file.sh --headed         # watch it drive
#   sh tests/integration/scripts/run-offline-by-file.sh 07_run_detail    # one area
#
# Same offline guarantee as run-all-offline.sh: pytest.ini's `-m "not live"`
# stays in force, so nothing here calls Bedrock.
# Each file is its own pytest session, so test-runs/ gains a
# <minute>-offline-by-file folder about once a minute. Nothing is ever deleted.
# POSIX sh, like run-all-offline.sh.
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
E2E=$(cd "$SCRIPT_DIR/../e2e" && pwd)
PY="$E2E/.venv/bin/python"
HEADED=""
[ "${1:-}" = "--headed" ] && { HEADED="--headed"; shift; }
FILTER=${1:-}
LOG=/tmp/integ-by-file-$(date +%Y%m%d-%H%M%S)

[ -x "$PY" ] || { echo "no $PY — run run-all-offline.sh once to build it"; exit 1; }
for u in http://localhost:3000/login http://localhost:8000/docs; do
  c=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$u" 2>/dev/null || true)
  [ "$c" = "200" ] || { echo "$u answered ${c:-000}, not 200 — start it first"; exit 1; }
done

mkdir -p "$LOG"
# Guarded because this script runs under `set -u` only, NOT `set -e`: an
# unguarded `cd` failure would not stop anything. The next line would then run
# `find suites` in whatever directory we happened to be in, match nothing, and
# the script would report "0 files" and exit 0 — a silent pass that ran no tests
# at all. (SC2164)
cd "$E2E" || { echo "cannot cd to $E2E — nothing was run"; exit 1; }
find suites -name 'test_*.py' | grep -- "$FILTER" | sort > "$LOG/files.txt"
total=$(wc -l < "$LOG/files.txt" | tr -d ' ')
echo "$total files, logs in $LOG"

num() { echo "$1" | grep -oE "[0-9]+ $2" | grep -oE '^[0-9]+' | head -1; }

TP=0; TF=0; TS=0; TX=0; i=0
while read -r f; do
  i=$((i+1))
  name=$(echo "$f" | sed 's|^suites/||; s|\.py$||')
  log="$LOG/$(echo "$name" | tr '/' '_').log"
  sleep 5
  "$PY" -m pytest --run-name offline-by-file $HEADED "$f" > "$log" 2>&1 < /dev/null
  sum=$(grep -E '(passed|failed|skipped|error|xfailed|deselected|no tests ran).* in [0-9.]+s' "$log" | tail -1)
  p=$(num "$sum" passed); f1=$(num "$sum" failed); e=$(num "$sum" 'errors?')
  s=$(num "$sum" skipped); x=$(num "$sum" xfailed)
  p=${p:-0}; s=${s:-0}; x=${x:-0}; f1=$(( ${f1:-0} + ${e:-0} ))
  TP=$((TP+p)); TF=$((TF+f1)); TS=$((TS+s)); TX=$((TX+x))
  printf '[%d/%d] %-52s %3dP %3dF %3dS %3dX  |  TOTAL: %d passed, %d failed, %d skipped, %d xfail, total %d\n' \
    "$i" "$total" "$name" "$p" "$f1" "$s" "$x" "$TP" "$TF" "$TS" "$TX" $((TP+TF+TS+TX)) | tee -a "$LOG/tally.txt"
done < "$LOG/files.txt"

echo "DONE: $TP passed, $TF failed, $TS skipped, $TX xfail (known open bugs), total $((TP+TF+TS+TX)) — logs in $LOG" | tee -a "$LOG/tally.txt"
