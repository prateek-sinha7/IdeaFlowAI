---
phase: 33
slug: concierge-compaction-a5
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-08
---

# Phase 33 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Offline-only: the full backend pytest suite HANGS (Chromium/Bedrock/Postgres-gated).
> Runner is `python3.11` (no venv). Live Concierge Q&A / multi-turn cache / live steering are LIVE-DEFERRED to Phase 34.
> Source of truth for the requirements→test map and security domain: `33-RESEARCH.md` §Validation Architecture + §Security Domain.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio, Hypothesis) |
| **Config file** | `backend/` project config; offline harness sets `RUNS_ROOT`→temp, `ENV=development` |
| **Quick run command** | `python3.11 -m pytest tests/agents/test_registry_capabilities.py -x` |
| **Full suite command** | `python3.11 -m pytest tests/agents/test_registry_capabilities.py tests/agents/test_chat_event_neutrality.py tests/agents/test_phase3_cutover_verify.py` (targeted register/parity suite — NEVER the full suite) |
| **Import gate** | `/opt/homebrew/bin/lint-imports` (expect 4 kept / 0 broken) |
| **Estimated runtime** | ~35 seconds (targeted suite) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command for the touched capability's test.
- **After every plan wave:** Run the full targeted register/parity suite + `/opt/homebrew/bin/lint-imports`.
- **Before `/gsd-verify-work`:** Targeted suite green + goldens byte-identical (`SNAPSHOT_UPDATE` unset) + banned-pattern gate (INV-13) green.
- **Max feedback latency:** ~35 seconds.

---

## Per-Task Verification Map

> Populated by the planner once task IDs exist. Each task's `<acceptance_criteria>` must map to an offline command below.
> Derived from `33-RESEARCH.md` §Validation Architecture requirements→test map:

| Requirement | Wave | Test Type | Automated Command | File Exists |
|-------------|------|-----------|-------------------|-------------|
| Registry lockstep — 3 new caps registered, `len(_KNOWN)==69`, `_KNOWN`==`_EXPECTED_NAMES` | compaction/provider wave | unit | `python3.11 -m pytest tests/agents/test_registry_capabilities.py -x` | ✅ (bump 66→69 in test_registry_capabilities.py:163, test_input_providers_run_images.py:132, test_uploaded_files_provider.py:200; add pairs to `_EXPECTED_NAMES`) |
| `discover()` binds impls — `resolve()` returns each new impl | compaction/provider wave | unit | `python3.11 -m pytest tests/agents/test_registry_capabilities.py -k discover` | ✅ pattern exists |
| `context_provider:conversation` returns compacted block; dormant un-gated | compaction/provider wave | unit | `tests/agents/test_conversation_provider.py` (clone `test_uploaded_files_provider.py`) | ❌ Wave 0 |
| `compaction:chat_history` under budget — long transcript ≤ budget, recent verbatim | compaction/provider wave | unit | `tests/agents/test_chat_history_compaction.py` | ❌ Wave 0 |
| Router escalation — free-form → Concierge; routable → zero-model existing channel | concierge wave | unit | `tests/unit/test_concierge_escalation.py` | ❌ Wave 0 |
| Proposal → channel — `propose_*` disposed via `set_review_response`/`apply_steering`/`_mint_revision_row` | concierge wave | unit | new proposal→channel test (mock the seams) | ❌ Wave 0 |
| INV-3 goldens byte-identical; concierge dormant on golden paths | integration wave | characterization | `SNAPSHOT_UPDATE` unset + `python3.11 -m pytest tests/agents/test_chat_event_neutrality.py` | ✅ (extend for any new event type) |
| Import purity — capabilities ↛ app; concierge app-impl ↛ kernel | all waves | lint | `/opt/homebrew/bin/lint-imports` | ✅ |
| INV-13 — `create_deep_agent` only in allow-listed module | concierge wave | banned-pattern | `python3.11 -m pytest tests/agents/test_banned_patterns.py` | ✅ |
| SC-001 — throwaway manifest → lane+router+Concierge, grep workflow name → 0 new branches | integration wave | integration+grep | new throwaway-manifest fixture test | ❌ Wave 0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/test_chat_history_compaction.py` — under-budget + recent-verbatim fidelity (clone `test_phase3_compaction.py`)
- [ ] `tests/agents/test_conversation_provider.py` — provider load + dormant (clone `test_uploaded_files_provider.py`)
- [ ] `tests/unit/test_concierge_escalation.py` — router escalation classification (zero-model on routable turns)
- [ ] proposal→channel unit test — Concierge proposals dispose through existing `run_commands` seams
- [ ] SC-001 throwaway-manifest fixture + grep gate (no new workflow-name branch)
- [ ] extend `tests/agents/test_chat_event_neutrality.py` for any new Concierge event type(s)

---

## Manual-Only Verifications

| Behavior | Why Manual | Test Instructions |
|----------|------------|-------------------|
| Live Concierge Q&A against a real Bedrock model | Needs live Bedrock/SSO — LIVE-DEFERRED to Phase 34 | Phase-34 live pass; expect `human_needed` |
| Multi-turn cache-point PLACEMENT confirmation | Requires live token telemetry across turns | Phase-34 live pass; caching already ON (P26), placement confirmed live |
| Live mid-run steering delivery | Needs live in-process `ectx` handle (`_live_ectx_for_run` returns `None` today) | Phase-34 live pass; expect `human_needed` |

---

## Validation Sign-Off

- [ ] All tasks have an offline `<automated>` verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter once the per-task map is filled by plans

**Approval:** pending
