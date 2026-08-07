---
id: TEST-2-1
type: test
status: done
area: [sse, workflow, agents, evals, artifacts]
summary: >-
  2.1 Manifest → ExecutionPlan compiler (register part 04)
source: .planning/TEST-REGISTER.md#2-1-manifest-executionplan-compiler-register-par
covers: [BE-CMP-01, BE-CMP-02, BE-CMP-03, BE-CMP-04, BE-CMP-05, BE-CMP-06, BE-CMP-07, BE-CMP-08, BE-CMP-09, BE-CMP-10]
---

### 2.1 Manifest → ExecutionPlan compiler  (register part 04)

| ID | Guarantee (assert) | Verify | Status |
|---|---|---|---|
| BE-CMP-01 | `workflow.yaml` parses via `yaml.safe_load` only into a typed `WorkflowManifest`; 5 required fields present | `pytest tests/agents/test_manifest.py` (15) | 🟢 |
| BE-CMP-02 | Malformed manifest → `ManifestValidationError` **naming the field** | `pytest tests/agents/test_manifest.py -k missing` | 🟢 |
| BE-CMP-03 | **No-DSL (INV-5):** any key outside the allow-list at **every** nesting level (top/step/task_source/fanout/tools) → rejected; no `when:`/`if:`/`for:`/`${}` | `pytest tests/agents/test_compiler.py -k "dsl or strict or unknown"` (13) | 🟢 |
| BE-CMP-04 | Unknown capability ref (`strategy`/`gate`/`validator`/`deliverable`/`post_step`/…) → `CompilerError` **naming `(kind,name)`** | `pytest tests/agents/test_compiler.py -k unknown` | 🟢 |
| BE-CMP-05 | **Thin compiler (INV-1):** no `if pipeline_type ==` / `spec.id ==`, no `eval`/`exec` of manifest values | `pytest tests/agents/test_banned_patterns.py`; `grep -nE "if pipeline_type|spec.id ==|eval\(|exec\(" agents/workflows/compiler.py` → 0 | 🟢 CI-gated |
| BE-CMP-06 | Step DAG topo-validated: dup `agent` / `depends_on` cycle → `CompilerError`; empty `steps:[]` valid | `pytest tests/agents/test_compiler.py -k "dag or cycle or duplicate"` | 🟢 |
| BE-CMP-07 | **Trust-conditional compile (CAP-03):** `user`/`db` manifests reject not-`user_allowed` caps + privileged grants (`exec`/`network`/`secrets`/`spawn_subagents`) + ceiling-raising Limits | `pytest tests/agents/test_compiler.py -k "trust or user_allowed or privileged"` | 🟢 |
| BE-CMP-08 | All 18 in-repo manifests compile; `planner: run` + `clarify.defaults` verbatim (INV-3 parity traps) | `pytest tests/agents/test_manifest_coverage.py test_manifest_parity.py` (16+26) | 🟢 char-locked |
| BE-CMP-09 | `GET /api/workflows` lists manifest-derived workflows; `GET /api/workflows/{id}` → compiled config, unknown → 404 | `pytest tests/unit/test_workflows_api.py` (7); API calls | 🟢 |
| BE-CMP-10 | Run-history under `/api/runs/*` with IDOR owner-filter (cross-owner → 404) | `pytest tests/unit/test_runs_api.py` (11) | 🟢 |
