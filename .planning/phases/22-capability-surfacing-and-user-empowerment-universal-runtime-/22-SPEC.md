# Phase 22: Capability Surfacing and User Empowerment — Universal Runtime UX Completeness — Specification

**Created:** 2026-06-14
**Ambiguity score:** 0.135 (gate: ≤ 0.20)
**Requirements:** 17 locked

## Goal

Cash the SC-001 dividend at the UX layer: every registered capability becomes **visible** in the UI (sourced from the live `GET /api/capabilities` registry, grouped by kind, trust/tier-gated) and **composable** — a user can opt a workflow's steps into user-allowed capabilities, save it, and launch it through the **existing** run path with **zero kernel workflow-name branches** — while closing the v1.0 audit's latent wiring gaps (accepted-but-dropped `model:`/`retry:`/`injects:` keys), the four UX data-faithfulness fixes, the two open product decisions (N9 retention, N11 premium-model policy), and one consolidated live-Bedrock confirmation pass.

## Background

This is the final phase of milestone v1.0 (21/22 phases passed; status `tech_debt`). The kernel + registry already expose ~20 capability kinds via `registry._KNOWN` (`backend/agents/capabilities/registry.py:79-143`), but the product surface uses ~a dozen. The capstone work, grounded in the 2026-06-14 codebase scout:

- **Surfacing gap:** `GET /api/capabilities` (`backend/app/api/capabilities.py:90-136`) returns only `{kind, name, user_allowed, config_schema={}}` per capability — **no `description`, no security-gated flag, and `config_schema` is a hardcoded `{}` stub** (`capabilities.py:117`). The FE fetches the `capabilities[]` array (`frontend/src/lib/api.ts:522-529`) but **renders none of it**; only `model_catalog` is consumed (by `AgentModelPicker.tsx:72-78`). Agents/skills/hooks in the composer are FE-hardcoded (`AgentLibraryData.ts`, `data/skills.ts`, `data/hooks.ts`).
- **Dormant untrusted compose path:** the compiler fully supports `trust="user"/"db"` with per-capability `is_user_allowed` checks and a Limits-only-lower ceiling (`backend/agents/workflows/compiler.py:140/279-321`), but **nothing invokes it** — saved workflows persist only `{base_pipeline_type, agent_ids, model_overrides}` (`backend/app/api/user_workflows.py:57-67`) and launch the static file manifest; the typed `Step`/`CompiledWorkflow` already declare the full per-step capability surface (`backend/agents/workflows/plan.py:341-411`).
- **Accepted-but-dropped keys:** `_ALLOWED_STEP_KEYS` permits `model`/`retry`/`injects` (`compiler.py:65-86`); `Step.model`/`Step.retry`/`Step.injects`/`CompiledWorkflow.model` fields exist (`plan.py:362/368/369/408`); `ModelResolver` already reads tiers 2 & 4 (`backend/agents/model_policy.py:96/101`); the RESUME-02 retry wrapper is live and gated on `step.retry` (`engine.py:1840-1842/4512-4513`) — but the two compiler constructors (`compiler.py:231-244`, `:505-517`) never pass these through, so all four are inert from a manifest. `injects:` today flows only via AGENT.md frontmatter (`loader.py:102` → `factory.py:311-315`).
- **UX gaps:** `deliverable_mimetype`/`deliverable_filename` are emitted live (`engine.py:2117-2128`) but **not persisted** on `WorkflowRun` (`backend/app/models/workflow.py:13-62`), so history-reopen re-sniffs from text (`frontend/src/types/index.ts:342-356`) and a binary deliverable can't recover its true mimetype. Home = hardcoded `CreationHub.WORKFLOWS` (`DashboardLayout.tsx:256/1070-1079`) vs catalog = data-driven `WorkflowCatalog` (`:1084-1093`) is a confirmed dual surface. The generic mimetype renderer is fallback-only behind 4 first-party branches (`PreviewPanel.tsx:557-569`).
- **Open decisions + live debt:** N9 (retention) and N11 (premium-model policy) were carried as "confirm" on ART-04/MODEL-05; a batch of live-Bedrock re-confirmations stood deferred behind ISS-018 (the `hexaware-srini` entitlement loss) — but the AWS `default` profile (acct 473293451041) retains full entitlement.

## Requirements

### Capability surfacing (visual)

1. **SURF-01 — Capability palette reads the live registry**: One palette/inspector renders EVERY capability kind, grouped by kind, with no hardcoded capability name list in the FE.
   - Current: FE fetches `capabilities[]` (`api.ts:522-529`) but renders none of it; only `model_catalog` is consumed (`AgentModelPicker.tsx:76`). No component lists strategies/deliverables/validators/gates/context_providers/compaction/task_parsers/merge/isolation(runtime_env)/hooks/skills/tools/mcp_servers/integration_providers/runtimes/model_catalog/limits.
   - Target: a palette component fetches `GET /api/capabilities` at runtime and renders every kind grouped by kind, each row showing name, description, `user_allowed`/trust flag, security-gated flag, and config schema — driven entirely by the fetched payload.
   - Acceptance: a grep for hardcoded capability-name arrays in the new palette source returns 0; rendering the palette against a registry payload with all kinds shows ≥1 row per kind; adding a capability to the registry (test fixture) makes it appear with no FE source edit (SC-001).

2. **SURF-02 — `/api/capabilities` supplies display metadata additively**: every registered capability returns the metadata the palette needs.
   - Current: `CapabilityEntry` = `{kind, name, user_allowed, config_schema={}}` (`capabilities.py:56-64`); `config_schema` is the literal `{}` stub (`:117`); no `description`, no security-gated flag.
   - Target: `/api/capabilities` is extended additively so each capability supplies `description`, a security-gated flag, and a populated per-capability `config_schema` (filled per capability, no longer a blanket `{}`); the API-02 contract, auth dependency (`Depends(get_current_user)`), and permission scopes are preserved.
   - Acceptance: `test_capabilities_api.py` asserts each entry now carries `description` + security-gated flag + non-trivial `config_schema` for capabilities that take config; the auth gate and existing response keys remain (additive, no breaking change); the FE palette renders these fields.

3. **SURF-03 — Composer shows a workflow's declared capabilities**: for each launchable workflow the user can SEE what it currently uses before composing.
   - Current: no surface shows a workflow's compiled capability set; the composer shows only agents + per-agent model + human gate.
   - Target: the composer reads the compiled plan (via `GET /api/workflows/{id}` or an equivalent compiled-capability projection) and displays which capabilities each step declares (strategy, gates, validators, context providers, deliverable type, etc.).
   - Acceptance: opening a built-in launchable workflow in the composer shows its per-step declared capabilities sourced from the compiled plan, not a hardcoded description.

### User empowerment (compose + use)

4. **EMP-01 — Compose into user-allowed capabilities, reaching the run path**: the live composer lets a user opt step(s) into user-allowed capabilities and the selection demonstrably takes effect at execution.
   - Current: the composer exposes exactly three levers — agent membership/order, per-agent model override, per-agent human gate (`IdeaInputPage.tsx` + `AgentsPopup.tsx`); validators/gates-beyond-human/context-providers/deliverable-type/compaction/fan-out/retry/limits have NO FE surface; saved workflows carry only the triple and launch the static file manifest.
   - Target: the composer lets a user attach, per step, at least the representative lever-set — a **validator**, a **human/validation gate**, a **non-default model**, and **retry** (plus deliverable type / context provider / compaction / fan-out / limits where user-allowed); the selection is persisted on the saved workflow and reaches the compiler/engine at launch through the existing run path (no new run endpoint, no kernel branch).
   - Acceptance: composing a workflow with a validator + a human gate + a non-default model + retry, saving it, and launching it produces observable execution effects — the chosen validator fires (a `validation_*` event / audit row), the chosen model is the one resolved (`ModelResolver` precedence), and retry activates under an injected transient fault — proven by a test driving save→launch.

5. **EMP-02 — Trust/tier gating enforced in UI AND server**: `user_allowed=False` capabilities are visible-but-locked and server-rejected if smuggled.
   - Current: `is_user_allowed` exists in the registry (`registry.py:336-346`) and the compiler's trust check exists (`compiler.py:312-321`) but is never invoked with `trust="user"`; the FE has no lock affordance.
   - Target: `user_allowed=False` capabilities (exec, `spawn_subagents`, `security`/`approval` gates, `user_allowed=False` MCP servers like filesystem/postgres) render visible-but-locked (engineer-only / upgrade affordance) and are never user-composable; the save and launch payloads are validated server-side with `trust="user"` so a smuggled privileged grant is rejected (CAP-03), re-validated at SAVE and at LAUNCH.
   - Acceptance: the palette renders a locked state for each `user_allowed=False` capability; a save/launch payload that injects a `user_allowed=False` capability is rejected by the server (test asserts the `_check_trust`/`is_user_allowed` rejection at both the save endpoint and the launch handler).

6. **EMP-03 — Saved workflows persist richer per-step selections, owner-scoped**: the new selections survive save/reload and are re-validated at launch.
   - Current: the saved row stores `{agents, base_pipeline_type, model_overrides, description}` on the reused `workflows` table (`workflow_definition.py`); `manifest_json` column exists but user rows never populate it; per-step capability selections are not persisted.
   - Target: the richer per-step capability selections persist additively (the existing `manifest_json` column or an additive JSON column on the `workflows` table), owner-scoped (`owner_id`+`workspace_id` on the row), IDOR→404, re-validated with `trust="user"` at launch.
   - Acceptance: a saved workflow with per-step capability selections round-trips (save → list → reopen shows the same selections); a cross-owner GET returns 404; launch re-validates the persisted selections; the migration is additive (no table drop/alter-narrowing).

7. **EMP-04 — Gate auto-attachment for capabilities that require one**: selecting a capability that requires a gate auto-attaches the required gate.
   - Current: the compiler enforces the exec⇒`gates:[security,approval]` coupling (D-01) at compile time, but the composer has no way to express it and cannot smuggle exec anyway (EMP-02).
   - Target: when a user selects a (user-allowed) capability that requires a gate (validation/approval), the composer auto-attaches the required gate so the compiled manifest satisfies the §13 coupling policies; the compiler's coupling checks stay enforced as the server-side backstop.
   - Acceptance: selecting a capability that requires a gate yields a saved manifest whose step carries the required gate; a manifest missing the coupled gate is rejected by the compiler (test asserts both the auto-attach and the compiler backstop).

### Latent manifest-key wiring (accepted-but-dropped)

8. **WIRE-01 — Compiler materializes `model:` (top-level + per-step)**: manifest-declared model selection is honored.
   - Current: `_ALLOWED_STEP_KEYS` permits `model` (`compiler.py:65-86`); `Step.model`/`CompiledWorkflow.model` fields exist (`plan.py:362/408`); `ModelResolver` reads tiers 2 & 4 (`model_policy.py:96/101`) — but `compiler.py:231-244` and `:505-517` never pass `model=`, so it is silently dropped.
   - Target: the compiler materializes top-level `model:` into `CompiledWorkflow.model` and per-step `model:` into `Step.model`, so `ModelResolver`'s workflow/step tiers honor a manifest-declared model.
   - Acceptance: a manifest declaring a per-step and a top-level `model:` changes the resolved model for that step/workflow (test asserts the resolved model id); the 5 characterization goldens stay byte-identical (INV-3).

9. **WIRE-02 — Compiler materializes per-step `retry:`**: a manifest can enable the transient-retry wrapper.
   - Current: `retry` is allow-listed (`compiler.py:65-86`); `Step.retry` field exists (`plan.py:368`); the RESUME-02 wrapper is live and gated on `step.retry.max_attempts>0` (`engine.py:4512-4513`) — but the compiler drops `retry:` and no manifest declares it, so the wrapper is reachable programmatically only.
   - Target: the compiler materializes per-step `retry:` into `Step.retry` so a manifest can activate the transient-retry wrapper (RESUME-02 reachable from a manifest).
   - Acceptance: a manifest declaring `retry: {max_attempts: N}` activates the retry wrapper under an injected transient throttle (test asserts retry fires); a manifest without `retry:` stays byte/event-identical (wrapper dormant).

10. **WIRE-03 — Per-step `injects:` consumed or fails loud; no silent no-op**: no allow-listed step key silently drops.
    - Current: `injects` is allow-listed (`compiler.py:65-86`) and `Step.injects` exists (`plan.py:369`), but the compiler drops per-step `injects:`; the live injects surface is AGENT.md-only (`loader.py:102`→`factory.py:311-315`).
    - Target: the compiler either materializes per-step `injects:` into `Step.injects` (and the engine consumes it) OR removes the key from the allow-list and rejects it loudly; a test asserts **every** `_ALLOWED_STEP_KEYS` entry is either consumed (materialized into the `Step`/`CompiledWorkflow`) or rejected — none accepted-but-dropped.
    - Acceptance: a parametrized test enumerates `_ALLOWED_STEP_KEYS` and asserts each key is either reflected on the compiled `Step`/`CompiledWorkflow` or raises `CompilerError`; no key is silently ignored.

### UX / data-faithfulness fixes

11. **UXFIX-01 — Catalog shows friendly `display_name`**: not the title-cased raw id.
    - Current: catalog rows derive a label from the raw id / `WORKFLOW_LABELS` fallback (P20 WR-01).
    - Target: launchable manifests carry an authored `display_name:` (or leave the BE fallback null deliberately) so the catalog shows the friendly name.
    - Acceptance: each launchable workflow renders its authored `display_name` in the catalog; the BE fallback is null only where intentionally unauthored (test/assertion on the rendered label source).

12. **UXFIX-02 — `deliverable_mimetype`/`deliverable_filename` persist on the run row**: history-reopen re-renders a binary deliverable faithfully.
    - Current: both emitted live (`engine.py:2117-2128`) but absent from `WorkflowRun` (`workflow.py:13-62`); history-reopen re-sniffs from text (`index.ts:342-356`), so a binary deliverable can't recover its true mimetype.
    - Target: persist `deliverable_mimetype`/`deliverable_filename` as additive columns on the run row (carrying owner_id+workspace_id via the existing run scope) and drive history-reopen from the persisted values.
    - Acceptance: a custom binary deliverable (e.g. `application/zip`) re-renders correctly on history-reopen using the persisted mimetype (not the text heuristic); the migration is additive.

13. **UXFIX-03 — Data-driven catalog is the home landing**: resolves the home-vs-CreationHub dual surface.
    - Current: default `home` view mounts hardcoded `CreationHub.WORKFLOWS` (`DashboardLayout.tsx:256/1070-1079`); the data-driven `WorkflowCatalog` is a separate `catalog` tab (`:1084-1093`).
    - Target: the data-driven catalog is the default landing surface so "no hardcoded name list" holds on the default view (P20 SC-1).
    - Acceptance: the default landing renders the data-driven `WorkflowCatalog` (sourced from `GET /api/workflows`); the hardcoded `CreationHub.WORKFLOWS` array no longer drives the default landing (removed or no longer mounted as home).

14. **UXFIX-04 — Generic mimetype renderer is the PRIMARY dispatch path**: the SC-001 dividend isn't fallback-only.
    - Current: `PreviewPanel.tsx:557-569` reaches the generic mimetype dispatch only after 4 first-party per-type branches (`user_stories`/`app_builder`/`ppt`/`prototype`).
    - Target: the generic mimetype-dispatched renderer is the primary dispatch path — first-party branches collapse into it or are proven equivalent to the generic path for their mimetype.
    - Acceptance: a custom/unknown deliverable renders via the generic path as the primary route (not fallback-only); the existing first-party types render identically (no visual regression in the per-type tests).

### Open decisions + live confirmation

15. **DECIDE-01 (N9) — Artifact retention = keep-by-default**: resolves N9 and reconciles stale labels.
    - Current: ART-04 reads "Default retention `run_ttl` (=48h)… (N9 — confirm)"; REPO-02 (N6/N10), REPO-04 (N5/N7), FANOUT-05 (N2) carry stale "confirm" labels.
    - Target (DECIDED): default retention is **keep** (run artifacts retained indefinitely); `run_ttl`/`days:N` are opt-in overrides. ART-04 is updated to keep-by-default; the three stale "confirm" labels are reconciled.
    - Acceptance: REQUIREMENTS.md ART-04 records keep-by-default with opt-in TTL overrides; REPO-02/REPO-04/FANOUT-05 "confirm" labels are reconciled (no dangling "confirm"); any retention default in code/config reflects keep.

16. **DECIDE-02 (N11) — Premium-model policy = open to all tiers**: resolves N11 and reflects it in the picker.
    - Current: MODEL-05 reads "Global default stays Haiku; per-step/workflow model honored (N11 — confirm premium policy + fallback chain)"; `AgentModelPicker` filters to `user_allowed` (`AgentModelPicker.tsx:76`).
    - Target (DECIDED): global default stays Haiku with an ordered fallback chain on throttle/error; premium (`cost_class=premium`) models are selectable by **all** tiers (no per-tier premium gating); the model picker offers the full `user_allowed` catalog to every tier.
    - Acceptance: REQUIREMENTS.md MODEL-05 records premium-open-to-all-tiers + the default fallback chain; the model picker offers premium models to a non-premium tier user (no tier-based filtering); the Haiku default + fallback chain is documented.

17. **LIVE-01 — Consolidated live-Bedrock confirmation on the `default` profile (Haiku 4.5)**: records evidence for the standing deferrals.
    - Current: a batch of live items stood deferred behind ISS-018 (`hexaware-srini` lost entitlement); offline structural fixes landed (COMPACT-03, P6 CR-02, P8 OTLP, P13 F1/F4/F5, P14 SC4, P16 SC1/SC2, P19 ISS-004).
    - Target: one consolidated live pass on the AWS `default` profile (acct 473293451041, full entitlement) using model `claude-haiku-4-5` (Haiku 4.5) records evidence per standing deferral; ISS-018 does not block on the `default` profile.
    - Acceptance: a LIVE-01 evidence record lists, per deferred item (COMPACT-03 · P6 CR-02 · P8 OTLP · P13 F1/F4/F5 · P14 SC4 · P16 SC1/SC2 · P19 ISS-004), either CONFIRMED-live (default profile, Haiku 4.5) or an explicit disposition; phase completion gates on offline evidence (per the defer-live-verification convention), with this live pass as the milestone-end confirmation.

## Boundaries

**In scope:**
- A live-registry-driven capability palette/inspector rendering every capability kind, grouped, trust-gated (SURF-01).
- Additive `/api/capabilities` metadata: `description`, security-gated flag, populated `config_schema` (SURF-02).
- Composer surface showing a workflow's declared capabilities (SURF-03).
- Composer levers to opt steps into user-allowed capabilities — at minimum a validator + a human/validation gate + a non-default model + retry — reaching the run path through the existing launch flow (EMP-01).
- UI + server trust/tier gating: visible-but-locked privileged capabilities, server-rejection of smuggled grants at SAVE and LAUNCH (EMP-02).
- Additive persistence of richer per-step selections on the reused `workflows` table, owner-scoped, re-validated at launch (EMP-03).
- Gate auto-attachment for capabilities that require a coupled gate (EMP-04).
- Compiler materialization of `model:` (top-level + per-step), per-step `retry:`, and per-step `injects:` — plus a test proving no `_ALLOWED_STEP_KEYS` entry is accepted-but-dropped (WIRE-01/02/03).
- Friendly `display_name` in the catalog (UXFIX-01); persisted `deliverable_mimetype`/`deliverable_filename` driving history-reopen (UXFIX-02); data-driven catalog as the home landing (UXFIX-03); generic mimetype renderer as the primary dispatch path (UXFIX-04).
- Recording the two product decisions in REQUIREMENTS.md: keep-by-default retention (DECIDE-01) and premium-open-to-all-tiers (DECIDE-02), reflected in the model picker.
- One consolidated live-Bedrock pass on the `default` profile with Haiku 4.5, with a per-item evidence record (LIVE-01).

**Out of scope:**
- **Exhaustive per-capability E2E proof** — compose+launch is proven with ≥1 representative capability per lever-type, not every individual user-allowed capability wired+proven (per the locked acceptance bar; full per-capability coverage is a follow-up).
- **ECS/container RuntimeEnvironment backend** — the Workspace/RuntimeEnvironment abstraction stays local-only; the container backend swap is a later milestone (designed, not built here).
- **Enabling code-exec / `spawn_subagents` / `security` gate by default** — these stay `user_allowed=False` (engineer-only); the `security` gate stays behind its gate until N3. This phase makes them *visible-but-locked*, not user-composable.
- **New capability kinds or new registry entries** — this phase surfaces and wires the *existing* registry; it adds no new strategies/validators/etc. (SURF-02 fills metadata for what exists).
- **Resolving CTX-04** (`run_revision` retirement) — remains an intentional VOID pending a separate product decision.
- **Nyquist VALIDATION.md backfill** — the weak Nyquist coverage (20 partial/missing phases) is reviewable debt, addressed by `/gsd-validate-phase`, not this phase.
- **Non-`default` AWS profile / ISS-018 resolution** — the live pass runs on the `default` profile; resolving the `hexaware-srini` entitlement is an external IT escalation, not repo work.

## Constraints

Invariants bind every plan (from the ROADMAP "Invariants" block):
- **SC-001**: the user composer routes through the capability registry + `trust=user/db`, never a workflow-name branch; this phase activates the built-but-dormant untrusted-manifest path. Kernel name-free grep must stay 0.
- **INV-3**: the 5 characterization goldens stay byte-identical (deliverable bytes + normalized event stream); `deliverable_mimetype`/`deliverable_filename` remain in `_VOLATILE_STRIP_KEYS` so additive emission/persistence keeps goldens identical.
- **INV-13**: `create_deep_agent` only inside the `langchain_deepagents` adapter (sole call site `app/agents/deep_agent_runner.py:291`).
- **Ports & Adapters**: import-linter stays 4 kept / 0 broken; adding a capability = add a module + register, no kernel edit.
- **INV-5**: no DSL; the compiler's strict step-key rejection is preserved (WIRE-03 must not loosen `_ALLOWED_STEP_KEYS` into a silent-accept).
- **Additive migrations only**: every new table carries `owner_id`+`workspace_id`; new columns (UXFIX-02 run-row mimetype, EMP-03 per-step selections) are additive on existing owner-scoped tables — no destructive alter.
- **API-02 contract intact**: `/api/capabilities` extensions are additive, preserving auth (`Depends(get_current_user)`) + permission scopes.
- **Live model**: the LIVE-01 pass uses the AWS `default` profile (acct 473293451041) with `claude-haiku-4-5` (Haiku 4.5).

## Acceptance Criteria

- [ ] Every registered capability kind is visible in the UI palette, sourced from a live `GET /api/capabilities` fetch, grouped by kind, each showing name / description / `user_allowed` / security-gated flag / config schema — and the FE carries no hardcoded capability name list (SC-001 grep = 0 in the palette source).
- [ ] A user can compose a workflow from the UI that opts into ≥1 previously-unsurfaced user-allowed capability per lever-type (a validator + a human gate + a non-default model + retry), SAVE it, and LAUNCH it through the existing run path — and the selection demonstrably reaches execution (the validator fires / the chosen model is resolved / retry activates under fault injection).
- [ ] Privileged capabilities (exec, `spawn_subagents`, `security`/`approval` gates, `user_allowed=False` MCP/integration servers) render visible-but-locked for an unentitled user and are server-rejected if smuggled into a save/launch payload (CAP-03), re-validated at SAVE and at LAUNCH.
- [ ] Compiler materializes top-level + per-step `model:` and per-step `retry:` so they take effect (a manifest-declared model changes the resolved model; a manifest-declared retry activates the wrapper under throttle); `injects:` is consumed or fails loud — a parametrized test proves no `_ALLOWED_STEP_KEYS` entry is accepted-but-dropped.
- [ ] The data-driven catalog is the home landing showing friendly `display_name`s; a custom binary deliverable re-renders faithfully on history-reopen from the persisted mimetype; the generic mimetype renderer is the primary deliverable dispatch path.
- [ ] REQUIREMENTS.md records the two decisions: ART-04 = keep-by-default (TTL opt-in) with the 3 stale "confirm" labels reconciled; MODEL-05 = premium-open-to-all-tiers + Haiku default/fallback chain; the model picker offers premium models to a non-premium tier.
- [ ] A LIVE-01 evidence record lists, per standing deferral (COMPACT-03 · P6 CR-02 · P8 OTLP · P13 F1/F4/F5 · P14 SC4 · P16 SC1/SC2 · P19 ISS-004), either CONFIRMED-live (default profile, Haiku 4.5) or an explicit disposition.
- [ ] Invariants hold: 5 characterization goldens byte-identical (INV-3) · kernel name-free (SC-001 grep 0) · `create_deep_agent` only in the adapter (INV-13) · import-linter 4/0 · additive migrations only (owner_id+workspace_id on every new table/column scope).

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                                 |
|--------------------|-------|------|--------|-----------------------------------------------------------------------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | Outcome specific + measurable; 8 falsifiable SCs from the ROADMAP      |
| Boundary Clarity   | 0.82  | 0.70 | ✓      | Acceptance bar locked (representative per lever); out-of-scope explicit |
| Constraint Clarity | 0.88  | 0.65 | ✓      | Invariants locked + N9/N11 policy decided; additive-migration mandate  |
| Acceptance Criteria| 0.88  | 0.70 | ✓      | 8 pass/fail criteria, each tied to a requirement                       |
| **Ambiguity**      | 0.135 | ≤0.20| ✓      | Gate passed in 1 round                                                 |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption). No dimensions below minimum.

## Interview Log

| Round | Perspective              | Question summary                                  | Decision locked                                                                 |
|-------|--------------------------|---------------------------------------------------|----------------------------------------------------------------------------------|
| 0     | Researcher (codebase scout) | What exists today vs the 17-item target?        | Registry live but under-surfaced; untrusted compile path dormant; 3 keys accepted-but-dropped; 4 UX gaps confirmed (file:line evidence) |
| 1     | Boundary Keeper          | DECIDE-01 (N9) artifact retention default?         | **Keep-by-default** — retain indefinitely; `run_ttl`/`days:N` opt-in overrides   |
| 1     | Boundary Keeper          | DECIDE-02 (N11) premium-model policy?              | **Premium open to all tiers** — no per-tier gating; Haiku default + fallback chain |
| 1     | Simplifier               | Compose+launch acceptance bar — representative or exhaustive? | **Representative per lever** — surface all kinds; prove compose+launch with ≥1 capability per lever-type (validator + gate + model + retry) |
| 1     | Failure Analyst          | LIVE-01 a hard blocking gate (ISS-018)?            | **Run live on the `default` profile with Haiku 4.5** (full entitlement); record-and-defer disposition per item; completion gates on offline evidence |

---

*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime-*
*Spec created: 2026-06-14*
*Next step: /gsd-discuss-phase 22 — implementation decisions (how to build the palette, where per-step composer levers plug in, the compiler materialization order, migration shape)*
