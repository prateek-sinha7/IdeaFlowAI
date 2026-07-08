---
phase: 32
slug: run-screen-redesign-a4
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-08
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **OFFLINE + DELTA-based** (autonomous run). Verify BY DELTA against the pre-existing
> **128-red mocked-Playwright baseline** (DEF-29-06-1) — absolute-green is NOT the target.
> **NEVER run the full backend pytest — it HANGS offline.** Any live-server check →
> mark live-deferred to the Phase-34 live pass; do not hang, do not fabricate.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **FE unit** | vitest `^4.1.5` — `cd frontend && npm test` (= `vitest --run`) |
| **FE e2e** | Playwright `^1.56.0` mocked — `cd frontend && npm run e2e` (`playwright test --project=mocked`) — **verify BY DELTA vs 128-red baseline** |
| **FE types** | `cd frontend && npx tsc --noEmit` (identity — no new errors) |
| **Backend (targeted)** | `python3.11 -m pytest backend/tests/agents/test_characterization_*.py` (5 goldens) + new endpoint tests |
| **Import boundary** | `/opt/homebrew/bin/lint-imports` (must stay 4/0) |
| **Config file** | `frontend/vitest.config.ts`, `frontend/playwright.config.ts`, `backend/pyproject.toml` |
| **Estimated runtime** | vitest ~30–60s · targeted pytest+lint ~35s · mocked Playwright delta ~variable |

**The 5 characterization goldens (byte/event-identical — INV-3):**
`backend/tests/agents/test_characterization_{prototype,prototype_revision,od_ppt,od_prototype,app_builder}.py`

---

## Sampling Rate

- **After every task commit:** FE tasks → `npm test` (vitest) + `npx tsc --noEmit`; backend tasks → `python3.11 -m pytest <targeted>` + `lint-imports`.
- **After every plan wave:** full vitest + mocked-Playwright DELTA + the 5 goldens byte-identical.
- **Before `/gsd-verify-work`:** 5 goldens byte-identical + `lint-imports` 4/0 + e2e delta non-regressing (no NEW reds vs the 128 baseline; targeted specs move toward green).
- **Max feedback latency:** ~60s (vitest) / ~35s (targeted backend).

---

## SC → Signal → Test Map

| SC | Observable signal | Offline test |
|----|-------------------|--------------|
| **SC-1 tokens** | Run components resolve `#3C2CDA`/Manrope/Heebo from the `src/styles/globals.css` `@theme`; no NEW hardcoded palette in the run subtree | vitest render assertions + a grep-guard test ("no new `#1B2A4A`/`#2563eb` raw hex in run subtree") + `tsc --noEmit` identity |
| **SC-2 Steps drill-down** | L1/L2/L3 render from real events (dual-source `task_progress` + `subagent_*`/`wave_*`); KAN-99 caps checklist at N-1 until `agent_complete`; gate/clarify render inline | vitest unit on Steps components with scripted event fixtures (incl. the N-1 cap assertion); mocked-Playwright DELTA on the Steps tab |
| **SC-2 SC-001 flag** | `review_gate_ready` carries a GENERIC name-free eligibility flag; FE affordance driven off the flag, no `prototype-analyze`/`prototype-specify` literal in the render/affordance path | **5 characterization goldens byte-identical** (new key in `_VOLATILE_STRIP_KEYS`) + banned-pattern/grep gate on the literal + vitest on `InlineGateActions` eligibility |
| **SC-3 Audit** | 3 endpoints return owner-scoped rows; cross-owner/missing → **404**; client counters/coverage chips/filters + CSV/JSON export render | backend targeted pytest on the new endpoints (owner-scope + IDOR→404, clone `get_hook_runs` test) + `lint-imports` 4/0 + vitest on `AuditTab` + export util |
| **SC-4 cancelled/failed** | `pipeline_cancelled` → cancelled marker on `pipelineState` → "Cancelled by you" ack + relaunch (LIVE-STATE-CONTRACT §1); failed/degraded → P16 affordances + "What went wrong" card | vitest on the `useWorkflow` `pipeline_cancelled` reducer (asserts the new cancelled marker; FIX-039 ordering intact) + RunChatLane terminal render; mocked-Playwright DELTA |
| **SC-4 e2e** | brittle color/class assertions replaced by token/`data-testid`; targeted specs non-regressing | mocked-Playwright DELTA on `ts-m`/`ts-c`/`ts-i`/`ts-f`/`ts-n` specs |

---

## Wave 0 Requirements (test scaffolding to add)

- [ ] New Audit endpoint tests (owner-scope + IDOR→404) — clone the `get_hook_runs` test pattern (`backend/tests/...`).
- [ ] Steps drill-down component tests — scripted `task_progress` / `wave_*` / `subagent_*` fixtures; **KAN-99 N-1 cap** assertion.
- [ ] `useWorkflow` `pipeline_cancelled` reducer test — asserts the new cancelled marker (ISS-035 regression guard) AND that the FIX-039 `agent_start` accumulator-reset ordering is unchanged.
- [ ] SC-001 backend-flag goldens guard — extend `_VOLATILE_STRIP_KEYS`, re-assert 5 goldens byte-identical.
- [ ] Token-guard grep test — no NEW raw `#1B2A4A`/`#2563eb`/off-palette hex introduced in the run subtree.
- [ ] Frameworks already installed (vitest + Playwright + pytest all present) — no install task needed.

---

## Manual-Only Verifications (live-deferred to Phase-34 live pass)

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live multi-turn chat / images / steering; live cancelled/failed/degraded visuals | SC-4 | needs a live server + Bedrock; full pytest hangs offline | Deferred to Phase-34 live pass (per CONTEXT execution-viability note) |
| Multimodal/visual pixel confirmation of the reskin | SC-1 | visual fidelity needs a running app | Deferred to Phase-34 live pass |

*All STRUCTURAL behavior has offline automated verification (vitest + mocked-Playwright delta + tsc identity + targeted backend + lint-imports). Only live/visual confirmation defers.*

---

## Security Domain (ASVS L1)

This phase adds only READ endpoints + a FE reskin + one additive golden-neutral payload flag.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `Depends(get_current_user)` on all 3 endpoints (existing dep) |
| V4 Access Control | **yes (primary)** | Two-layer owner gate `WorkflowRun.user_id == current_user.id` → **404 (never 403)** on cross-owner/missing (P13/P25); child rows scoped by `run_id` (+ `owner_id`/`workspace_id` defense-in-depth). NOT the nullable `owner_id` as the gate. |
| V5 Input Validation | yes | path param is a run id; no request body on GETs; export is client-side (no injection surface) |
| V7 Error Handling / Logging | yes | `exec_runs.output_digest` is TRUNCATED — surface digest only, never raw child output/secrets |

**Threat model seed (each PLAN.md `<threat_model>` block, block-on: high):** IDOR on `{run_id}` (→ two-layer `user_id` filter → 404); cross-owner row leak (→ owner/workspace scoping on the audit tables); secret leak via exec output (→ truncated `output_digest`); SQLi (→ SQLAlchemy ORM parameterized).

---

## Validation Sign-Off

- [ ] All tasks have an offline `<automated>` verify (or a Wave-0 scaffolding dependency)
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify
- [ ] Wave 0 covers all MISSING test references
- [ ] No watch-mode flags (all runs are `--run`/one-shot)
- [ ] Feedback latency < 60s
- [ ] 5 goldens byte-identical proven for the SC-001 flag change
- [ ] `nyquist_compliant: true` set once the plans' per-task map is complete

**Approval:** pending
