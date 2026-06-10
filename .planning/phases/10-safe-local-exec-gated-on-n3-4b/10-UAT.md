---
status: complete
phase: 10-safe-local-exec-gated-on-n3-4b
source: [10-01-SUMMARY.md, 10-02-SUMMARY.md, 10-03-SUMMARY.md, 10-04-SUMMARY.md, 10-05-SUMMARY.md]
started: 2026-06-10T19:34:13Z
updated: 2026-06-10T19:40:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Hardened argv exec layer (no-shell, scrubbed env, caps, kill, truncation)
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_local_runtime.py -q
  All pass: exec deny-default preserved (T-09-01-02); pre-spawn allow/deny with
  deny-beats-allow; scrubbed env (no host-credential-class key survives); wall-clock
  kill; 64KB/stream truncation; rlimit mechanism. Plus grep shell=True over
  backend/app/agents/runtime/ + backend/agents/ = 0 (IN-02 surface gone).
result: pass
evidence: 20 passed in 4.30s; grep shell=True over app/agents/runtime/ + agents/ → 0 (run 2026-06-10, user delegated execution to Claude)

### 2. exec_runs audit trail (migration 0018 + scoped default-deny store)
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_exec_runs.py -q
  All pass: 0018 reversible offline (upgrade → downgrade -1 → upgrade); allowed/
  denied/killed outcomes written scoped (owner_id+workspace_id); cross-owner read
  returns empty; KernelServices.record_exec_run degrades best-effort offline
  (never aborts the run).
result: pass
evidence: 7 passed in 0.27s

### 3. Compile-time exec enforcement (trust ceiling + GRANT-PATH + D-01 + INV-12)
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_compiler_trust.py tests/agents/test_compiler.py tests/agents/test_tool_permissions.py -q
  All pass: file/builtin exec grant survives intersect_permissions (Step.tools.exec
  True); user/db exec/network/secrets grant raises CompilerError naming grant + step;
  exec step missing security OR approval gate raises CompilerError naming the missing
  gate (no auto-injection); no-grant path parity across trust levels. Plus INV-12:
  grep -rnE "ExecutionPolicy\.check" backend/ --include=*.py → 0 (forward surface deleted).
result: pass
evidence: 37 passed in 0.13s; ExecutionPolicy.check grep → 0

### 4. Security + approval gates (tier 2) and §15 host seam
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_gates.py -q
  All pass: file/builtin exec step with approval declared + constrained profile →
  GATE_PASS; network/secrets requests BLOCK byte-identical; exec without approval
  BLOCKS (D-01); approval gate pauses first exec via run_human_gate with the D-04
  policy-snapshot payload (allow-list + caps, no creds/argv); prior approval-pass
  gate_events row short-circuits re-pause (D-03); offline → wait_human, never
  auto-approve; host seam binds exec workspace ONLY for exec-granting plans.
result: pass
evidence: 32 passed in 0.11s

### 5. Code validators reach exec via handle only + EXEC-02/SC-001 proof
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_code_validators.py tests/agents/test_registry_capabilities.py -q
  All pass: code_compile/code_test/code_lint registered (registry 50→53), reach exec
  ONLY via target.runner.workspace.exec_command(argv); VALIDATOR-DENY: ungranted exec
  → explicit refusal Issue, zero spawns, no escaping PermissionError; fixture repo
  compile+test PASS offline, seeded F401 flagged; sample_exec_workflow manifest
  compiles to Step.tools.exec=True with both gates; zero engine edits (SC-001).
  Plus grep subprocess over the three validator files = 0.
result: pass
evidence: 90 passed in 1.79s; subprocess.run/Popen grep over agents/capabilities/validators/ → 0

### 6. Review-trio closure (IN-01/IN-02/IN-03) + N3 resolution + ledger ratchets
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_repo_diff.py tests/agents/test_migration_ledger.py -q
  All pass: repo_diff keys unparseable diff headers under synthetic __unparsed_N__
  (quoted/rename headers survive, normal path byte-identical, distinct keys); the
  IN-02 shell=True ledger ratchet + D11 ExecutionPolicy.check ratchet are green.
  Plus: MCP-04 sign-off docstring present near slack user_allowed=True in catalog.py;
  N3 flipped to RESOLVED in STATE.md + PROJECT.md citing 10-SPEC.md.
result: pass
evidence: 32 passed, 5 skipped in 1.90s (skips are the same benign class as Phase 9 — "no ☑ grep rows yet / CHECK-row gate handled out-of-band" placeholders; the D11 + IN-02 ratchet rows themselves are green). MCP-04 sign-off present in catalog.py (8 mentions); N3 RESOLVED in STATE.md (blocker row struck through citing 10-SPEC.md) and PROJECT.md (resolved row + roadmap line [x])

### 7. Phase-wide invariants: parity, runtime mandate, import boundaries
expected: |
  cd backend && env -u SNAPSHOT_UPDATE python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_banned_patterns.py -q
  All pass: the 5 characterization pipelines stay byte/event-identical (INV-3 — the
  whole exec stack is dormant for non-exec runs); no banned patterns (INV-13, no
  hand-rolled deep agent, no kernel workflow-name branch). /opt/homebrew/bin/lint-imports
  reports 4 contracts kept, 0 broken (gates/validators stay kernel-pure).
result: pass
evidence: 21 passed in 35.63s with `env -u SNAPSHOT_UPDATE`; lint-imports → Contracts: 4 kept, 0 broken

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
