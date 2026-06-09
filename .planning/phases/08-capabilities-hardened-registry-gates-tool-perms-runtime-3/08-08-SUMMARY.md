---
phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
plan: 08
subsystem: api
tags: [fastapi, capabilities-registry, react, nextjs, websocket-events, model-catalog]

# Dependency graph
requires:
  - phase: 08-01
    provides: "@register/discover() registry + user_allowed trust flags (_KNOWN/_TRUST)"
  - phase: 08-02
    provides: "gate kinds (human/validation/approval/security) registered"
  - phase: 08-04
    provides: "Tier validators (spec_plan_coverage/task_done_when/design_quality) registered + severity map"
provides:
  - "GET /api/capabilities — auth-gated registry palette (kind/name/user_allowed/config_schema) incl. runtimes/skills/hooks/model catalog"
  - "Additive validator_result/validation_warning/gate_* WS event contract (no existing event renamed/removed; no snapshot re-baseline)"
  - "Three frontend composer panels: CapabilityPalette, AgentModelPicker, ValidatorIssuePanel (live API/WS data)"
affects: [phase-09, phase-11, phase-12, composer, run-stream]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Authenticated FastAPI GET enumerating the registry live (_KNOWN post-discover) — no hardcoded list"
    - "Additive-only WS event types through the generic websocket.py forward (no per-type edit)"
    - "Additive sibling composer panels reusing existing surfaces (D-11 reuse, not rebuild)"

key-files:
  created:
    - backend/app/api/capabilities.py
    - backend/tests/unit/test_capabilities_api.py
    - frontend/src/components/workflow/CapabilityPalette.tsx
    - frontend/src/components/workflow/AgentModelPicker.tsx
    - frontend/src/components/results/ValidatorIssuePanel.tsx
  modified:
    - backend/app/main.py
    - frontend/src/lib/api.ts
    - frontend/src/types/index.ts
    - frontend/src/components/workflow/WorkflowComposer.tsx

key-decisions:
  - "config_schema is a forward-compat empty {} slot — the capability ports (base.py) are one-method Protocols with no declared per-cap config schema today"
  - "model_catalog kind is surfaced EXPANDED under a separate model_catalog key (per-model records from ModelCatalog), not as one opaque palette row"
  - "ValidatorIssuePanel is props-driven (issues fed in by the parent WS handler) — mirrors AgentProgressPanel, keeps the panel decoupled from WS plumbing"

patterns-established:
  - "Registry-reflective palette endpoint: a new @register appears with zero endpoint edit (test_palette_reflects_registry)"
  - "Additive WS event proof via source inspection: the generic '{type: event[type]}' forward needs no edit for new event types"

requirements-completed: [API-02, API-03, API-06]

# Metrics
duration: ~25min
completed: 2026-06-09
---

# Phase 8 Plan 8: API + Frontend Capability Surface Summary

**GET /api/capabilities auth-gated registry palette (incl. runtimes/skills/hooks/model catalog) + additive validator_result/validation_warning/gate_* WS events + three live composer panels (palette, per-agent model picker, validator/issue panel) — human-verified rendering from live data.**

## Status

**COMPLETE — all 3 tasks done.** Tasks 1 and 2 are committed; the automated backend/frontend gates all pass. Task 3 (`checkpoint:human-verify`, API-06 panel render) was VERIFIED and APPROVED by the human: they ran the dev backend + frontend, opened the workflow composer, and confirmed the capability palette, per-agent model picker, and validator/issue panel all populate from live `/api/capabilities` + WS data, and that the deferred subagent/wave-tree + repo-diff viewers are correctly absent.

## Performance

- **Duration:** ~25 min (Tasks 1-2) + human verification
- **Tasks completed:** 3 of 3 (Task 3 = human-verify checkpoint, APPROVED)
- **Files created:** 5 · **Files modified:** 4

## Accomplishments
- `GET /api/capabilities` (API-02): auth-gated (`Depends(get_current_user)`, 401 without a token) registry palette — every `(kind, name)` with `user_allowed` + a forward-compat `config_schema`, the runtime/skill/hook/gate/validator/tool kinds, plus the expanded model catalog. Enumerated live from `_KNOWN` post-`discover()` — a freshly `@register`'d cap appears with no endpoint edit.
- Additive WS event contract (API-03): `validator_result`/`validation_warning`/`gate_*` flow through the generic `websocket.py` forward with NO `websocket.py` edit; the 5 characterization snapshots stay byte/event-identical (no re-baseline).
- Three composer panels (API-06, partial): `CapabilityPalette` (live `/api/capabilities`, grouped by kind with the `user_allowed` badge), `AgentModelPicker` (per-agent model from the live model catalog → `model_overrides`), `ValidatorIssuePanel` (live `validator_result`/`validation_warning` issues grouped CRITICAL/HIGH/MEDIUM/LOW). All wired additively into `WorkflowComposer`.
- Deferred viewers (subagent/wave-tree + repo-diff) intentionally NOT built (no backing data until P9/11/12).

## Task Commits

1. **Task 1: GET /api/capabilities palette endpoint + additive WS event proof** — `89d11f2` (feat) — TDD RED (module-not-found) → GREEN (8 tests pass)
2. **Task 2: Frontend palette + per-agent model picker + validator/issue panel** — `f0806be` (feat)
3. **Task 3: Human-verify panel render (API-06)** — APPROVED (checkpoint:human-verify) — human ran the dev servers, confirmed the capability palette, per-agent model picker, and validator/issue panel render from live `/api/capabilities` + WS data; deferred subagent/wave + repo-diff viewers correctly absent. No commit (verification task).

## Files Created/Modified
- `backend/app/api/capabilities.py` — auth-gated palette endpoint (registry-reflective + model catalog)
- `backend/app/main.py` — `capabilities_router` registered alongside `workflows_router`
- `backend/tests/unit/test_capabilities_api.py` — auth/shape/registry-reflective/trust/additive-event tests (8, all pass)
- `frontend/src/lib/api.ts` — `getCapabilities` helper + palette/model types
- `frontend/src/types/index.ts` — additive `validator_result`/`validation_warning`/`gate_*` `StreamMessage` types + `ValidationIssue`/`IssueSeverity`
- `frontend/src/components/workflow/CapabilityPalette.tsx` — live palette panel
- `frontend/src/components/workflow/AgentModelPicker.tsx` — per-agent model picker (model catalog)
- `frontend/src/components/results/ValidatorIssuePanel.tsx` — validator/issue panel (WS events)
- `frontend/src/components/workflow/WorkflowComposer.tsx` — wires the three panels additively

## Verification (automated gates — all green)
- `python3.11 -m pytest tests/unit/test_capabilities_api.py -x` → **8 passed**
- `python3.11 -m pytest tests/agents/test_characterization_*.py -x` → **10 passed** (byte/event-identical, no re-baseline)
- `/opt/homebrew/bin/lint-imports` → **3 kept / 0 broken**
- `npm run build` → **passes** (no type/compile errors)
- `websocket.py` unmodified (additive new event types confirmed via `git status`)

## Decisions Made
- `config_schema` is an empty `{}` forward-compat slot — the ports declare no per-capability schema yet (honors plan intent; documented in the endpoint docstring).
- Model catalog surfaced expanded under a `model_catalog` key (per-model records) for the picker, rather than as one opaque palette row.
- `ValidatorIssuePanel` takes issues as a prop (parent WS handler routes the events) — the same props-driven shape `AgentProgressPanel` uses.

## Deviations from Plan
None - plan executed exactly as written. The "config_schema = {}" choice is honoring intent (no per-cap schema exists on the ports), documented inline.

## Known Stubs
- `config_schema` is intentionally `{}` for every capability — the capability ports are one-method Protocols with no declared config schema in Phase 8. This is the documented, stable slot a future per-capability JSON schema lands in without an API-shape change. Not blocking the plan goal (the palette's kind/name/user_allowed + model catalog are the data-bearing fields the panels render).

## Issues Encountered
None.

## Next Phase Readiness
- API-02 + API-03 + API-06 all complete and gated; the human confirmed the live panel render (Task 3 approved). Plan 08-08 closes the user-facing API/frontend surface of the hardened registry/gates/validators.
- Phase 08 plan 8/8 complete. Remaining Phase 08 requirements (GATE-*, TOOLPERM-*, VALID-*, AGENTRT-06, HOOK-*, OBS-2) are tracked across the other plans/phase verification.

## Self-Check: PASSED
- FOUND: backend/app/api/capabilities.py
- FOUND: backend/tests/unit/test_capabilities_api.py
- FOUND: frontend/src/components/workflow/CapabilityPalette.tsx
- FOUND: frontend/src/components/workflow/AgentModelPicker.tsx
- FOUND: frontend/src/components/results/ValidatorIssuePanel.tsx
- FOUND commit: 89d11f2
- FOUND commit: f0806be
- FOUND commit: cbbe5aa
- Gates re-confirmed green at finalize: `pytest test_capabilities_api.py + test_characterization_prototype.py` → 10 passed; `lint-imports` → 3 kept / 0 broken

---
*Phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3*
*Completed: 2026-06-09 (Task 3 human-verified/approved)*
