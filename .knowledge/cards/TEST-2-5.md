---
id: TEST-2-5
type: test
status: done
area: [sse, workflow, agents, evals, artifacts, runtime]
summary: >-
  2.5 Capability registry & ports/adapters (register part 08) — 63 registered
  capabilities
source: .planning/TEST-REGISTER.md#2-5-capability-registry-ports-adapters-register
covers: [BE-CAP-01, BE-CAP-02, BE-CAP-03, BE-CAP-04, BE-CAP-05]
---

### 2.5 Capability registry & ports/adapters  (register part 08) — **63 registered capabilities**

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-CAP-01 | `@register` binds `(kind,name)→instance` into `_IMPLS`, adds to `_KNOWN`, records `user_allowed`; **two surfaces** — `_KNOWN` literal (compiler, impl-free at compiler import) vs runtime `discover()` | `pytest tests/agents/test_registry_capabilities.py` | 🟢 |
| BE-CAP-02 | **Registry drift guard: `len(_KNOWN)==63`** and `==_EXPECTED_NAMES`; `resolve()` static-dict (no `getattr`/`eval`/`importlib`); unknown → `KeyError`, known-unbound → `RuntimeError` | `pytest …test_registry_capabilities.py` (asserts 63) | 🟢 |
| BE-CAP-03 | **Add a capability = add module + `@register` + `discover()` + bump `_KNOWN` — no kernel edit** (the architecture promise) | new-capability test fixture compiles + resolves | 🟢 |
| BE-CAP-04 | **Import-linter 4 contracts kept / 0 broken** (engine ↛ app.api; workflows/capabilities/runtime ↛ {execution_engine, app}) | `lint-imports` | 🟢 |
| BE-CAP-05 | Capability inventory by kind exists & resolvable: `strategy`(single_shot/task_loop/fanout_batch/wave_scheduler), `merge`(copy_disjoint/git_3way/json/html_fragment), `validator`(html_static/html_render/design_quality/spec_plan_coverage/task_done_when/code_compile/code_test/code_lint/api_prefix), `deliverable`(single_file/serialized_sandbox/streamed_text/ppt/repo_diff), `context_provider`(opendesign/previous_run/repo), `task_parser`(heading_tasks/json_tasks), `gate`(human/validation/approval/security), `tool`(workspace/prototype/prototype_emit_only/planning/spawn_subagents), `post_step`(revision_validation/api_prefix_audit), `compaction`(html_skeleton), `runtime`(langchain_deepagents), `prompt`(default), `skill`(ui/disk/template/repo), `hook`(behavioral/secret_scan/otel_tracing), `runtime_env`(local), `mcp_server`/`integration_provider`(github/gitlab/jira/slack/…) | `pytest tests/agents/test_registry_capabilities.py` membership + per-impl tests | 🟢 |
