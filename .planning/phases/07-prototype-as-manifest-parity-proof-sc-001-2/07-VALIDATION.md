---
phase: 7
slug: prototype-as-manifest-parity-proof-sc-001-2
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-08
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **This is a parity-proof phase: validation IS the deliverable.** The existing CI gates already encode every required parity check; Phase 7's job is to keep them green while routing behavior through capabilities, then flip the deletion ratchets. Source: `07-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` + `pytest-asyncio` (Python 3.11, no venv) |
| **Config file** | `backend/pyproject.toml` (`[tool.importlinter]` + `[tool.vulture]`; pytest config conventional) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -x` |
| **Full suite command** | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |
| **Adjacent gates** | `cd backend && lint_imports` (import-linter) · `cd backend && vulture app/ agents/` (orphan check before 07-05 deletes) |
| **Estimated runtime** | ~60–120s full suite (offline; Chromium/Bedrock/Postgres degrade cleanly) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -x` (fast parity + ratchet pulse)
- **After every plan wave:** Run `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` + `lint_imports` + `vulture app/ agents/`
- **Before `/gsd-verify-work`:** Full suite green + all 5 characterization snapshots green + migration-ledger ratchet green (L1–L13 ☑) + banned-pattern hard-fail green + import-linter green + 0C ≥50% gate green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

> Strategy-level map keyed by plan + requirement (tasks are created by the planner; the executor refines this into per-task rows). Plan IDs follow CONTEXT D-05 / ROADMAP 07-01..07-05. **PLAN.md frontmatter `wave:` is authoritative** — the waves below are the dependency-implied grouping (07-01/02/03 build capabilities; 07-04 routes + proves parity; 07-05 deletes).

| Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01 | 1 | PARITY-01 | `resolve` is static dict lookup, never `getattr`/`eval` (T-04-01) | unit + characterization | `pytest tests/agents/test_characterization_prototype.py -k event` + new `test_strategies.py` / `test_capability_resolution.py` | ✅ char · ❌ W0 unit | ⬜ pending |
| 07-02 | 1 | PARITY-02 | resolvers read sandbox via traversal-proof `read`/`path_for` | characterization + unit | `pytest tests/agents/test_characterization_app_builder.py` + `test_deliverable_resolvers.py` | ✅ char · ❌ W0 unit | ⬜ pending |
| 07-02 | 1 | PARITY-03 | `previous_run` keeps `assert_owns` before seeding (INV-8) | unit + characterization | `pytest tests/agents/test_characterization_od_prototype.py` + `test_context_providers.py` / `test_heading_tasks_parser.py` | ✅ char · ❌ W0 unit | ⬜ pending |
| 07-02 | 1 | PARITY-07 | carousel sanitize moves from BOTH sites (engine.py:1394 + :1916) | characterization | `pytest tests/agents/test_characterization_od_ppt.py` | ✅ | ⬜ pending |
| 07-03 | 1 | PARITY-04 | `html_skeleton` behavior-preserving; ≥50% reduction held | unit (deterministic gate) | `pytest tests/agents/test_phase3_compaction.py` (re-pointed to capability) | ✅ re-point | ⬜ pending |
| 07-04 | 2 | PARITY-05 | 3 flavors run from manifests; no kernel name-branch | characterization | `pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py` | ✅ | ⬜ pending |
| 07-04 | 2 | PARITY-09 | 5-pipeline deliverable byte + semantic event parity | characterization | `pytest tests/agents/test_characterization_*.py` | ✅ | ⬜ pending |
| 07-05 | 3 | PARITY-06 | L1–L13 deleted; `pipeline.py` gone; `vulture` confirms orphaned first | ratchet | `pytest tests/agents/test_migration_ledger.py` | ✅ | ⬜ pending |
| 07-05 | 3 | PARITY-08 | INV-1 kernel grep → 0; hard-fail on reintroduction | ratchet | `pytest tests/agents/test_banned_patterns.py` | ✅ flip + scope | ⬜ pending |
| 07-05 | 3 | PARITY-10 (L16 re-verify) | cross-owner parent-run denial propagates | CHECK | `pytest tests/agents/test_parent_run_ownership.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> New unit coverage + test-coupling migrations the executor must land before/with the capability work (from RESEARCH § Wave 0 Gaps). The existing characterization suite already covers the 5-pipeline parity surface.

- [ ] `tests/agents/test_strategies.py` — drive `single_shot` + `task_loop` from a compiled `Step` (PARITY-01 acceptance: "a unit test drives both strategies from a compiled Step")
- [ ] `tests/agents/test_deliverable_resolvers.py` — `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` resolution from a sandbox fixture
- [ ] `tests/agents/test_context_providers.py` — `opendesign`/`previous_run` `load(ctx)` block output + generic injector ordering
- [ ] `tests/agents/test_heading_tasks_parser.py` — `## Task N:` + `<tasks>` fallback → `Task[]` (port `_count_plan_tasks`/`_extract_task_block` cases)
- [ ] `tests/agents/test_capability_resolution.py` — `registry.resolve(kind,name)` returns the right impl; unknown name raises; `is_registered` unchanged
- [ ] **Re-point** `test_phase3_compaction.py` from `engine._extract_html_skeleton`/`_build_context_message` → the `html_skeleton` capability + injector (keep the ≥50% assertion)
- [ ] **Update** `test_manifest_parity.py:26` to not import `SKIP_PLANNER_FOR_PROTOTYPE` from the deleted `pipeline.py`
- [ ] **Update** `_scripted_model.py:425` (`engine_mod.ALWAYS_CLARIFY = False`) for L6 deletion — replace with the manifest-sourced clarify path or remove the monkeypatch

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live render-validated build (real Chromium) | PARITY-05/09 | Headless Chromium absent locally — `render_check` degrades to `available=False` offline; full render only on live env | Defer to end-of-milestone live pass (run a real prototype build with Chromium present; confirm fix-loop render lines appear) |
| Live LLM build (real Bedrock) | PARITY-05/09 | Offline harness uses `ScriptedFakeChatModel`; live model not exercised by the parity suite | Defer to end-of-milestone live pass (one live `prototype` run; confirm deliverable + event stream) |

> Per project convention ([[defer-live-verification-to-milestone-end]]): parity is proven **offline** by design (the characterization suite runs fully offline). Live Chromium/Bedrock checks are deferred to an end-of-milestone live pass and do not block phase completion.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (the 5 new unit files + 3 test-coupling migrations above)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
