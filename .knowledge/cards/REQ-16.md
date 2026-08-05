---
id: REQ-16
type: req
status: done
area: [workflow, agents, auth]
summary: >-
  Capability Surfacing & User Empowerment (Phase 22)
source: .planning/REQUIREMENTS.md#capability-surfacing-user-empowerment-phase-22
---

### Capability Surfacing & User Empowerment (Phase 22)

- [x] **SURF-01**: One capability palette/inspector reads the live `GET /api/capabilities` registry and renders EVERY capability kind grouped by kind, each showing name / description / `user_allowed` (trust) flag / security-gated flag / config schema — no hardcoded capability-name list in the FE (SC-001); embedded in `AgentsPopup` (Phase 22 / D-01)
- [x] **SURF-02**: `/api/capabilities` extended additively so every registered capability supplies `description` + a security-gated flag + a populated per-capability `config_schema` (the `{}` stub filled); auth + permission scopes preserved (API-02 intact) (Phase 22 / D-08)
- [x] **SURF-03**: For each launchable workflow the composer shows which capabilities each step declares, sourced from the compiled plan (`GET /api/workflows/{id}` / compiled projection), not a hardcoded description (Phase 22)
- [x] **EMP-01**: The live composer lets a user opt step(s) into user-allowed capabilities — at minimum a validator + a human/validation gate + a non-default model + retry — and the selection reaches the run path (saved-workflow payload → compiler/engine) and demonstrably takes effect at execution (Phase 22 / D-05)
- [x] **EMP-02**: Trust/tier gating enforced in UI AND server: `user_allowed=False` capabilities render visible-but-locked, never user-composable; a smuggled privileged grant is server-rejected by compiling with `trust="user"` (`_check_trust` / CAP-03), re-validated at SAVE and at LAUNCH (Phase 22 / D-04/D-12)
- [x] **EMP-03**: Saved workflows persist the richer per-step capability selections additively (reused `manifest_json` column), owner-scoped (IDOR→404), re-validated with `trust="user"` at launch (Phase 22 / D-11)
- [x] **EMP-04**: Selecting a capability that requires a coupled gate auto-attaches the required gate in the composer; the compiler's coupling checks stay the server-side backstop (Phase 22 / D-07)
- [x] **WIRE-01**: The compiler materializes top-level `model:` → `CompiledWorkflow.model` and per-step `model:` → `Step.model` so `ModelResolver` honors a manifest-declared model; INV-3 goldens byte-identical (Phase 22 / D-14)
- [x] **WIRE-02**: The compiler materializes per-step `retry:` → `Step.retry` so a manifest can activate the transient-retry wrapper (RESUME-02 reachable from a manifest) (Phase 22 / D-15)
- [x] **WIRE-03**: Per-step `injects:` is consumed (materialized into `Step.injects` + merged at the factory seam) or fails loud; a parametrized test asserts no `_ALLOWED_STEP_KEYS` entry is accepted-but-dropped (INV-5 preserved) (Phase 22 / D-16/D-17)
- [x] **UXFIX-01**: The catalog shows the friendly authored `display_name` (not the title-cased raw id); the P20 BE coalesce fix stays intact (Phase 22 / D-18)
- [x] **UXFIX-02**: `deliverable_mimetype`/`deliverable_filename` persist on the `WorkflowRun` row (additive columns, owner_id+workspace_id scope) and drive history-reopen so a custom binary deliverable re-renders faithfully (Phase 22 / D-19)
- [x] **UXFIX-03**: The data-driven catalog is the home landing so "no hardcoded name list" holds on the default view; `CreationHub.WORKFLOWS` no longer drives the default landing (Phase 22 / D-20)
- [x] **UXFIX-04**: The generic mimetype-dispatched deliverable renderer is the PRIMARY dispatch path; the 4 first-party types become routed entries rendering identically (no visual regression) (Phase 22 / D-21)
- [x] **DECIDE-01**: (N9) Artifact retention = keep-by-default (run artifacts retained indefinitely); `run_ttl`/`days:N` opt-in overrides; ART-04 updated; the 3 stale open-question labels (REPO-02/REPO-04/FANOUT-05) reconciled — WAVE-03 (N8) left out of scope (Phase 22 / D-22)
- [x] **DECIDE-02**: (N11) Premium-model policy = open to all tiers (no per-tier premium gating); global default stays Haiku with an ordered fallback chain; MODEL-05 updated; the model-picker tier filter removed (Phase 22 / D-23)
- [x] **LIVE-01**: One consolidated live-Bedrock confirmation pass on the AWS `default` profile (acct 473293451041, `claude-haiku-4-5`) records per-item evidence for the 8 standing deferrals (or an explicit disposition); phase completion gates on offline evidence (deferred to milestone-end, Phase 22 / D-24)
