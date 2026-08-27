#!/bin/sh
# Run the whole offline integration suite.
#
#   sh tests/integration/scripts/run-all-offline.sh
#   sh tests/integration/scripts/run-all-offline.sh -k auth      # extra pytest args
#   sh tests/integration/scripts/run-all-offline.sh --headed     # watch it drive
#
# Offline means no Bedrock. Live tests are marked `live` and pytest.ini skips
# them by default, so nothing here can spend money.
#
# This script NEVER deletes anything under test-runs/. Every run adds a new
# timestamped folder and nothing is ever pruned, rotated or overwritten —
# clearing old runs is the user's call and no one else's. Comparing today's
# screenshots against last week's is the whole reason they are kept.
#
# POSIX sh on purpose — it is invoked as `sh <path>`, which ignores the shebang
# and would not give us bash. No arrays, no [[ ]], no `local`.
set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
E2E="$ROOT/tests/integration/e2e"
VENV="$E2E/.venv"
PY="$VENV/bin/python"

FRONTEND="${E2E_BASE_URL:-http://localhost:3000}"
BACKEND="${E2E_API_URL:-http://localhost:8000}"

say() { printf '%s\n' "$*"; }
fail() { printf '\n  %s\n\n' "$*" >&2; exit 1; }

# ── 1. environment ───────────────────────────────────────────────────────────
# Built on first run so this stays the only command anyone has to remember.

if [ ! -x "$PY" ]; then
    say "Setting up $VENV (first run only)…"
    if command -v uv >/dev/null 2>&1; then
        uv venv "$VENV" >/dev/null
        uv pip install -q -p "$VENV" -r "$E2E/requirements.txt"
    else
        python3 -m venv "$VENV"
        "$PY" -m pip install -q --upgrade pip
        "$PY" -m pip install -q -r "$E2E/requirements.txt"
    fi
    say "Done."
fi

# The suite drives the real Google Chrome, not a downloaded Chromium, so this
# is a hard requirement rather than something `playwright install` can fix.
[ -d "/Applications/Google Chrome.app" ] || \
    fail "Google Chrome not found at /Applications/Google Chrome.app — the suite drives the real browser."

# ── 2. the app has to be up ──────────────────────────────────────────────────
# Checked before launching a browser: 500 tests each failing on a connection
# refused is a slow, noisy way to learn the dev server is not running.

check() {
    # curl prints `000` itself on a connection failure, so `|| echo 000` would
    # append a second one and report `000000`.
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$1" 2>/dev/null || true)
    [ "${code:-000}" = "200" ] || \
        fail "$2 is not answering at $1 (got ${code:-000}). Start it and try again."
}
check "$FRONTEND/login" "Frontend"
check "$BACKEND/docs" "Backend"

# ── 3. spec/test consistency ─────────────────────────────────────────────────
# One second, no browser. Reports drift between the specs and the tests but does
# NOT block the run — a stale link is worth knowing about, not worth refusing to
# test over.

say ""
python3 "$ROOT/tests/integration/capture/_scenarios.py" || \
    say "  ^ spec/test drift above — not blocking this run"

# Refreshed every run so it can never go stale. A hand-kept checklist of 506
# rows is wrong within a day, and a wrong one is worse than none.
python3 "$ROOT/tests/integration/capture/_scenarios.py" --ledger

# ── 4. the suite ─────────────────────────────────────────────────────────────

say ""
cd "$E2E"

# Timestamp to compare run folders against. Without it, a run that collected no
# tests reports the PREVIOUS run's screenshots as if they were this one's.
MARKER=$(mktemp)

set +e
"$PY" -m pytest --run-name offline "$@"
STATUS=$?
set -e

# ── 5. where the evidence went ───────────────────────────────────────────────

LATEST=$(find "$ROOT/tests/integration/test-runs" -maxdepth 1 -mindepth 1 -type d -newer "$MARKER" 2>/dev/null | head -1)
rm -f "$MARKER"

if [ -n "$LATEST" ]; then
    say ""
    say "Screenshots: $LATEST"
    say "  $(find "$LATEST" -name '*.png' | wc -l | tr -d ' ') shots, $(find "$LATEST" -name '*-FAILED.png' | wc -l | tr -d ' ') on a failed step"
else
    say ""
    say "No screenshots written — no test ran."
fi

exit $STATUS
