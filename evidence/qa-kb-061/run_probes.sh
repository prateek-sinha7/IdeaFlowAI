#!/bin/sh
# QA-KB-061 analyzer probes. Edits NO repo file: probe_fix_plugin.py patches live module
# objects in-process (lazily, after the repo conftest pins DATABASE_URL); probe_siblings_test.py
# reuses the repo's own harness from test_rest_run_launch_api. Offline: sqlite, stub engine.
# Run from the repo root:  sh evidence/qa-kb-061/run_probes.sh
set -u
E="$PWD/evidence/qa-kb-061"
cd backend
PY=.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:///:memory: PYTHONPATH="$E:."
T=tests/integration/api
run() { echo; echo "### $1"; shift; "$@" 2>&1 | sed -e 's/^\.*//' | grep -E "^(B[0-9]|S[0-9]|T |FAILED|[0-9]+ (passed|failed))|passed|failed" | cut -c1-290; }

echo "# 1. HEAD behaviour, the two files the card lists"
unset PROBE_FIX_A PROBE_FIX_C
run "launch file, as shipped"    $PY -m pytest $T/test_rest_run_launch_api.py    -p probe_fix_plugin -q -p no:cacheprovider -W ignore
run "revisions file, as shipped" $PY -m pytest $T/test_rest_revisions_api.py     -p probe_fix_plugin -q -p no:cacheprovider -W ignore

echo; echo "# 2. Proposed fix A in-process: _launch_run_core resolves the parent from (request_source_workflow_run_id or source_workflow_run_id)"
run "launch file, fix A only"    env PROBE_FIX_A=1 $PY -m pytest $T/test_rest_run_launch_api.py -p probe_fix_plugin -q -p no:cacheprovider -W ignore

echo; echo "# 3. Fixture fix C in-process: events after agent_start carry the open agent_id"
run "launch file, fix C only"    env PROBE_FIX_C=1 $PY -m pytest $T/test_rest_run_launch_api.py -p probe_fix_plugin -q -p no:cacheprovider -W ignore
run "revisions file, fix C only" env PROBE_FIX_C=1 $PY -m pytest $T/test_rest_revisions_api.py  -p probe_fix_plugin -q -p no:cacheprovider -W ignore
run "launch file, fix A + C"     env PROBE_FIX_A=1 PROBE_FIX_C=1 $PY -m pytest $T/test_rest_run_launch_api.py -p probe_fix_plugin -q -p no:cacheprovider -W ignore

echo; echo "# 4. Sibling and stale-test probes (B1-B4 stale-test direction, S1/S1b/S3 siblings)"
run "probes at HEAD behaviour"   $PY -m pytest "$E/probe_siblings_test.py" -p probe_fix_plugin -q -s -p no:cacheprovider --rootdir="$E" -W ignore
run "probes with fix A applied"  env PROBE_FIX_A=1 $PY -m pytest "$E/probe_siblings_test.py" -p probe_fix_plugin -q -s -p no:cacheprovider --rootdir="$E" -W ignore

echo; echo "# 5. Which *_revision types does POST /api/runs accept, and is the owned source linked as parent_run_id?"
run "all ten *_revision types at HEAD behaviour"  $PY -m pytest "$E/probe_revision_types_test.py" -p probe_fix_plugin -q -s -p no:cacheprovider --rootdir="$E" -W ignore
run "all ten *_revision types with fix A applied" env PROBE_FIX_A=1 $PY -m pytest "$E/probe_revision_types_test.py" -p probe_fix_plugin -q -s -p no:cacheprovider --rootdir="$E" -W ignore

echo; echo "# 6. Found while regression-checking fix A: three stale _mint_revision_row tests (caller_tier). Fix D = pass caller_tier in-process."
run "test_phase5_chaining.py as shipped"   $PY -m pytest tests/agents/test_phase5_chaining.py   -p probe_fix_plugin -q -p no:cacheprovider -W ignore
run "test_chain_context_v3.py as shipped"  $PY -m pytest tests/agents/test_chain_context_v3.py  -p probe_fix_plugin -q -p no:cacheprovider -W ignore
run "test_phase5_chaining.py, fix D"       env PROBE_FIX_D=1 $PY -m pytest tests/agents/test_phase5_chaining.py  -p probe_fix_plugin -q -p no:cacheprovider -W ignore
run "test_chain_context_v3.py, fix D"      env PROBE_FIX_D=1 $PY -m pytest tests/agents/test_chain_context_v3.py -p probe_fix_plugin -q -p no:cacheprovider -W ignore
