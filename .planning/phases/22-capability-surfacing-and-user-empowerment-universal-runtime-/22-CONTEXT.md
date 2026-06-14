# Phase 22: Capability Surfacing and User Empowerment — Universal Runtime UX Completeness - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Source:** `22-SPEC.md` (17 requirements locked) + this discussion (implementation HOW)

<domain>
## Phase Boundary

The final phase of milestone v1.0 — **cash the SC-001 dividend at the UX layer**. Make every registered capability **visible** (sourced from the live `GET /api/capabilities` registry, grouped by kind, trust/tier-gated) and **composable** (a user opts a workflow's steps into user-allowed capabilities, saves it, and launches it through the **existing** run path with **zero kernel workflow-name branches**) — while closing the v1.0 audit's latent wiring gaps (accepted-but-dropped `model:`/`retry:`/`injects:` keys), the four UX data-faithfulness fixes, the two open product decisions (N9 retention, N11 premium-model policy), and one consolidated live-Bedrock confirmation pass.

This phase **surfaces and wires the existing registry** — it adds NO new strategies/validators/capability kinds. It activates the **built-but-dormant untrusted-manifest compile path** (`trust="user"`), which the kernel already supports but nothing currently invokes.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**17 requirements are locked.** See `22-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `22-SPEC.md` before planning or implementing. Requirements are not duplicated here. The requirement IDs (for cross-reference): SURF-01/02/03 · EMP-01/02/03/04 · WIRE-01/02/03 · UXFIX-01/02/03/04 · DECIDE-01/02 · LIVE-01.

**In scope (from SPEC.md):**
- A live-registry-driven capability palette/inspector rendering every capability kind, grouped, trust-gated (SURF-01).
- Additive `/api/capabilities` metadata: `description`, security-gated flag, populated `config_schema` (SURF-02).
- Composer surface showing a workflow's declared capabilities (SURF-03).
- Composer levers to opt steps into user-allowed capabilities — at minimum a validator + a human/validation gate + a non-default model + retry — reaching the run path through the existing launch flow (EMP-01).
- UI + server trust/tier gating: visible-but-locked privileged capabilities, server-rejection of smuggled grants at SAVE and LAUNCH (EMP-02).
- Additive persistence of richer per-step selections on the reused `workflows` table, owner-scoped, re-validated at launch (EMP-03).
- Gate auto-attachment for capabilities that require a coupled gate (EMP-04).
- Compiler materialization of `model:` (top-level + per-step), per-step `retry:`, and per-step `injects:` — plus a test proving no `_ALLOWED_STEP_KEYS` entry is accepted-but-dropped (WIRE-01/02/03).
- Friendly `display_name` in the catalog (UXFIX-01); persisted `deliverable_mimetype`/`deliverable_filename` driving history-reopen (UXFIX-02); data-driven catalog as the home landing (UXFIX-03); generic mimetype renderer as the primary dispatch path (UXFIX-04).
- Record the two product decisions in REQUIREMENTS.md: keep-by-default retention (DECIDE-01) and premium-open-to-all-tiers (DECIDE-02), reflected in the model picker.
- One consolidated live-Bedrock pass on the `default` profile with Haiku 4.5, per-item evidence record (LIVE-01).

**Out of scope (from SPEC.md):**
- Exhaustive per-capability E2E proof — compose+launch is proven with **≥1 representative capability per lever-type**, not every user-allowed capability.
- ECS/container RuntimeEnvironment backend — stays local-only (designed, not built).
- Enabling code-exec / `spawn_subagents` / `security` gate by default — they stay `user_allowed=False` (engineer-only); this phase makes them **visible-but-locked**, not user-composable.
- New capability kinds or registry entries — surfaces/wires the **existing** registry only.
- Resolving CTX-04 (`run_revision` retirement) — remains an intentional VOID.
- Nyquist VALIDATION.md backfill — handled by `/gsd-validate-phase`, not here.
- Non-`default` AWS profile / ISS-018 resolution — external IT escalation, not repo work.

</spec_lock>

<decisions>
## Implementation Decisions

> The SPEC locks WHAT/WHY. These are the HOW decisions from this discussion. All four area decisions were the recommended option, user-confirmed 2026-06-14.

### Capability palette — placement & shape (SURF-01, SURF-03, EMP-02)
- **D-01:** ONE grouped capability palette panel **embedded inside the `AgentsPopup` composer** — NOT a separate standalone browse view. It is the single surface that satisfies SURF-01 (renders every kind), SURF-03 (shows what a workflow declares), and EMP-01 (attach user-allowed caps). One palette = INV-12-clean (no dual surface).
- **D-02:** **Reuse the `AgentModelPicker` fetch/loading/error/empty shell** (`AgentModelPicker.tsx:57,99-114`-style) for the palette's `GET /api/capabilities` fetch — same reuse-first pattern P20 used for the catalog. The FE already fetches `capabilities[]` (`api.ts:522-529`) but renders none of it; this consumes it.
- **D-03:** Render **grouped by kind**; each row shows name / description / `user_allowed` (trust) flag / security-gated flag / config schema — driven entirely by the fetched payload. **No hardcoded capability-name array** in the palette source (SC-001 grep target = 0).
- **D-04 (EMP-02):** `user_allowed=False` capabilities (exec, `spawn_subagents`, `security`/`approval` gates, `filesystem`/`postgres` MCP) render **visible-but-locked** (engineer-only / upgrade affordance) — never user-composable.

### Per-step lever surface (EMP-01, EMP-04)
- **D-05:** Attach per-step levers via a **per-agent "Advanced" expander** on each agent row in `AgentsPopup`. Treat **agent ≈ step** (the engine sequences one step per agent in a custom linear workflow). Expander exposes at minimum: a **validator**, a **human/validation gate**, a **non-default model**, and **retry** (plus deliverable type / context provider / compaction / fan-out / limits where user-allowed).
- **D-06:** Reuse the location where the **per-agent model picker already lives** (relocated into `AgentsPopup` in P18 / ISS-014) — extend it rather than building a separate per-step inspector.
- **D-07 (EMP-04):** When a user selects a capability that requires a coupled gate (validation/approval), the composer **auto-attaches the required gate inline** so the compiled manifest satisfies the §13 coupling policy. The compiler's coupling checks (e.g. exec⇒`gates:[security,approval]`, D-01) stay enforced as the server-side backstop.

### Capability metadata source (SURF-02)
- **D-08:** Each capability **self-describes via the registry** — add optional `description` + `config_schema` carried on the `@register(kind, name, *, user_allowed=...)` decorator (mirroring the existing `user_allowed=` kwarg in `registry.py:167-191`), surfaced by the existing live `_KNOWN` enumeration in `capabilities.py:106-118`. **No static metadata map in the API layer** (that would be a second hardcoded source — a newly `@register`'d cap would appear without metadata, eroding SC-001).
- **D-09:** The thin one-method Protocol ports stay unchanged; metadata is **additive-optional**. `config_schema` is populated per-capability for caps that take config, and legitimately stays `{}` for caps that take none. Replaces the literal `{}` stub at `capabilities.py:116`.
- **D-10:** `/api/capabilities` extension is **additive** — preserve the API-02 contract, `Depends(get_current_user)` auth, and permission scopes. `test_capabilities_api.py` extended to assert each entry carries `description` + security-gated flag + non-trivial `config_schema` where applicable.

### Richer-selection persistence (EMP-03)
- **D-11:** **Reuse the dormant `manifest_json` JSON column** on the `workflows` table (`workflow_definition.py:39`, nullable, future-fitted, never populated by user rows) — store a **compact per-step capability-selections map** there. **Zero new migration** (INV-12 reuse-first; P21 set the reuse-this-table precedent with migration 0021).
- **D-12:** Persisted selections are **owner-scoped** (the row already carries `user_id`/`owner_id`/`workspace_id` from P21), IDOR→404, and **re-validated with `trust="user"` at SAVE and at LAUNCH** by compiling the stored selections through the dormant untrusted compile path (`compiler.py` trust check, ~`:279-321`/`:312-321`). Round-trips: save → list → reopen shows the same selections.
- **D-13:** Launch reaches the compiler/engine through the **existing run path** — no new run endpoint, no kernel branch. Extends the P21 launch wiring (replay `{base_pipeline_type, agent_ids, model_overrides}` + now the per-step selections) at the `/api/user-workflows` save + the `websocket.py run_pipeline` re-validation site.

### Compiler latent-key materialization (WIRE-01, WIRE-02, WIRE-03)
- **D-14 (WIRE-01):** Materialize top-level `model:` → `CompiledWorkflow.model` and per-step `model:` → `Step.model` by passing the kwarg through the two compiler constructors (`compiler.py:231-244` + the `Step(...)` build ~`:505-517`). `ModelResolver` already reads workflow/step tiers (`model_policy.py:96/101`).
- **D-15 (WIRE-02):** Materialize per-step `retry:` → `Step.retry` via the same constructors. The RESUME-02 retry wrapper is already live and gated on `step.retry` (`engine.py:1840-1842/4512-4513`).
- **D-16 (WIRE-03 — DECIDED: materialize-and-consume):** Compile per-step `injects:` → `Step.injects` and have the engine **consume** it, merged with the AGENT.md-derived injects at the existing factory injection seam (`loader.py:102` → `factory.py:311-315`) — **generic, no workflow-name branch**. Goldens declare no per-step `injects:`, so the merge is a no-op there → INV-3 byte-identical.
  - **Fallback (planner applies ONLY if materialize-and-consume cannot be proven INV-3-safe):** reject-loudly — remove `injects` from `_ALLOWED_STEP_KEYS` and raise `CompilerError`. Either path satisfies the WIRE-03 acceptance.
- **D-17 (WIRE-03 test):** A **parametrized test enumerates every `_ALLOWED_STEP_KEYS` entry** (`compiler.py:65-86`) and asserts each is either reflected on the compiled `Step`/`CompiledWorkflow` or raises `CompilerError` — **no key accepted-but-dropped**. INV-5 preserved (strict key rejection stays; do NOT loosen the allow-list into silent-accept).

### UX / data-faithfulness (UXFIX-01..04)
- **D-18 (UXFIX-01):** Launchable manifests carry an authored `display_name:` (or leave the BE fallback null deliberately) so the catalog renders the friendly name (builds on the P20 `display_name` field; the P20 review fixed a BE coalesce that defeated the FE fallback — keep that fix intact).
- **D-19 (UXFIX-02):** Persist `deliverable_mimetype` + `deliverable_filename` as **additive columns on the `WorkflowRun` row** (`workflow.py:13-62`), carrying the existing run scope (owner_id+workspace_id). Drive history-reopen from the persisted values instead of re-sniffing from text (`types/index.ts:342-356`). Additive migration. Both keys stay in `_VOLATILE_STRIP_KEYS` so emission/persistence keeps the 5 goldens byte-identical (INV-3).
- **D-20 (UXFIX-03):** Make the **data-driven `WorkflowCatalog` the default home landing** so "no hardcoded name list" holds on the default view. The hardcoded `CreationHub.WORKFLOWS` array (`DashboardLayout.tsx:256/1070-1079`) no longer drives the default landing (removed or no longer mounted as home); the P20 `catalog` tab content becomes home.
- **D-21 (UXFIX-04):** Make the **generic mimetype renderer the PRIMARY dispatch** in `PreviewPanel.tsx` (currently fallback-only behind 4 first-party branches at `:557-569`). Restructure as a mimetype-dispatch table where the 4 first-party types (`user_stories`/`app_builder`/`ppt`/`prototype`) become **registered entries the generic dispatcher routes to** — generic-primary, no visual regression, existing per-type tests stay green.

### Product decisions (DECIDE-01, DECIDE-02 — LOCKED in SPEC, recorded here)
- **D-22 (DECIDE-01 / N9):** Artifact retention = **keep-by-default** (run artifacts retained indefinitely); `run_ttl`/`days:N` are opt-in overrides. Update REQUIREMENTS.md ART-04 to keep-by-default; reconcile the 3 stale "confirm" labels (REPO-02 N6/N10, REPO-04 N5/N7, FANOUT-05 N2). Any retention default in code/config reflects keep.
- **D-23 (DECIDE-02 / N11):** Premium-model policy = **open to all tiers** (no per-tier premium gating); global default stays Haiku with an ordered fallback chain on throttle/error. Update REQUIREMENTS.md MODEL-05; **drop the `user_allowed` tier filter at `AgentModelPicker.tsx:76`** so premium models are offered to every tier.

### Live verification (LIVE-01)
- **D-24:** **Defer the consolidated live-Bedrock pass to milestone-end** (defer-live-verification convention); phase completion gates on **offline evidence**. The live pass runs on the AWS `default` profile (acct 473293451041) with `claude-haiku-4-5` (Haiku 4.5); ISS-018 does not block on `default`. Produce a per-item evidence record (CONFIRMED-live or explicit disposition) for: COMPACT-03 · P6 CR-02 · P8 OTLP · P13 F1/F4/F5 · P14 SC4 · P16 SC1/SC2 · P19 ISS-004.

### Claude's Discretion (settle in research/planning — do not re-ask the user)
- The exact `@register` metadata mechanism (decorator kwargs `description=`/`config_schema=` vs optional classattrs/staticmethods on the impl) — lean decorator kwargs for consistency with `user_allowed=`.
- The exact JSON shape stored in `manifest_json` (compact `{step → {validators, gates, model, retry, ...}}` selections map vs a full synthesized partial manifest) — lean compact selections map compiled at launch.
- The `config_schema` representation (JSON-Schema-lite object vs a minimal field-spec list) per capability kind.
- Composer expander interaction details (which lever rows render per agent, ordering, empty states).
- Whether the security-gated flag is a distinct boolean or derived from `user_allowed=False` + kind — pick the additive, test-assertable shape.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase spec (authoritative — locked requirements, MUST read before planning)
- `.planning/phases/22-capability-surfacing-and-user-empowerment-universal-runtime-/22-SPEC.md` — the 17 locked requirements, full file:line evidence for every gap, boundaries, constraints, acceptance criteria, and the N9/N11 decision records (Interview Log).

### Registers (read before touching code — avoid duplication / contradicting locked decisions)
- `.planning/IMPLEMENTATION-REGISTER.md` — pointer-first per-phase index (code-free).
- `.planning/ISSUES-REGISTER.md` — issue lineage incl. ISS-018 (entitlement), ISS-015/WF-DB-01.
- `.planning/TEST-REGISTER.md` — BE + Playwright case index.
- `.planning/REQUIREMENTS.md` — ART-04 (DECIDE-01 target), MODEL-05 (DECIDE-02 target), traceability.

### Capability surfacing (SURF-01/02/03, EMP-02)
- `backend/app/api/capabilities.py` — the endpoint to extend additively: `CapabilityEntry` (`:56-64`), the `{}` `config_schema` stub (`:116`), the live `_KNOWN` enumeration loop (`:106-118`), `model_catalog` expansion (`:120-132`).
- `backend/agents/capabilities/registry.py` — `_KNOWN` membership (`:79-143`), `register()` decorator (`:167-191`), `discover()` (`:194-313`), `is_user_allowed`/`_TRUST` (`:336-346`), `CapabilityRegistry` (`:316-368`).
- `backend/agents/capabilities/model_catalog.py` — the `model_catalog` data capability (MODEL-04 / DECIDE-02 picker source).
- `frontend/src/lib/api.ts:522-529` — the existing `capabilities[]` fetch (consumed by the new palette); `:302` `getWorkflows` (name taken by run-history).
- `frontend/src/components/workflow/AgentModelPicker.tsx:72-78` — model_catalog consumer + the `user_allowed` filter at `:76` (DECIDE-02 removes the tier filter); the fetch/loading/error shell to reuse for the palette.

### Composer / per-step levers (EMP-01/03/04)
- `frontend/src/components/workflow/AgentsPopup.tsx` — the live per-agent composer (the palette + Advanced expander host).
- `frontend/src/components/workflow/IdeaInputPage.tsx` — save payload origin + launch preload props (`initialAgentIds`/`initialModelOverrides`, P21); `onRun` run-path send.
- `frontend/src/components/catalog/WorkflowCatalog.tsx` — P20 data-driven catalog (UXFIX-03 home landing; "Your workflows" + kebab from P21).
- `frontend/src/components/layout/DashboardLayout.tsx` — `home`=hardcoded `CreationHub.WORKFLOWS` (`:256/1070-1079`) vs `catalog` tab (`:1084-1093`) — the UXFIX-03 dual surface; `handleLaunchSaved` (P21).

### Compiler / plan / model policy (WIRE-01/02/03, EMP-03 trust path)
- `backend/agents/workflows/compiler.py` — `_ALLOWED_STEP_KEYS` (`:65-86`), `_compile_step` + extra-key rejection (`:328`/`:341`), the `Step(...)` constructor (`~:505`) and the workflow constructor (`:231-244`) that currently drop `model`/`retry`/`injects`, the `trust="user"` check + Limits-only-lower ceiling (`~:279-321`/`:312-321`).
- `backend/agents/workflows/plan.py` — `Step.model` (`:362`), `Step.retry` (`:368`), `Step.injects` (`:369`), `CompiledWorkflow.model` (`:408`); the typed per-step surface (`:341-411`).
- `backend/agents/model_policy.py:96/101` — `ModelResolver` workflow/step tiers (WIRE-01 consumer).
- `backend/agents/execution_engine/engine.py` — RESUME-02 retry wrapper gated on `step.retry` (`:1840-1842/4512-4513`); the `post_step` invocation seam (`:1666-1668`); `deliverable_mimetype`/`deliverable_filename` emit (`:2117-2128`).
- `backend/agents/loader.py:102` → `backend/agents/factory.py:311-315` — the live `injects` (AGENT.md frontmatter) seam WIRE-03 merges into.

### Persistence (EMP-03, UXFIX-02)
- `backend/app/models/workflow_definition.py` — the reused `workflows` table; `manifest_json` column (`:39`, dormant); the row (`:13-52`).
- `backend/app/models/workflow.py:13-62` — `WorkflowRun` (UXFIX-02 additive-column target).
- `backend/app/api/user_workflows.py` — P21 owner-scoped CRUD (save + IDOR→404; the SAVE-time re-validation site).
- `backend/app/api/websocket.py` — `run_pipeline` + the launch re-validation (`~:1394-1406`) the persisted selections flow through.
- `backend/alembic/versions/0021_*` — the P21 additive-migration precedent (UXFIX-02's new migration mirrors its shape).

### UX / deliverable rendering (UXFIX-01/04)
- `frontend/src/components/preview/PreviewPanel.tsx:557-569` — the generic mimetype dispatch (UXFIX-04 makes it primary).
- `frontend/src/types/index.ts:342-356` — the reopen mimetype re-sniff (UXFIX-02 replaces with persisted value).
- `backend/agents/workflows/manifest.py` — `display_name`/`user_launchable` manifest fields (P20; UXFIX-01).
- `backend/app/api/workflows.py` — `WorkflowSummary` `display_name` population (P20).

### Invariant tests (must stay green / be extended)
- 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) — INV-3 byte-identical.
- `backend/tests/unit/test_capabilities_api.py` (SURF-02), `test_manifest.py`/`test_workflows_api.py` (UXFIX-01), the WIRE-03 parametrized `_ALLOWED_STEP_KEYS` test (new).
- `lint-imports` at `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (Ports & Adapters).
- The targeted parity/gate suite (~35s) + SC-001 kernel name-free grep (= 0).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`AgentModelPicker` fetch shell** — fetch/loading/error/empty pattern over `GET /api/capabilities`; the palette and the model picker share it (D-02).
- **`WorkflowCatalog` (P20)** — data-driven, reads `GET /api/workflows`; becomes the home landing (UXFIX-03/D-20). Already hosts "Your workflows" + kebab (P21).
- **`@register` decorator + `discover()` + `_KNOWN`/`_TRUST` (registry.py)** — the self-registration seam D-08 extends with `description`/`config_schema`; live enumeration means a new cap auto-appears (SC-001).
- **Dormant `manifest_json` column (workflow_definition.py:39)** — future-fitted JSON slot, reused for per-step selections (D-11) with zero migration.
- **`trust="user"` compile path (compiler.py ~:279-321)** — fully built, never invoked; this phase activates it for save/launch re-validation (EMP-03/D-12).
- **RESUME-02 retry wrapper (engine.py:4512-4513)** — live, gated on `step.retry`; WIRE-02 just makes it manifest-reachable.
- **Generic mimetype renderer (P18 / ISS-021)** — exists as fallback in `PreviewPanel.tsx`; UXFIX-04 promotes it to primary.
- **P21 launch wiring** — `IdeaInputPage` preload props + `DashboardLayout.handleLaunchSaved` + `/api/user-workflows`; EMP-03 extends the persisted payload, not the run path.
- **`_VOLATILE_STRIP_KEYS`** — already holds `deliverable_mimetype`/`deliverable_filename`; keeps UXFIX-02 INV-3-safe.

### Established Patterns
- **Reuse-first FE** — every new file names its analog (P20/P21 mandate); minimize net-new UI.
- **Additive migrations only** — owner_id + workspace_id on every table/column scope; no destructive alter (UXFIX-02 new column; EMP-03 reuses an existing column).
- **Capability self-registration** — no central if/elif; `@register` + lazy `discover()`; the compiler validates against `_KNOWN`.
- **INV-3 goldens** — body/prompt/post_step/event-free changes must be proven byte-identical (run the suite, never assume); the scripted model ignores prompt bodies.
- **SC-001 name-free kernel** — every new branch keys on a generic capability/condition, never a workflow/agent name; grep gate = 0.
- **Defer-live-verification** — mark phase complete on offline evidence; live Bedrock pass at milestone-end.

### Integration Points
- `GET /api/capabilities` (`capabilities.py`) — additive metadata; the palette's data source.
- `AgentsPopup` — the palette + per-agent Advanced expander host.
- `/api/user-workflows` (P21) + `websocket.py run_pipeline` — the save + launch re-validation sites for persisted selections.
- The two compiler constructors (`compiler.py:231-244` / `~:505`) — the WIRE-01/02/03 materialization sites.
- `PreviewPanel.tsx` + the history-reopen path (`types/index.ts`) — UXFIX-02/04.
- `DashboardLayout` home view + `WorkflowRun` model — UXFIX-03 / UXFIX-02.
- `AgentModelPicker.tsx:76` — DECIDE-02 tier-filter removal.

</code_context>

<specifics>
## Specific Ideas

- The palette is **one surface, embedded in the composer** — explicitly NOT a separate standalone browse view (D-01). SURF-01 "every kind visible" is satisfied by the same panel rendering locked rows for `user_allowed=False` caps.
- Per-step levers attach via a **per-agent Advanced expander** treating **agent ≈ step** (D-05) — the engine sequences one step per agent in a custom linear workflow.
- The **representative-per-lever** acceptance bar (SPEC out-of-scope): prove compose→save→launch with ≥1 validator + 1 human gate + 1 non-default model + retry reaching execution — NOT every user-allowed capability.
- WIRE-03 `injects:` = **materialize-and-consume** (D-16), with reject-loudly as the INV-3-safety fallback the planner applies only if needed.
- The WIRE-03 test is **parametrized over `_ALLOWED_STEP_KEYS`** — the durable "no accepted-but-dropped key" guard (D-17).

</specifics>

<deferred>
## Deferred Ideas

- Exhaustive per-capability compose+launch coverage (every user-allowed cap wired+proven) — explicit SPEC follow-up beyond the representative-per-lever bar.
- ECS/container `RuntimeEnvironment` backend — designed-only this milestone; backend swap is a later milestone.
- Enabling code-exec / `spawn_subagents` / `security` gate for users — stays engineer-only (visible-but-locked); revisit post-N3 if ever.
- New capability kinds / registry entries — this phase surfaces the existing registry only.
- CTX-04 (`run_revision` retirement) — intentional VOID pending a separate product decision.
- Nyquist VALIDATION.md backfill (20 partial/missing phases) — `/gsd-validate-phase`, not here.
- ISS-018 (`hexaware-srini` entitlement) resolution — external IT escalation.
- A standalone read-only "Capabilities" reference/catalog view — considered and rejected for this phase (D-01 chose the embedded palette); could be added later for discovery if warranted.

</deferred>

---

*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime-*
*Context gathered: 2026-06-14*
