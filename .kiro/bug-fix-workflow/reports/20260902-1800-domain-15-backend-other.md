# Domain 15 — backend·other — Run Report

**Date:** 2026-09-02T18:00:00Z  
**Workflow:** KiroCrew bug-fix-workflow (PLAN.md)  
**Domain:** 15 — backend·other  
**Cards:** 31  
**Outcome:** DONE — 18 CLOSED, 13 ESCALATED

---

## Summary

| Metric | Value |
|--------|-------|
| Cards in scope | 31 |
| CLOSED (fixes verified green) | 18 |
| ESCALATED (no fix warranted or product decision needed) | 13 |
| New FIX cards minted | 15 (FIX-423 – FIX-437) |
| New ISS cards spun off | 3 (ISS-640, ISS-641, ISS-642) |
| Post-domain open backlog | 106 work units (dedup regenerated) |

---

## Verification pass (2026-09-02, KiroCrew session)

The fixes were applied in the original Claude Code run (2026-08-31T17:34:32Z).
This KiroCrew session ran the full test suite for all witness files and confirmed:

| Group | Files | Tests | Result |
|-------|-------|-------|--------|
| G1 — B1 unit (ISS-098/101/106/118/120/185/357/637 + ISS-257) | 9 | 46 | ✅ 46 pass (after 2 fixes below) |
| G2 — B1 skills regressions (ISS-185) | 2 | 53 | ✅ 53 pass |
| G3 — B1 registry/parity (ISS-631/635/636) | 6 | 223 | ✅ 223 pass |
| G4 — B4 engine/factory (ISS-072/090/098/101/106/125/131/402 + FIX-BUGFIX-NR) | 17 | 193 | ✅ 192 pass + 1 skip (expected) |
| G5 — Revision (ISS-633) | 2 | 21 | ✅ 21 pass |
| **TOTAL** | **36** | **536** | **535 pass, 1 skip** |

### Two fixes applied during KiroCrew verification

**Fix A — `skill_staging.py` Windows encoding (`app/agents/skill_staging.py:183`)** → [FIX-485](../../../.knowledge/cards/20260902-1800-FIX-485.md)

`target.write_text(file_text)` was missing `encoding="utf-8"`, causing a
`'charmap' codec can't encode character '\u2192'` failure on Windows when the
`systematic-debugging` skill file contains an arrow character. Fixed by adding
`encoding="utf-8"` to the `write_text` call. The `read_text` call on the same
line already had the encoding; this was a Windows-only regression that did not
surface on Linux CI.

`test_staged_skill_carries_its_referenced_sibling_files` — was FAIL → now PASS.

**Fix B — stale `xfail(strict=True)` for ISS-257 (`tests/unit/test_register_password_echo.py:68`)** → [FIX-486](../../../.knowledge/cards/20260902-1800-FIX-486.md)

`test_a_too_short_password_is_never_echoed_back_in_the_422_body` was decorated
`@pytest.mark.xfail(reason="ISS-257 unfixed", strict=True)`. The underlying
ISS-257 defect was resolved by FIX-332 (already in the codebase). The test now
passes, but `strict=True` treats an unexpected pass as a failure. Removed the
`xfail` decorator; `@pytest.mark.issue("ISS-257")` retained for traceability.

---

## Card outcomes

### B1 — backend scattered (19 cards)

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-096 | ESCALATED | not reproducible (`test_od_ppt_validator_deck_reemission_contract` 14/14 green; path `od-ppt-validator` doesn't exist) |
| ISS-098 | CLOSED | FIX-425 — narrow `except asyncio.CancelledError` arm in `wave_scheduler.py:346` |
| ISS-101 | CLOSED | FIX-426 — `conversation.py` swapped onto bounded `read_events_of_types` |
| ISS-106 | CLOSED | FIX-428 — `close_checkpointer()` pool close now guarded by `asyncio.wait_for` |
| ISS-118 | CLOSED | FIX-429 — `_CONSTRUCTS_BUT_NEVER_INVOKES` emptied; 3 test seams added |
| ISS-120 | CLOSED | FIX-427 — `enable_cache: bool = True` keyword opt-out on `cached_invoke` |
| ISS-130 | ESCALATED | not reproducible — scratch_lock invariant already closed by KRN-005 |
| ISS-132 | ESCALATED | product decision: N sequential invocation gates per task is correct behaviour; three mutually-exclusive fix shapes exist but none is selected |
| ISS-156 | ESCALATED | not reproducible — all 3 named test files green |
| ISS-185 | CLOSED | FIX-431 — `stage_skills` now `shutil.copytree`s the catalog folder into the staged skill dir |
| ISS-357 | CLOSED | FIX-430 — both fixtures now do late `from app.main import app`; no bare `FastAPI()` |
| ISS-630 | ESCALATED | no application defect — ISS-102 live-model guard fires intentionally; stale test contract |
| ISS-631 | CLOSED | FIX-433 — `prototype-revision-analyzer/AGENT.md` fixed `pipeline_type`; 6 goldens regenerated |
| ISS-632 | ESCALATED | no application defect — ADR-0008 roster seam is correct; stale `[:2]` test harness |
| ISS-633 | CLOSED | FIX-432 — `engine.py:8058` swapped `agents[-1].id` to `_compiled_revision.steps[-1].agent_id` |
| ISS-634 | ESCALATED | card root cause wrong — `_ChunkStreamSanitizer` clean; real cause is ADR-0008 roster seam |
| ISS-635 | CLOSED | FIX-435 — `playwright_smoke_test` unioned into `_PLANNER_SKIP_IDS` and pinned clarify-defaults in both parity tests |
| ISS-636 | CLOSED | FIX-436 — `AgentLibraryData.ts:38-40` regenerated to `gate: null` for prototype-specify/plan/analyze |
| ISS-637 | CLOSED | FIX-434 — `WorkflowRun.__table_args__` now carries the sparse unique index mirroring migration 0040 |
| ISS-638 | CLOSED (partial) | FIX-437 — `previous_run._seed_existing_artifact` now guards re-entry; 4 stale test rows ESCALATED |

### B2 — `test_phase6_frontend_consistency.py` (2 cards)

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-079 | ESCALATED | not reproducible — both named tests pass today |
| ISS-636 | CLOSED | FIX-436 (same as B1 above — primary fix site is `AgentLibraryData.ts`) |

### B3 — workflow YAML fixes (2 cards)

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-173 | ESCALATED | not reproducible — both named tests pass today |
| ISS-174 | ESCALATED | not reproducible — option 1 exemption already applied upstream in parity tests |

### B4 — `engine.py` (8 cards)

| Card | Outcome | FIX |
|------|---------|-----|
| ADR-0002 | ESCALATED | requires a breaking wire-protocol rename + coordinated release; human go/no-go needed |
| FIX-BUGFIX-NESTED-REVISION | CLOSED | engine.py fix — see domain notes |
| ISS-072 | CLOSED | FIX-420 — `suppress_review_gate` publish/honour/restore in engine.py |
| ISS-090 | CLOSED | FIX-419 (ref) — `redoable` predicate + enforcement at 5 gate sites |
| ISS-094 | ESCALATED | already fixed upstream; no red reproducible |
| ISS-125 | CLOSED | FIX-421 — `_stamp_resume_marker` swapped onto `_max_event_seq` + `append_event_at_or_after` |
| ISS-131 | CLOSED | FIX-424 — `runs_agent_inline` on `ExecutionStrategy` port; ANDed into both `inline_gated` reads |
| ISS-402 | CLOSED | FIX-423 — `_CONSTITUTION_MAX_CHARS = 32_000` ceiling + truncation marker in `factory.py` |

---

## Escalated cards — human actions needed

| Card | Reason | Action required |
|------|--------|-----------------|
| ISS-132 | Three-way product decision on invocation gate suppression | Product owner to select fix shape |
| ISS-630 | Stale test contract (pre-revision-pipeline-refactor) | 4-test-writer rewrite of `test_revision_analyzer_integration.py` |
| ISS-632 | Stale `[:2]` roster in test harness conflicts with ADR-0008 | 4-test-writer: drop `[:2]`, derive counts from full roster |
| ISS-634 | Root cause wrong; real cause is ADR-0008 roster seam | 3-analyzer/4-test-writer re-decision; `execute(compiled_override=…)` is viable seam |
| ISS-638 (4 rows) | Stale test assertions freeze pre-refactor contracts | Human owner to confirm refactor is end-state; 4-test-writer rewrite |
| ADR-0002 | Wire-protocol rename; 94 AGENT.md keys, 122 .py files, 93 .ts/.tsx, 3 DB columns | Human go/no-go before any code moves |
| ISS-094 | Already fixed upstream; card can be closed | Mark ISS-094 resolved |
| ISS-096 | Path `od-ppt-validator` does not exist in codebase | Confirm path or close as invalid |
| ISS-130 | KRN-005 scratch_lock already resolves this | Mark ISS-130 resolved |
| ISS-156 | All named tests green | Confirm resolution or close |
| ISS-173 | Both named tests pass | Mark ISS-173 resolved |
| ISS-174 | Exemption already applied | Mark ISS-174 resolved |
| ISS-079 | Named tests pass | Mark ISS-079 resolved |

---

## New cards spun off during domain run

| Card | Brief |
|------|-------|
| ISS-640 | Middleware half of ISS-120 — `deep_agent_runner.py:283` needs a manifest-declared per-step cache flag |
| ISS-641 | (see domain notes) |
| ISS-642 | Stale `test_concierge_proposal_channels` + `test_revision_gating` harnesses — 4-test-writer rewrite needed |

---

## Backlog state after domain 15

`python3 bug-hunter/tools/dedup.py` regenerated successfully.

- **Before:** 112+ open cards
- **After:** 112 cards → 106 work units (15 families + 91 singletons, 22 batches)
- All 18 CLOSED domain-15 ISS cards have `status: resolved` in their `.knowledge/cards/` files and dropped off the open backlog automatically.

---

## Ready to commit

Files changed by the original Claude Code run (FIX-423 – FIX-437) plus the two
KiroCrew-session fixes:

- `backend/app/agents/skill_staging.py` — `write_text` encoding fix (KiroCrew Fix A)
- `backend/tests/unit/test_register_password_echo.py` — removed stale `xfail` for ISS-257 (KiroCrew Fix B)
- `backend/app/agents/factory.py` — FIX-423 (`_CONSTITUTION_MAX_CHARS`)
- `backend/agents/execution_engine/engine.py` — FIX-420/421/424 + FIX-BUGFIX-NESTED-REVISION
- `backend/agents/execution_engine/context.py` — FIX-420 `suppress_review_gate` field
- `backend/agents/capabilities/base.py` — FIX-424 `runs_agent_inline` port attribute
- `backend/agents/capabilities/strategies/wave_scheduler.py` — FIX-425
- `backend/agents/capabilities/context_providers/conversation.py` — FIX-426
- `backend/app/agents/cached_invoke.py` — FIX-427
- `backend/app/agents/checkpointer.py` — FIX-428
- `backend/tests/conftest.py` — FIX-429 (`_CONSTRUCTS_BUT_NEVER_INVOKES` emptied)
- `backend/app/agents/skill_staging.py` — FIX-431 (`shutil.copytree` sibling files)
- `backend/app/agents/skills_catalog.py` — FIX-431 (`skill_source_dir()`)
- `backend/agents/execution_engine/engine.py` — FIX-432 (`_compiled_revision.steps[-1].agent_id`)
- `backend/agents/workflows/prototype-revision-analyzer/AGENT.md` — FIX-433
- `backend/tests/agents/characterization/golden/` — FIX-433 (6 goldens regenerated)
- `backend/app/models/workflow.py` — FIX-434 (`WorkflowRun.__table_args__`)
- `backend/tests/agents/test_manifest_parity.py` — FIX-435
- `backend/tests/agents/test_id_alias_resolver.py` — FIX-435
- `frontend/src/components/workflow/AgentLibraryData.ts` — FIX-436
- `backend/tests/agents/test_agents_api_real_registry.py` — FIX-436
- `backend/tests/agents/test_phase6_frontend_consistency.py` — FIX-436
- `backend/app/agents/cached_invoke.py` — FIX-427
- `backend/tests/unit/test_register_password_echo_fixture_mounts_real_app.py` — FIX-430
- `backend/agents/capabilities/context_providers/previous_run.py` — FIX-437
- Plus: all new test files pinned to ISS-xxx cards (xfail markers cleared)

Operator should review git diff and commit.
