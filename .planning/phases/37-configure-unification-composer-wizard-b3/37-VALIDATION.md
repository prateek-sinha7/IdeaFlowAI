---
phase: 37
slug: configure-unification-composer-wizard-b3
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-09
---

# Phase 37 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **No REQ-IDs map to this phase** (`phase_req_ids: null`) — validation is keyed to the CONTEXT `<decisions>` (D-15/C, SC-001/INV-1, INV-3, INV-5, INV-13, LOCK-E/F) + the four deliverables + the per-file token gate. All checks are OFFLINE + BY DELTA. See `37-RESEARCH.md` §"Validation Architecture" for the per-deliverable command map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest (frontend) · pytest 7.x on **python3.11, no venv** (backend) |
| **Config file** | `frontend/vitest.config.ts` · `backend/pyproject.toml` (import-linter contracts) |
| **Quick run command** | FE: `cd frontend && npx vitest run <touched files>` + `npx tsc --noEmit` · BE: `cd backend && python3.11 -m pytest tests/unit/test_rest_run_launch.py -q` |
| **Full suite command** | **NEVER full pytest — it HANGS offline** (Chromium/Bedrock/Postgres-gated). Targeted: `python3.11 -m pytest tests/agents/test_characterization_*.py tests/unit/test_rest_run_launch.py -q` + `/opt/homebrew/bin/lint-imports` (expect 4/0) |
| **Estimated runtime** | ~35–60 s targeted |

---

## Sampling Rate

- **After every task commit:** FE — `vitest run` on touched specs + `tsc --noEmit` identity (no NEW errors vs baseline) + per-touched-file retired-palette grep `-nE '#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains'` == **0** + positive `@theme`/`ui/` primitive usage.
- **After the D-15/C wave (Wave 1):** run the **5 characterization goldens** (`test_characterization_{prototype,od_prototype,od_ppt,app_builder,prototype_revision}.py`) with **`SNAPSHOT_UPDATE` unset**, then `git status --porcelain backend/tests/agents/characterization/golden/` must be **empty** (byte-identical, INV-3). Then `/opt/homebrew/bin/lint-imports` → **4/0**.
- **Before `/gsd-verify-work`:** targeted suite green + goldens clean + lint-imports 4/0.
- **Max feedback latency:** ~60 s.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Decision/Deliverable | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|----------------------|-----------------|-----------|-------------------|-------------|--------|
| 37-01-* | 01 | 1 | D-15/C generic template/DS (SC-001/INV-1/INV-3) | declared-signal gate; owner-scoped launch unchanged; IDOR→404 preserved | unit + characterization | `python3.11 -m pytest tests/unit/test_rest_run_launch.py tests/agents/test_characterization_*.py -q` + goldens git-clean | ✅ (test_rest_run_launch exists; parity test = W0) | ⬜ pending |
| 37-0N-* | 0N | 2–4 | Configure/Composer/Wizard/Drawer/Dialog/Draft | owner-scoped reads; `user_allowed` gating; no exec/net/secrets | vitest + tsc + token grep | `npx vitest run <spec>` + `tsc --noEmit` + retired-palette grep=0 | ✅ existing infra | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. The planner/nyquist-auditor expands this map to one row per task at execution time.*

---

## Wave 0 Requirements

- [ ] `backend/tests/unit/test_rest_run_launch.py` — **ADD a launch-boundary od_context-parity test** (today only covers `od_context=None`): assert the declared-signal path produces the SAME `od_context` dict for `od_prototype`/`od_ppt` as the current name-branch (the D-15/C additive proof at the boundary). This is the one genuinely-new test the phase must add.
- [ ] No framework install needed — vitest + pytest(3.11) + import-linter already configured.

*Everything else: existing infrastructure covers all phase behaviors.*

---

## Manual-Only Verifications

| Behavior | Decision | Why Manual | Test Instructions |
|----------|----------|------------|-------------------|
| Mocked Playwright e2e (composer/wizard/drawer flows) | LOCK / baseline | Offline webServer timeout — the mocked e2e suite cannot run headless offline here | **LIVE-DEFERRED** — run in the end-of-milestone live pass (baseline); do NOT block phase completion on it |
| Live run-launch with a non-prototype deliverable declaring template/DS | D-15/C | Needs live Bedrock + server | **LIVE-DEFERRED to Phase 34** live confirmation |

*All offline-verifiable behaviors have automated verification above.*

---

## Validation Sign-Off

- [ ] Every task has an `<automated>` offline verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers the one MISSING reference (launch-boundary parity test)
- [ ] No watch-mode flags (`vitest run`, not `vitest`)
- [ ] Feedback latency < 60 s
- [ ] `nyquist_compliant: true` set after the planner wires per-task `<automated>` verifies

**Approval:** pending
