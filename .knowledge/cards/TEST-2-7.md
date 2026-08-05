---
id: TEST-2-7
type: test
status: done
area: [workflow, agents, runtime]
summary: >-
  2.7 Workspace / RuntimeEnvironment + safe local exec (register parts 09/10)
source: .planning/TEST-REGISTER.md#2-7-workspace-runtimeenvironment-safe-local-exec
covers: [BE-RT-01, BE-RT-02, BE-EXEC-01, BE-EXEC-02]
---

### 2.7 Workspace / RuntimeEnvironment + safe local exec  (register parts 09/10)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-RT-01 | 4 runtime/workspace ports kernel-side interface-only (ECS-swap seam); `LocalSandboxRuntime` provisions a traversal-proof `LocalWorkspace` (`..` escape → `ValueError`); sole git-subprocess owner (hardened clone) | `pytest tests/agents/test_local_runtime.py` (8); `lint-imports` | 🟢 |
| BE-RT-02 | Repo workflow class end-to-end no-exec (`sample_brownfield`), zero `if repo:` engine fork; SC-001 holds | `pytest tests/agents/test_sample_brownfield_workflow.py` (3); `grep "if repo" execution_engine/` → 0 | 🟢 |
| BE-EXEC-01 | Hardened `exec_command`: argv-only (no shell), allow-list python/python3/pytest/ruff (deny beats allow), scrubbed env, rlimits cpu60s/mem512MB + 120s group-kill, 64KB truncation; **deny-default until granted** | `pytest tests/agents/test_local_runtime.py test_exec_runs.py` | 🟢 |
| BE-EXEC-02 | Code validators (compile/test/lint) reach exec only via workspace handle; refuse-before-spawn if exec ungranted (never silent pass); SC-001 proof via `sample_exec_workflow` | `pytest tests/agents/test_code_validators.py` | 🟢 |
