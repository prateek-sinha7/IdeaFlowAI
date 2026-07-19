---
phase: 47
slug: uploads-durability-r2
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
---

# Phase 47 — Validation Strategy

> Sourced from 47-RESEARCH.md "## Validation Architecture"; per-task map filled by the planner (47-01-PLAN.md).

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (python3.11, NO venv, ABSOLUTE cd to `backend/`) |
| **Quick run command** | `python3.11 -m pytest tests/unit/test_run_files_upload.py tests/agents/test_uploaded_files_provider.py -q` |
| **Full suite command** | quick + `tests/agents/test_restart_resume.py` + the 5 characterization files + `tests/agents/test_banned_patterns.py` -q, then `/opt/homebrew/bin/lint-imports` |
| **Estimated runtime** | quick ~8s · battery ~60s |

**NEVER the full backend suite. NEVER live Bedrock in executors.**

**Pre-phase baseline (47-RESEARCH, 2026-07-19):** test_run_files_upload 20 ✅ · test_uploaded_files_provider 16 ✅ (drift-guard `test_known_count_is_sixty_nine`=69, `test_sc001_...` green) · test_restart_resume 16 ✅ / 1 red (KAN-88 `test_waiting_for_user_run_is_rearmed_not_driven` — stays) · goldens 10 ✅ · lint 4/0. Verify BY DELTA.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Task 1 | 47-01 | 1 | RESUME-12 | T-47-01, T-47-03, T-47-04, T-47-05 | Durable rows written ONLY from Layer-2 `ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)` (never client payload); caps + 415 before ANY write; best-effort `SQLAlchemyError`-only degrade; ZERO image storage | unit (DB-backed, in-mem SQLite) | `cd backend && python3.11 -m pytest tests/unit/test_run_files_upload.py -q` | ✅ extend | ✅ |
| Task 2 | 47-01 | 1 | RESUME-13 | T-47-02, T-47-06 | Durable read via `ctx.scoped_store.list_refs` default-deny (cross-owner → `[]` → `{}`); provider kernel-pure (no `app.*` import); `.uploads/` re-materialization fence confirm-only (no engine edit) | unit + scripted-engine integration | `cd backend && python3.11 -m pytest tests/agents/test_uploaded_files_provider.py -q` | ✅ extend | ✅ |

**Phase gate (after both tasks):** quick + `test_restart_resume.py` (expect 16 ✅ / 1 KAN-88 red — the SOLE red) + 5 characterization goldens (10/10, SNAPSHOT_UPDATE unset) + `test_banned_patterns.py` + `/opt/homebrew/bin/lint-imports` (4/0) + INV-1 name-literal grep → 0.

## Wave 0 Requirements

Both target test FILES already exist and pass at baseline — Wave 0 here is the RED-before-change extension of each (add the failing case, observe it fail on HEAD, then implement). No new file, no framework install (pytest/pytest-asyncio present).

- [x] `backend/agents/artifacts/graph.py` — append `upload_text` to `ARTIFACT_KINDS` (additive, no migration) — Task 1 prerequisite.
- [x] `tests/unit/test_run_files_upload.py` — add (RED first): durable `upload_text` rows present + content-exact (sidecar + manifest, generic labels, `task_id=None`, owner/workspace correct); best-effort degrade (patched `SQLAlchemyError` → 200 + loud warning); no-row-on-415/413; text-less upload writes manifest row only.
- [x] `tests/agents/test_uploaded_files_provider.py` — add (RED first): `_FakeScopedStore`; wiped-sandbox fallback; disk-body == durable-body byte-equivalence; disk-wins; neither → `{}`; cross-owner denial (empty `list_refs`) → `{}`; wiped-sandbox 3-agent sticky proof via `engine._compose_context_message`.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live upload→crash→resume doc-context proof on real Bedrock | RESUME-12/13 | live env | Milestone-end pass (orchestrator-owned; per the defer-live-verification convention, offline gates bind phase completion) |

## Validation Sign-Off

- [x] All tasks have an automated `<verify>` command · [x] test-map continuity (every requirement mapped) · [x] Wave 0 coverage (both suites + graph.py) · [x] no watch-mode · [x] latency <60s (quick ~8s, battery ~60s) · [x] nyquist_compliant flipped

**Approval:** approved (planner, 2026-07-19) — one plan (47-01), two tasks; both requirements mapped to automated DB-backed / scripted-engine unit tests; RED-before-change enforced per task; verify BY DELTA.
