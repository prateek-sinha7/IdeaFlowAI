# Bugs & Issues — 015 frontend-routing session log

Every bug/issue found this session: where it was, what "passing" means, what was actually
wrong, and what was done about it. Frontend items were fixed directly; backend items were
root-caused but left for the parallel backend session (out of this session's
`/frontend`-only scope).

## Fixed — frontend

| # | Path | To pass | Root cause | Fix |
|---|------|---------|------------|-----|
| 1 | `frontend/src/components/layout/DashboardLayout.tsx` | Every Back click navigates one screen back (nav −1), never straight to Dashboard | All 5 `onBack` handlers called `handleGoHome`, which always routes to `/` regardless of navigation history | Added `handleBackNav`: `router.back()` when `window.history.length > 1`, `handleGoHome` fallback otherwise; rewired all 5 `onBack` sites |
| 2 | `frontend/src/components/history/RunDetailPage.tsx` | Header has a refresh button + auto-refresh interval, with a visible countdown and a loading state while fetching | Feature didn't exist; first attempt reset-and-refetched atomically so "0 / reloading" never visibly showed | Added refresh button + interval `<select>` (Off/10s/15s/30s/1m); split the ticker (holds at 0) from a separate fetch-trigger effect; spinner icon while a fetch is in flight |
| 3 | `frontend/src/components/history/WorkflowHistory.tsx` | Same as #2, on the run-history list | Feature didn't exist | Same pattern mirrored from #2 (`isRefreshingRuns`/`runsRefreshMs`/`runsSecondsLeft`) |
| 4 | `frontend/src/components/history/RevisionFamilyView.tsx` | Every run card shows its agent count, regardless of workflow type | Agent-count suffix was only appended for hardcoded/known types | `FamilyGroupCard`'s label always appends `` `${agentCount} agent(s)` `` now |
| 5 | `RevisionFamilyView.tsx`, `hooks/useWorkflowMetadata.ts`, `store/slices/globalSlice.ts` | Any pipeline without a hardcoded `TYPE_META` entry shows its real catalog name, not generic "Custom" | No fallback past the hardcoded `TYPE_META` map; live catalog data was never consulted | New `selectWorkflowShortNameIndex` + `useWorkflowShortNames()` + `resolveWorkflowTypeLabel()`; resolves from the live `/api/workflows` catalog, humanized fallback otherwise |
| 6 | `WorkflowHistory.tsx`, `RevisionFamilyView.tsx` | "Custom" filter tab buckets every non-framework type, not just literal `"custom"` (5 shown → ~44 expected) | `baseWorkflowType` only bucketed exact `"custom"` runs; every dynamic-catalog type matched no bucket at all | New `filterBucketFor(type)`: the 4 known framework types keep their own bucket, everything else buckets as `"custom"` |
| 7 | `RevisionFamilyView.tsx` | `DivertBadge` names the target workflow, not its launch message + step id | Badge text was built from message text + step id; never looked up the target's workflow label | `DivertBadge` now uses `resolveWorkflowTypeLabel` (same resolver as #5); dropped the step-id clause |
| 8 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | Composer always mounts with its manifest's agents populated, never empty | `pipelineAgents`'s lazy `useState` initializer could run before `ALL_LIBRARY_AGENTS` was populated (race) | Added `resyncedAgentsFromLibrary` ref + effect that re-syncs once the library populates |
| 9 | `composer/CanvasNode.tsx`, `composer/CanvasView.tsx` | No orphaned component or unused imports | `ExternalPipelineCard` was superseded by `ExternalWorkflowNode` and never removed | Deleted `ExternalPipelineCard` + its unused imports; fixed a stale comment referencing it |
| 10 | `frontend/src/components/workflow/IdeaInputPage.tsx` | Page renders with real catalog copy for any launchable type, not just the hardcoded ones | `TYPE_CONFIG[effectiveType]` was `undefined` for any type outside the hardcoded map, crashing on `.tag` | New `useWorkflowCatalogEntry()` derives `tag`/`subtitle` from the catalog row when no curated `TYPE_CONFIG` entry exists (parallel session — superseded this session's interim `\|\| TYPE_CONFIG.custom` patch) |
| 11 | `DashboardLayout.tsx` (`createRouteForType`) | Clicking any catalog pipeline card navigates to its launch panel | Fallback route `/create` parsed to a truthy `mainView`, which the URL-sync effect used to stomp the optimistic `setMainView("input")` back to home | Route to a per-type path (`` `/create/${type}` ``) instead of the bare `/create` fallback |
| 12 | `frontend/src/lib/routes.ts`, `frontend/src/app/[...view]/page.tsx` | `/create/{any-catalog-type}` renders the launch panel, including on a cold load/refresh | Unrecognized `/create/{type}` fell through to `screen: "unknown"`, which triggers `notFound()` | `parseViewPath` now returns `{screen:"create-workflow", pipelineType}`, mapped to `mainView:"input"` (parallel session, also fixes cold-load which #11 alone didn't cover); own follow-up fixed a stale comment describing the old "unknown screen" mechanism |
| 13 | `frontend/src/components/workflow/LaunchWizard.tsx`, `LaunchWizard.test.tsx` | Saving a PPT/Prototype workflow returns `201`, not a `422` | `MODE_CONFIG.savePipeline` still sent the retired `base_pipeline_type` values `"od_ppt"`/`"od_prototype"` | Updated to `"ppt"`/`"prototype"`; updated the matching test assertion. Verified live: `201`, shows as "Presentation · 3 agents" |

## False alarms — investigated, not bugs

| # | Path | To pass | Root cause | Fix |
|---|------|---------|------------|-----|
| 14 | `IdeaInputPage.tsx` | N/A — investigated whether a fix was needed | `ReferenceError: Cannot access 'manifestSelections' before initialization`, but only appeared mid-stream during rapid Fast-Refresh (HMR) while the parallel session was actively editing the same file; a cold reload right after was completely clean | None — transient HMR artifact, not a real bug |
| 15 | `IdeaInputPage.tsx` | N/A — investigated whether a fix was needed | "Review gates · no gates" badge looked suspicious on gate-based fixtures, but it correctly reflects the separate, optional, user-configurable manual-review-checkpoint feature (`gate_agent_ids`) — unrelated to the pipeline's own built-in `gates:[...]` step logic | None — correct as shown |

## Root-caused — backend (not fixed, out of `/frontend` scope)

| # | Path | To pass | Root cause | Fix |
|---|------|---------|------------|-----|
| 16 | Backend LLM provider layer (`ex_A4_human_gate` pipeline) | All agents complete successfully | Every agent call rejected with `"The model rejected this request."` (0/5 completed, `pipeline_failed`); per the user, an Ollama misconfiguration | Not this session's fix — resolved once the backend switched to a properly configured AWS Bedrock provider (parallel session). Confirmed resolved: every later run shows `model_id: eu.anthropic.claude-haiku-4-5-20251001-v1:0` on every agent call |
| 17 | `backend/agents/execution_engine/engine.py` (~line 2938-3220), `backend/agents/capabilities/gates/conditional.py` | An unrecognized/malformed routing decision with no `default_next` hard-stops the run (`pipeline_failed`) — never silently executes a different branch | `conditional.py` correctly fails closed to `GATE_BLOCK` when `pick-language`'s reply isn't valid JSON (model ignored the strict-JSON-only instruction) and no `default_next` is declared. But `engine.py`'s POST-step gate loop has **no handling arm for `_outcome == "block"`** (unlike the PRE-step loop, which hard-stops correctly) — falls through to a plain `cursor += 1`, silently running whichever branch is declared first in the manifest (`say-hello`), and the pipeline still reports `pipeline_complete` | Not applied (backend, actively edited elsewhere). Suggested: add a `block`-outcome arm to the POST-step loop, scoped to the `conditional` gate specifically (via the `gate_blocked` event's `data.gate` field) so `validation`'s existing intentional soft-block isn't regressed, mirroring the PRE-step loop's hard-stop (`pipeline_failed`) |

**Note on #17:** reproduced twice (once via `tools/api/runs/run.ex_A4_human_gate.http`, once
live through the browser UI) before issue #16 was resolved — after that, the trigger
condition (non-JSON model reply) stopped occurring, so the run now passes reliably (4/4 clean
UI passes: english/spanish/dutch×2, all matching the human's actual choice). The engine gap
itself is still unpatched and will resurface on any future model format slip.

---

# Session log — spec 014 conditional-gates end-to-end (backend + canvas)

Numbered from 1 for this session. This session took the four spec-014 example cases
(A1 loop, A2 forward branch, A3 cross-workflow divert, A4 human-decided) from
"reference fixtures, never executed" to running end to end, then made them render and
launch from the Composer canvas. Every defect below was found by RUNNING something —
none were visible from reading code, a typecheck, or an API probe.

The earlier session's #17 (post-step `gate_blocked` does not halt the run) was
independently reproduced here; see #18 below.

## Fixed — backend engine

| # | Path | To pass | Root cause | Fix |
|---|------|---------|------------|-----|
| 1 | `agents/workflows/plan.py`, `compiler.py`, `execution_engine/engine.py` | A loop-back re-dispatch reaches its target with the retry instruction, not a byte-identical context | A backward jump rebuilt the target's context from scratch, so `greet` saw `context_sources: []` and emitted identical output on every pass — the loop could only ever fail closed at the cap | R-28: `RouteOutcome.feedback` (authored, compiler-validated as a string), stashed in `ectx.pending_route_feedback` at the jump and emitted by `_compose_context_message` as a retry block, popped so it is delivered once |
| 2 | `compiler.py` (`_ALLOWED_STEP_KEYS`), `plan.py` (`Step`), `engine.py` (`_specs_from_plan`) | A step declaring `consumes` actually receives the named upstream artifacts | `consumes` was never author-exposed: absent from `_ALLOWED_STEP_KEYS` and from `Step`, so `_filter_consumed_outputs` read `[]` for every manifest step — `check` was asked to judge a greeting it had never been shown. Second half: a composed step's runtime `AgentSpec` comes from `custom-agent/AGENT.md`, which declares neither `produces` nor `consumes` | R-29: added `consumes` to the allow-list and to `Step`; `_specs_from_plan` now overlays `produces`/`consumes` onto the runtime spec |
| 3 | `engine.py` (backward-jump arm, ~3017) | `step_visit_counts` is readable after a loop-back | Written under the AUTHORED id (`greet`) but read under the COMPOSED id (`custom-agent:greet`), so it was always 0 — silently disarming the R-08 gate-key fold and the completion record | R-08: both read and write now key on `ordered_agents[_route_index].id` |
| 4 | `engine.py` (`agent_skipped` emission) | A loop target that already ran is not reported "Skipped" | The conditional gate's `skipped_targets` were emitted unconditionally, so a BACKWARD target that had already produced `agent_complete` events was labelled Skipped — the UI honours the last lifecycle signal and rendered a step that ran twice as Skipped, under-reporting the run as 3/4 agents | Report a sibling only if it never ran (`any(r["agent_id"] == _sib_id for r in results)` → skip). A2's forward branch still reports both untaken branches, which is the negative case the runners now assert |
| 5 | `engine.py` (`agent_start` / `agent_complete`) | The UI can tell pass 1 from pass 2 of a looped step | No iteration information reached the wire at all | Additive `visit_count`, emitted ONLY when non-zero so the five characterization goldens stay byte-identical |
| 6 | `execution_engine/kernel_services.py`, `engine.py` (workflow-trigger arm) | A diverting parent can hand an instruction to the child run it starts | `run_trigger_workflow` called `_launch_run_core(content="")` unconditionally — a triggered child inherits `parent_run_id`/owner/workspace/budget but NOT the parent's message, so there was no channel at all | R-28 extended to the workflow arm: the matched outcome's `feedback` is threaded as the child's `content`. Defaults to `""`, so every existing divert is byte-identical |
| 7 | `app/api/run_stream.py`, `frontend/src/types/index.ts`, `tests/unit/test_sse_stream.py` | A divert closes the SSE stream cleanly, with no "Reconnecting…" flash | `pipeline_diverted` was in NEITHER stream-terminal set. The engine yielded the frame and returned, nothing recognised it as terminal, the connection dropped unclean → client showed "Reconnecting", reconnected, and only then replayed the divert — so the banner always arrived AFTER a spurious warning | Added to `_STREAM_TERMINAL_TYPES` (unioned in at the stream level, NOT into `_GATE_RESOLUTION_TYPES`, which also derives `_GATE_REARM_TYPES`), to the frontend constant, and to the guard test's `expected` set |
| 8 | `capabilities/gates/human.py`, `capabilities/registry.py`, `engine.py`, `compiler.py` | A manifest can say WHEN a human gate runs, and the same spelling always means the same thing | `gates: [human]` and `AGENT.md gate: Human_Gate` looked identical but did opposite things — pre-step (reviews the PREVIOUS step's output) vs post-step (reviews its OWN output, supports redo). Which one ran was decided by whether the step's agent had an `AGENT.md`, invisible from the manifest. `prototype` declares `gates: [human]` on three steps and **all three were dead lines** — the inline gate won every time | Split the vocabulary: `human` is now POST-step (what authors expect, and what every shipping pipeline actually does); `before-human` is the PRE-step variant. The inline-gate dedupe followed `human` into the post phase — without that, prototype's now-live declarations would fire ALONGSIDE the inline gate and double-prompt. Compiler rejects >1 human-family gate per step, because `gate_key` is `f"{run}:{agent_id}:{visit}"` with no gate name in it |
| 9 | `app/api/workflows.py` | `GET /api/workflows/{id}` returns usable step metadata for a COMPOSED workflow | `name`/`role`/`order` all came from an `AGENT.md` lookup; a composed step (`custom-agent:emoji`) has none, so every field collapsed to the raw id / `""` / `0` — a launch panel built from this showed five rows called `custom-agent:…` with no ordering | Prefer the compiled step's own `display_name` (the manifest's label), and use the position in `compiled.steps` as `order` — one ordering system, matching what actually runs |
| 10 | `app/api/workflows.py` (`WorkflowDetail`) | A client can reconstruct an EDITABLE workflow from the API | The compiled `steps` projection is lossy: no `prompt`, `tools`, `instance_id`, `depends_on` or `route`. Opening a workflow in the canvas and saving would have silently produced promptless steps | Added `manifest_steps` — the manifest's raw step dicts, verbatim. Already parsed and validated by `load_manifest`; no new derivation |
| 11 | `app/api/run_commands.py` (`RunCommand`, launch-source detection, Case 3) | "Run once" works on an edited-but-unsaved composition | A composed workflow's nodes are `custom-agent:<instance_id>` instances whose bare ids can never appear in the static allow-list `agent_ids` is checked against; the only escape was `user_workflow_id`, which requires saving first. `ComposerPage`'s own comment documents the limitation | Accept an inline `manifest` in the launch body, compiled at `trust="user"` — STRICTER than a saved row's `trust="db"`. Not a new trust surface: the same bytes could already be POSTed to `/api/user_workflows` and then launched |

## Fixed — frontend (Advanced canvas + full canvas)

| # | Path | To pass | Root cause | Fix |
|---|------|---------|------------|-----|
| 12 | `IdeaInputPage.tsx` | Advanced shows a composed workflow's agents | The roster came only from `LIBRARY_AGENTS`, which is built from `AGENT.md` files — a composed workflow has none, so the filter returned `[]` and Advanced rendered empty | Fall back to the compiled manifest's steps (already fetched for the capabilities strip) when the library has nothing for this type. Structural, not a `custom`-name branch (SC-001) |
| 13 | `IdeaInputPage.tsx` | A conditional step renders as a conditional on the canvas | `CanvasView` requires BOTH `agent.route` outcomes AND `selections[id].gates` containing `"conditional"`. Gates live in `selections` (a user-toggled lever in the composer), and a manifest-opened workflow has them DECLARED, not toggled — so that half was never populated and `check` drew as an ordinary node | Seed `selections` from the manifest's own `gates`, merged UNDER any saved/user selection so a user lever still wins |
| 14 | `IdeaInputPage.tsx` | Branch edges resolve and no node is falsely orphaned | Route targets in a hand-authored manifest are BARE instance ids (`done`) — the engine resolves those with a suffix fallback, the canvas does not: it compares targets against node ids (`custom-agent:done`). So `done` was never seen as a route target, rendered as an orphan, and every branch edge failed to resolve | Normalise `trigger: "step"` targets to node ids when mapping; `trigger: "workflow"` targets are workflow ids and are left alone |
| 15 | `IdeaInputPage.tsx` | The Advanced modal sees the manifest-derived selections | `AgentsPopup` seeds `liveSelections` with a `useState` INITIALIZER and is rendered unconditionally (`isOpen` only toggles visibility), so it mounted with the page — before the manifest fetch resolved. The later value never entered its state | Key the popup on whether the manifest has landed, so its initializer re-runs exactly once with the real seed |
| 16 | `routes.ts`, `[...view]/page.tsx`, `DashboardLayout.tsx`, `ComposerPage.tsx`, `LaunchWizard.tsx` | "Open in full canvas" opens THAT workflow, on a URL that survives refresh | Four separate faults, found one at a time by clicking: (a) the hand-off passed only `agentIds`, which `ComposerPage` resolves against the agent library where `custom-agent:*` does not exist → blank canvas; (b) the button did not exist on the prototype/ppt path at all — `AgentsPopup` has TWO mount sites and only `IdeaInputPage` was wired; (c) `ComposerPage` mounts TWICE (page.tsx briefly renders null through a cold-mount gate), and in-memory `savedComposition` does not survive the remount; (d) going BACK re-applied that composition to the launch panel, whose `initialAgentIds` restore dropped every composed id → "0 agents", surviving a refresh via the sessionStorage TTL | New route `/workflows/{type}/canvas` carrying the workflow's identity, seeded by a cold-load fetch of `manifest_steps`. Both entry points navigate there; the sessionStorage hand-off was deleted outright — the URL makes it unnecessary and it was the cause of (d) |
| 17 | `ComposerPage.tsx` | The composer populates on client-side navigation, not only on a cold load | Two one-shot seeds: the agent re-sync burns its ref the first time `ALL_LIBRARY_AGENTS` is non-empty — on a COLD load the library is also still empty so it gets a second chance, but on CLIENT-SIDE navigation it fired with no props and never ran again. `selections` was initializer-only and never re-derived at all, so gates were missing (`0 review gate`, no Route badge) | Both now keyed on `initialManifestSteps`, so they fire when the props actually arrive |

**Pattern worth naming:** #15, #16(c) and #17 are the same defect shape four times — state
seeded by a `useState` initializer or a one-shot effect, fed by data that arrives
asynchronously. None is visible to a typecheck or a pure-function test; each was found only
by clicking through the real UI.

## Open — not fixed

| # | Path | To pass | Root cause | Status |
|---|------|---------|------------|--------|
| 18 | `engine.py` post-step gate loop | A blocked conditional gate halts the run instead of advancing | **Same defect as the earlier session's #17**, reproduced independently here: `conditional` is a POST-step gate and the §8b terminate-on-block fix covered only the PRE-step loop. The cursor advances to the next step in sequence, which LOOKS like a correct forward branch, and the run reports `pipeline_complete` | OPEN. Not patched — making a post-step block terminal changes terminal semantics for every pipeline using `validation` gates, so it needs the test suite behind it. MITIGATED in tests: every branching `.http` runner now asserts `no gate_blocked`, so a fall-through fails loudly instead of scoring green (this is what caught it) |
| 19 | `app/agents/deep_agent_runner.py` (past `factory.py:389`) | A step with `read_files: false` cannot read the run sandbox | **`read_files: false` is not enforced at runtime.** On `ex_A1_loop`, 11 `tool_call`s executed despite every step denying reads, and `ls /` returned a real directory listing (`['/.logs/', '/emoji-…md', '/greet-…md']`). Steps burn their turn reading the previous step's `artifact_fallback` file and narrating it, which corrupts `check`'s output into prose so the conditional gate cannot parse a decision. Traced: compiler correct, `denied_tools` correctly computed at `factory.py:330` and passed to `DeepAgentRunner(denied_tools=…)` at `:389` — **the break is inside the runner, past that hand-off** | OPEN. Security-adjacent: a step denied read access can read the run sandbox. This is why `ex_A1_loop` fails consistently on Bedrock while A2/A3/A4 pass — A1 is the only fixture whose prompts reference prior output ("Look at the greeting above"), which invites file-seeking |
| 20 | `tests/unit/`, `tests/agents/` | Today's engine changes have regression cover | No tests were written for #1–#11 | OPEN. `cd backend && python3.11 -m pytest tests/unit/ tests/agents/ -q` has not been run since these changes. #8's dedupe is the one most worth covering — a `prototype` double-prompt would only surface on a live run |
| 21 | `composer/CanvasView.tsx` | Deleting a node that a route targets cleans or warns about the dangling outcome | Deleting `say-hallo` left `language`'s `dutch → say-hallo` outcome in place. The backend correctly refuses with a precise `R-10` message (`target 'say-hallo' … does not name a step id in this compiled workflow`), but only at launch | OPEN. Backend behaviour is correct; the canvas should not let the composition reach that state silently |
| 22 | `ComposerPage.tsx` (unmodified-built-in check) | A rename or prompt edit is honoured by "Run once" | The check compares step IDS only, so an edit that changes a name or prompt but not the id set is treated as "unmodified" and runs the workflow AS AUTHORED, silently ignoring the edit | OPEN. Narrow, but silent — the safer shape is to compare the serialised manifest |
| 23 | `tools/api/runs/` | `ex_A4_human_divert` has a repeatable test | Never given a `.http` runner; all three of its paths were driven by hand via curl | OPEN. The other six `ex_*` fixtures have runners |
| 24 | `IdeaInputPage.tsx`, `AgentsPopup.tsx`, `ComposerPage.tsx` | No debug logging in shipped code | `[wf] 1…7` console traces and the `debugLabel` prop were added deliberately to diagnose #12–#17 | OPEN. Intentional scaffolding, safe to strip |

## Verified this session

Backend, on AWS Bedrock (`eu.anthropic.claude-haiku-4-5`), via `tools/api/runs/*.http`:

```
A2 english / spanish / dutch          7/7   7/7   7/7
A3 english / spanish / dutch          7/7  12/12 12/12
A4 step-chooser (headless, spanish)   9/9
A4 divert  spanish / dutch / english  diverted+child / diverted+child / in-run
A1 loop                               FAILS — see #19
```

Canvas, in a real browser: all 7 `ex_*` fixtures render as designed; A1 draws
`retry ↺3` as a backward edge and `ok` forward; `/workflows/{type}/canvas` cold-loads
for `ppt`, `ex_A1_loop` and `ex_A4_human_divert`; Run once launches
`pipeline_type: ex_A2_branch` and routes to `say-hola` on Spanish input.

Contracts: 25/25 manifests compile; entitlement parity backend↔frontend; stream-terminal
sets in sync across backend, frontend and the guard test.
