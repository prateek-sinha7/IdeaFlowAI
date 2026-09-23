#!/bin/bash
# Watchdog: alert when a worker passes its budget. NEVER declares a stall —
# transcript mtime is not a liveness signal (proven: 42m run with frozen mtime).
# usage: watch.sh <transcript-file> <deadline-minutes> <worker-id>
F="$1"; MIN="$2"; W="$3"; END=$(( $(date +%s) + MIN*60 ))
while [ "$(date +%s)" -lt "$END" ]; do
  sleep 60
  AGE=$(( $(date +%s) - $(stat -f %m "$F" 2>/dev/null || date +%s) ))
  if [ "$AGE" -gt 120 ] && tail -c 20000 "$F" 2>/dev/null | grep -q "RESULT:"; then
    echo "WATCHDOG $W: DONE-EARLY — worker already returned, nothing to do."; exit 0
  fi
done
echo "WATCHDOG $W: OVER BUDGET (${MIN}m) and no RESULT line yet."
echo "ACTION: do NOT relaunch. Wait for its completion notification, or SendMessage it to wrap up."
