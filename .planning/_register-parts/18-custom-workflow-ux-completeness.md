## Phase 18 — Custom-Workflow UX Completeness (post-milestone)

**Folder:** `.planning/phases/18-custom-workflow-ux-completeness/`  ·  **Status:** Complete (2026-06-13) — `18-VERIFICATION.md` verdict `passed`, 5/5 success criteria verified, 0 overrides  ·  **Plans:** 5/5  ·  **Plan-id → §25:** (post-milestone — not in the milestone plan-id ledger)
**Requirements delivered:** none new — closes cluster E of the 2026-06-13 deep root-cause investigation: **ISS-021** (custom non-markdown deliverable had no faithful FE path), **ISS-014** (orphaned capability-palette composer = INV-3/12 dual-impl), **ISS-019** (WaveTreePanel below the 1440×950 fold), **ISS-015** (generic pipeline-type picker → WONTFIX). Delivers **MODEL-03**'s reachable FE half (per-agent `model_overrides` now wired into the run path). Sources: `.planning/ROADMAP.md` "### Phase 18"; `.planning/ISSUES-REGISTER.md` rows ISS-021/014/019/015 + cluster-E note (line 76).
**One-line outcome:** A brand-new SC-001 custom workflow now renders its declared deliverable (HTML→sandboxed iframe / markdown / zip-bundle) through a generic mimetype-dispatched FE renderer with **zero per-workflow FE code**, the dead capability-palette composer is deleted, the per-agent model picker is live and wired, and the wave panel clears the fold — all with the 5 characterization goldens byte-identical.

### 1. Goal & Success Criteria (what was PLANNED)

From `.planning/ROADMAP.md` "### Phase 18" (goal + 5 SC) and `18-CONTEXT.md` (cluster-E LOCKED decisions, code-proven file:line). **Depends on Phase 17.** Cluster E = "SC-001 custom workflows are backend-complete but UI-incomplete, plus orphaned dual UI" — FE-weighted with one INV-3-sensitive BE addition.

1. **(ISS-021)** A custom/unknown-type workflow whose declared deliverable is HTML renders in a **sandboxed iframe** (markdown→markdown, zip/bundle→file view) via a **GENERIC mimetype-dispatched renderer** — no per-workflow FE branch (SC-001); the resolved deliverable is also listed + downloadable in the Files tab. BE emits `deliverable_mimetype`/`deliverable_filename` on `pipeline_complete`, both added to `_VOLATILE_STRIP_KEYS` so the 5 goldens stay byte-identical.
2. **(ISS-014)** `WorkflowComposer.tsx` + `CapabilityPalette.tsx` deleted (proven unrouted; no broken imports; FE build + tests green); the per-agent model picker relocated into the live agent-composer with `model_overrides` reaching the `run_pipeline` payload (or, if too invasive, deleted with MODEL-03's FE-half recorded as v2 — decision recorded); `/api/capabilities` + `test_capabilities_api.py` retained.
3. **(ISS-019)** At 1440×950 during an active wave run the "WAVE / SUBAGENT TREE" heading is fully visible WITHOUT scrolling while the agent panel still scrolls internally — a **CSS-only flex-budget fix**.
4. **(ISS-015)** Dispositioned **WONTFIX** in the register with a by-design rationale (wizards + agent-composer are the launch surfaces; generic manifest-driven picker = v2/WF-DB-01). **Do not build the generic picker.**
5. INV-3 parity holds (5 goldens byte-identical, lint-imports 4/0, zero new tables/migrations); SC-001 honored (generic mimetype dispatch + no workflow-name FE branch); FE `tsc --noEmit` + vitest green.

### 2. What Was Implemented — per plan (BUILT)

| Plan | Wave · depends | Requirement | Built (BUILT) | Result |
|------|----------------|-------------|---------------|--------|
| **18-01** | w1 · — | ISS-021 (BE) | `DeliverableSpec.mimetype` optional field; compiler thin pass-through (`mimetype=raw.get("mimetype")`, INV-5); per-resolver default-mimetype helper (`deliverables/_mimetype.py` + a `default_mimetype` staticmethod on each of the 4 resolvers); emit `deliverable_mimetype` + `deliverable_filename` on every `pipeline_complete` from `ectx.deliverable`; both keys added to `_VOLATILE_STRIP_KEYS`. | 27 passed (17 mimetype unit + 10 goldens); lint-imports 4/0; 0 migrations. See `18-01-SUMMARY.md` "INV-3 / Verification Evidence". |
| **18-02** | w1 · — | ISS-019 | CSS-only flex budget of the left execution column in `DashboardLayout.tsx`: column wrapper `flex flex-col overflow-hidden` (dropped column-level `overflow-y-auto`); agent wrapper `flex-1 min-h-0 overflow-hidden`; wave wrapper `flex-shrink-0 max-h-[40%] overflow-y-auto`. No panel-component change. | Structural className-contract test green (`DashboardLayout.waveMount.test.tsx`); tsc clean. Pixel-fold proof deferred. `18-02-SUMMARY.md`. |
| **18-03** | w2 · 18-01 | ISS-021 (FE) | `GenericDeliverablePreview` in `PreviewPanel.tsx` — mimetype dispatch (text/html→sandboxed iframe, text/markdown→`MarkdownPreview`, zip→AppBuilder bundle view, else→download), taken only when `renderType` matches none of the known set; mirrored on the history-reopen surface (`WorkflowHistory.tsx`); one generic Files-tab row (`FilesTab.tsx`); shared exported `deriveDeliverableMimetype` helper (`types/index.ts`) imported by BOTH reopen surfaces so they cannot diverge; generic channel threaded through `DashboardLayout.tsx`. | 41 passed; SC-001 grep 0 matches; tsc clean; FE-only diff. `18-03-SUMMARY.md`. |
| **18-04** | w3 · 18-03 | ISS-014 | **RELOCATED** (not deleted) `AgentModelPicker` into the live `AgentsPopup` "Agents" tab; threaded its selection into `run_pipeline` as `model_overrides` via `IdeaInputPage` extraParams → `useWorkflow` `Object.assign(payload, context)` (MODEL-03 FE half, end-to-end); `model_overrides` included ONLY when ≥1 non-default model picked (empty → byte-identical payload). Fault-injection-proved orphan-ness (rename→.bak→tsc+vitest), then **DELETED** `WorkflowComposer.tsx` + `CapabilityPalette.tsx`. Kept `/api/capabilities` + `test_capabilities_api.py`. | tsc clean before/after delete; 0 broken imports; `test_capabilities_api.py` 8 passed; MODEL-03 wiring test green. `18-04-SUMMARY.md`. |
| **18-05** | w1 · — | ISS-015, ISS-014 | Docs-only: ISS-015 → **WONTFIX (by-design)** in `ISSUES-REGISTER.md` with rationale + the v2/WF-DB-01 guardrail; ISS-014 deletion-as-superseded reconciled across `REQUIREMENTS.md` API-06 + `IMPLEMENTATION-REGISTER.md` Phase-8/Phase-12 "composer-routing concern" notes. | Docs-only diff; no code. `18-05-SUMMARY.md`. |

### 3. Capabilities, Modules, Schema & API Added

**BE (additive, parity-neutral):**
- `DeliverableSpec.mimetype: str | None = None` — optional **declared** deliverable shape hint (`backend/agents/workflows/plan.py`); compiler passes it through verbatim (`compiler.py _compile_deliverable`), no defaulting (INV-5).
- New import-pure helper module `backend/agents/capabilities/deliverables/_mimetype.py` (`default_mimetype(strategy, name)`) + a `default_mimetype` staticmethod on each of the four resolvers. Defaults: `single_file`→infer from name extension (`.html`/`.htm`→`text/html`, `.md`→`text/markdown`, unknown→`application/octet-stream`); `serialized_sandbox`→`application/zip`; `streamed_text`→`text/markdown`; `ppt`→`text/html`. **Derived from the DECLARED strategy/name, never content-sniffed.**
- `pipeline_complete` now carries two **unconditional** keys — `deliverable_mimetype` + `deliverable_filename` — sourced from `getattr(ectx.deliverable, …)` beside `final_output` (clean + degraded). No new cross-boundary import.

**FE (generic, SC-001):**
- `GenericDeliverablePreview` — the generic mimetype-dispatched renderer in `PreviewPanel.tsx` (HTML→sandboxed iframe `sandbox="allow-scripts"`, NO `allow-same-origin`; markdown→`MarkdownPreview`; zip→AppBuilder bundle; else→download). Reused on the history-reopen surface (`WorkflowHistory.tsx`).
- Shared `deriveDeliverableMimetype` helper (`frontend/src/types/index.ts`) — the single reopen-side mimetype source imported by both reopen surfaces (live uses the BE-declared `deliverable_mimetype`).
- One generic deliverable row in `FilesTab.tsx` (resolved mimetype + filename via the existing `downloadBlob` path); per-agent `.md` outputs preserved as "Agent outputs".
- **Model picker relocated** into the live `AgentsPopup` Agents tab; `model_overrides` threaded into the `run_pipeline` payload — **MODEL-03 is now reachable end-to-end** (backend `_validate_model_overrides` already validated + persisted it; this closed the FE gap).

**NOTE — zero schema/API churn:** **zero new tables / migrations** (`find -newermt 2026-06-13 migrations` → none). `/api/capabilities` (API-02) + `test_capabilities_api.py` **retained** untouched (8 passed). No reopen-row persistence column added — reopen mimetype is content-derived (see §7 carry-forward).

### 4. What Was Deleted / Superseded (INV-12)

- **`frontend/src/components/workflow/WorkflowComposer.tsx` — DELETED.** Orphaned dual-impl: mounted by no route (pre-existing legacy, base commit `4889e3a8`). Do NOT resurrect (INV-12). The live custom-workflow surface is the agent-composer (`AgentsPopup` / `IdeaInputPage` "Workflow configuration" modal), not the capability palette.
- **`frontend/src/components/workflow/CapabilityPalette.tsx` — DELETED.** Consumed only by the composer (transitively dead). Do NOT resurrect.
- **`AgentModelPicker.tsx` — RETAINED, RELOCATED** (not deleted). Its prior home (the dead composer) is superseded by the live `AgentsPopup` Agents tab; it is now the **primary** model-selection surface, not an "additive sibling panel". The delete-fallback (MODEL-03 → v2) was NOT taken.
- Orphan-ness was **fault-injection-proven** before deletion (rename-to-`.bak` → `tsc --noEmit` + full vitest → zero NEW broken imports). The only references to the deleted symbols were two prose comments (`lib/api.ts`, `DashboardLayout.waveMount.test.tsx`), since tidied.
- Doc reconciliation (18-05): `REQUIREMENTS.md` API-06 framed **deletion-as-superseded** (API-06 NOT marked removed; `/api/capabilities`/API-02 stands); `IMPLEMENTATION-REGISTER.md` Phase-8 capability-palette note + Phase-12 "separate composer-routing concern" marked **RESOLVED** by Phase 18 / ISS-014.

### 5. Key Decisions & Locked Constraints (do NOT contradict)

- **Generic mimetype dispatch = SC-001 (LOCKED).** The deliverable renderer dispatches on the **declared mimetype** (live) / output-shape heuristic (reopen), **never a workflow name**. No FE-side workflow-name render branch (grep-clean across `PreviewPanel.tsx`/`page.tsx`/`WorkflowHistory.tsx`). REJECTED hacks (do not reintroduce): hardcode `ui_custom_proto`→iframe; route unknown→the `custom` branch (escaped HTML); BE content-sniff `final_output`.
- **The `custom` type is NOT a known branch (CR-01 fix, LOCKED).** `custom` was removed from `KNOWN_RENDER_TYPES` so a live `custom` HTML deliverable falls into the generic channel and gets the sandboxed iframe (not escaped MarkdownPreview). The 4 bespoke renderers (user_stories/ppt/prototype/app_builder) are untouched — the generic path is a FALLBACK only.
- **HTML is ALWAYS sandboxed (T-18-05, LOCKED).** Both live and reopen iframes are `sandbox="allow-scripts"` with **NO `allow-same-origin`**. `MarkdownPreview` uses NO `rehype-raw` (raw HTML escaped to text) — confirmed XSS-safe (WR-03); do not add `rehype-raw` to the generic markdown path.
- **INV-3: the 5 characterization goldens stay byte-identical via `_VOLATILE_STRIP_KEYS` (LOCKED).** The two additive `pipeline_complete` keys live there (mirroring `model_id`/`estimated_cost_usd`); `_REQUIRED_DATA_KEYS["pipeline_complete"]` is a SUBSET check so additive keys pass. Any future `pipeline_complete` key that must stay parity-neutral goes in `_VOLATILE_STRIP_KEYS` and must keep deliverable BYTES unchanged.
- **`model_overrides` empty-selection guard (LOCKED).** Only sent when ≥1 non-default model is picked → existing runs are byte-identical. Single ingress: `useWorkflow` `Object.assign(payload, context)` (no double-send).
- **WR-01 effective-strategy mimetype (LOCKED).** When `serialized_sandbox` resolves None and falls back to `streamed_text`, the emitted mimetype is derived from the **effective** strategy (the bytes actually produced), not the declared one — so the advertised mimetype matches the bytes.
- **MODEL-03 reachability decision:** the picker was RELOCATED (preferred branch), delivering MODEL-03 FE↔BE; it was NOT deferred to v2.
- **ISS-015 — WONTFIX at P18, ⚠ SUPERSEDED: reopened & CLOSED by Phase 20.** Phase 18 recorded WONTFIX for a *bare hardcoded* picker; Phase 20 then built the **data-driven** version the guardrail itself prescribed — a `WorkflowCatalog` that reads `GET /api/workflows` + the `user_launchable` flag (never a hardcoded name dropdown), launching via the existing run/wizard paths. So the rule still holds (**do not build a hardcoded-name picker**) but the catalog now IS the launch surface. → Phase 20 section. The original rationale: wizards collect template+design-system (a bare picker structurally can't); bare `prototype`/`ppt` are template-gated-unreachable; `sample_*` are test fixtures.

### 6. Status, Verification & Evidence (what HAPPENED)

**Verdict (`18-VERIFICATION.md`):** `passed`, score 5/5 must-haves, 0 overrides, 2026-06-13T18:20Z.

**Evidence:** 5 goldens (10 tests) + 17 mimetype unit + 8 capabilities-API = byte-identical / green; lint-imports **4 kept / 0 broken**; zero new migrations; FE `tsc --noEmit` exit 0; Phase-18 vitest areas **45 passed / 8 files** (incl. CR-01 live-custom-html→sandboxed-iframe, genericReopen, deriveDeliverableMimetype, modelOverrides). SC-001 grep clean (no workflow-name render literal). Both deleted composer files confirmed absent with 0 import refs.

**Review → fix arc:** `18-REVIEW.md` (standard depth, 20 files) found **1 critical (CR-01) + 3 warnings + 2 info**. CR-01 = the headline blocker: the LIVE surface still hardcoded `custom`→`MarkdownPreview` (escaped HTML) while reopen rendered correctly — the two surfaces diverged, the exact root-cause bug the phase chartered to kill. `18-REVIEW-FIX.md` (iteration 1) fixed **all 6** atomically: CR-01 (dropped `custom` from the live known set + regression tests, commit `db725a56`), WR-01 (`_effective_strategy` mimetype, `33c55a44`), WR-02 (bundle-shape derive in the shared helper, `f22e105b`), WR-03 (MarkdownPreview no-`rehype-raw` confirmed + security test, `f2ef8a7f`), IN-01/IN-02 doc fixes. INV-3 re-proven after the engine change (10 goldens green, no SNAPSHOT_UPDATE).

**Deferred (non-blocking):** two VISUAL confirmations — ISS-019 pixel-fold proof (heading bottom ≤ 950 at 1440×950, no scroll) and ISS-021 live custom-HTML pixel render — were deferred to the dedicated live Playwright pass (offline proofs = className-contract + dispatch-unit, both verified; per the defer-live-verification memory note). **Both were subsequently live+visually confirmed** in `CAMPAIGN-2026-06-13-phases16-19.md` (see §7).

**Key commits:** 18-01 `e9bfae82`/`2a607e57`; 18-02 `af61f1d3`/`81ed1719`; 18-03 `5f6ca616`/`3ae12120`/`13d1ad0c`; 18-04 `de30059b`/`61394d95`; 18-05 `d92fe946`; review-fixes `db725a56`/`33c55a44`/`f22e105b`/`f2ef8a7f`/`43be7d37`/`6a541f7b`.

### 7. Gotchas, Survivors & Carry-Forward

- **ISSUES-REGISTER dispositions (current):** ISS-021 **FIXED** (18-01/03), ISS-014 **FIXED** (18-04/05), ISS-019 **FIXED** (18-02), ISS-015 **WONTFIX at 18-05 → later reopened & FIXED by Phase 20** (the data-driven catalog). Per `ISSUES-REGISTER.md` line 79 (`CAMPAIGN-2026-06-13-phases16-19.md`), ISS-019/021/014 were **live + visually confirmed on the `default` Bedrock profile** in the consolidated post-phase pass — the two deferred visual confirmations are now closed (no product defect surfaced).
- **Reopen content-derive limitation (carry-forward, recorded in 18-REVIEW-FIX WR-02):** the *ideal* fix is persisting `deliverable_mimetype`/`deliverable_filename` additively on the run row and reading it on reopen; that column was out of scope. Until then, the shared `deriveDeliverableMimetype` heuristic keeps live/reopen in sync for **HTML** and **zip/bundle** shapes, but a custom **binary** deliverable with no detectable shape still derives to `text/markdown` on reopen. A future persistence pass should add the additive run-row column (carries `owner_id`/`workspace_id`) and read it on reopen.
- **`deferred-items.md` (out of scope, NOT introduced here):** 7 pre-existing FE test failures — `src/lib/workflowChaining.test.ts` (6) + `AgentProgressPanel.test.tsx` (1), same `availableChainTargets` chain-exclusion drift. Confirmed identical before/after the 18-04 deletion; last touched in `4889e3a8`/`a219fade` (pre-phase-18). NOT a phase-18 gap; wants a dedicated FE-health / workflow-chaining fix.
- **Do NOT rebuild:** the generic deliverable renderer (`GenericDeliverablePreview` + `deriveDeliverableMimetype`) and the relocated model picker (`AgentModelPicker` in `AgentsPopup` + the `model_overrides` wiring) already EXIST — extend, don't duplicate. **Do NOT resurrect** `WorkflowComposer.tsx`/`CapabilityPalette.tsx` (INV-12). The data-driven launch picker (ISS-015) was subsequently **built by Phase 20** (`WorkflowCatalog`) — extend that, and never a hardcoded-name dropdown.
- **The one thing to know:** the generic deliverable surface is **type-driven, not name-driven** — a new custom workflow renders by declaring `DeliverableSpec.mimetype` (or relying on the per-resolver default) and emitting it on `pipeline_complete`; the FE needs zero edits. Any new `pipeline_complete` field must go in `_VOLATILE_STRIP_KEYS` or it breaks the 5 goldens.

### 8. File Index (every file in this folder)

| File | What it is |
|------|-----------|
| `18-CONTEXT.md` | Cluster-E LOCKED decisions (ISS-021/014/019/015), code-proven file:line, in/out scope, rejected hacks, invariants. |
| `18-01-PLAN.md` / `18-01-SUMMARY.md` | ISS-021 BE: `DeliverableSpec.mimetype` + per-resolver defaults + emit on `pipeline_complete` + `_VOLATILE_STRIP_KEYS` parity guard. |
| `18-02-PLAN.md` / `18-02-SUMMARY.md` | ISS-019: CSS-only flex-budget of the left execution column (wave panel above the fold). |
| `18-03-PLAN.md` / `18-03-SUMMARY.md` | ISS-021 FE: generic mimetype-dispatched renderer (live + reopen) + shared derive helper + generic Files row. |
| `18-04-PLAN.md` / `18-04-SUMMARY.md` | ISS-014: delete the orphaned composer/palette + relocate the model picker + wire `model_overrides` (MODEL-03). |
| `18-05-PLAN.md` / `18-05-SUMMARY.md` | ISS-015 WONTFIX disposition + ISS-014 deletion-as-superseded doc reconciliation. |
| `18-REVIEW.md` | Code review (1 critical CR-01, 3 warnings, 2 info) — caught the live/reopen divergence. |
| `18-REVIEW-FIX.md` | All 6 findings fixed (iteration 1); INV-3 re-proven after the engine change. |
| `18-VERIFICATION.md` | Goal-backward verification: 5/5 success criteria verified, verdict `passed`, 2 deferred visual items. |
| `deferred-items.md` | 7 pre-existing out-of-scope FE test failures (workflowChaining / AgentProgressPanel). |
| `.gitkeep` | Folder placeholder. |
