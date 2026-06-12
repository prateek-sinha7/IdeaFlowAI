# Phase 14: run_revision real revision loop (F2 end-to-end) - Research

**Researched:** 2026-06-12
**Domain:** Brownfield engine refactor — replace the `_handle_revision` Phase-3 echo stub with a real dispatch through `ExecutionEngine.execute()` (Python / FastAPI / LangChain deepagents / manifest-compiled workflows)
**Confidence:** HIGH (all findings verified directly against the working tree at `feature/003-workflow-engine-decoupling`)

## Summary

`_handle_revision` (engine.py:3656–3943) today does everything EXCEPT run a model: it validates the instruction and owner, `assert_owns` the parent run, resolves the parent original via the 13-05 FR-014 three-link chain (exact kind → `deliverable` → `summary` with the IN-06 `[Error:` filter), composes the three-section revision context (optionally prefixed by the parent's `planning_context`), computes the WR-06 generic revision alias (`{target}.removesuffix('_output') + '_revision'`), then **writes the composed context back as the "revision" artifact** and emits a hand-rolled `pipeline_start`/`pipeline_complete` pair (`total_duration: 0.0`, fake single "revision-agent"). The fix is structurally simple because everything the real dispatch needs already exists: revision **manifests** exist for all five revision pipelines (`agents/workflows/{ppt_revision,od_ppt_revision,prototype_revision,user_stories_revision,app_builder_revision}/workflow.yaml`), revision **agents** exist with correct `pipeline_type` frontmatter, `execute()` is the single emit/stamp/persist chokepoint, and the `ppt` deliverable resolver already unwraps the `<artifact>`-wrapped revised deck the revision agents are prompted to emit.

Three non-obvious blockers shape the plan. (1) **The clarify pause:** every dispatchable manifest declares `planner: run` + `clarify.mode: auto`, and clarify-auto pauses **indefinitely** at `event.wait()` for a questionnaire round-trip (clarify_engine.py:155) — a dispatched revision would hang waiting for answers the revision panel never sends. The clean, INV-5-conformant fix is flipping `ppt_revision` and `od_ppt_revision` manifests to `planner: skip` (data-only; the skip path sets `gate_verdict = "PROCEED"` and bypasses clarify entirely), which requires updating the parity-trap test `test_manifest_parity.py::test_planner_run_everywhere` — its own docstring anticipates exactly this revisit, and **no characterization golden covers either manifest** (goldens: prototype, od_prototype, od_ppt, app_builder, prototype_revision). (2) **Double-stamping:** `execute()` stamps `seq`/`event_id` and persists `run_events` at its chokepoint, so the WR-06 `_RunEventSink`/`_stamped_send` wrapper inside `_handle_revision` must be **deleted**, not bypassed (INV-12) — keeping it would double-stamp every event and double-persist the ledger. `execute()` also creates the run workspace and calls `set_run_scope` organically (engine.py:756–816), so the CR-01 scope-writeback code in `_handle_revision` is superseded too. (3) **The blocking WS loop:** the `run_revision` WS branch awaits `_handle_revision` inline; that was fine for an instant stub but a multi-minute model run would freeze the socket's receive loop (no cancel, no ping, no reconnect). The run_pipeline path already solves this with a background task + per-run event queue.

The roadmap's design wrinkle (od_*_revision `injects` vs the 13-06 `missing_template_context` guard) is **settled by evidence: exempt revision dispatch by construction**. No revision agent declares any `injects` today (all six AGENT.md frontmatters verified), the guard lives only at the `run_pipeline` WS ingress which `_handle_revision` → `execute()` never traverses, the factory's `TemplateMissingError` only fires for inject-declaring agents, and parent-template re-resolution is impossible anyway (WorkflowRun persists no `template_id`; od_context is never persisted). Dispatch with `od_context=None`; the parent deck embedded in the composed context already physically realizes the template, and the revision prompts mandate surgical edits that preserve it.

**Primary recommendation:** Inside `_handle_revision`, after the existing FR-014 resolution + context composition, resolve `agents = get_pipeline_agents(revision_pipeline_type)` and `async for event in self.execute(...)`-forward through `websocket_send_fn`; capture `final_output` from the forwarded `pipeline_complete`; then write the exact-kind `derived_from` ref (the stub's write block, repointed at real content). Flip the two run_revision manifests to `planner: skip`. Move the WS `run_revision` branch onto the existing background-task + queue pattern. Delete the stub write, the fake event pair, and the `_rev_sink` stamping wrapper (INV-12).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| run_revision frame validation + WorkflowRun row creation | API / WS layer (`app/api/websocket.py`) | — | Already owns ingress validation, run-row creation, WR-06 type stamping |
| Parent resolution (FR-014 chain) + ownership gate | Engine kernel (`_handle_revision`) | ScopedStore (`agents/authz.py`) | `assert_owns` BEFORE any cross-run read (T-5-SEED) — must stay first |
| Revision context composition | Engine kernel (`_handle_revision`) | — | Existing three-section composer is correct and test-pinned; becomes the `user_message` |
| Revision pipeline dispatch | Engine kernel (`execute()`) | Manifest/compiler (`agents/workflows`) | The phase goal: route through the normal single chokepoint |
| Planner/clarify suppression for revisions | Manifest data (`workflow.yaml`) | — | INV-5: control flow declared as data, zero engine edits |
| Agent execution | deepagents runtime (`create_runner` → `DeepAgentRunner`) | — | INV-13: no new loop code |
| Deliverable resolution (artifact unwrap + carousel sanitize) | Capability (`deliverables/ppt.py`) | — | Already registered; `strategy: ppt` declared by both revision manifests |
| `derived_from` lineage persistence | Engine kernel (`_handle_revision`, post-dispatch) | ArtifactGraph + ScopedStore | Exact-kind ref keeps FR-014 chain link 1 for revision-of-revision |
| Event stamping + run_events ledger | `execute()` chokepoint | — | Single counter, single place — the `_rev_sink` duplicate is deleted |
| Revision run terminal status persistence | API / WS layer | — | Must reflect `pipeline_failed` vs `pipeline_complete`, not unconditionally "completed" |
| FE preview routing | Frontend (`useWorkflow` / dashboard) | — | Already handles `od_ppt_revision`/`ppt_revision` aliases (WR-06) and `pipeline_failed` (13-06) |

## Standard Stack

### Core (all existing — this phase adds ZERO new dependencies)

| Library / Module | Version / Location | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `deepagents` | 0.6.7 (pinned, INV-13) | Agent runtime via `create_runner` → `DeepAgentRunner` | Runtime mandate; dispatch through `execute()` inherits it automatically [VERIFIED: codebase + CLAUDE.md] |
| `ExecutionEngine.execute()` | `agents/execution_engine/engine.py:517` | The single dispatch/stamp/persist chokepoint | PERSIST-03 / D-11; arms its own run-events sink, creates workspace, stamps run scope [VERIFIED: engine.py:517–816] |
| Workflow manifests + compiler | `agents/workflows/<id>/workflow.yaml`, `compile_for_run` (engine.py:212) | Declarative routing: agent steps, deliverable strategy, planner/clarify flags | INV-5; all 5 revision manifests already exist [VERIFIED: ls + cat] |
| `agents/registry.get_pipeline_agents` | `agents/registry.py:223` | Resolve `list[AgentSpec]` for a derived pipeline id | Already imported by engine.py (line 1155); returns ppt/od_ppt revision agents correctly [VERIFIED: registry.py + AGENT.md frontmatter] |
| `ArtifactGraph.write_ref` + `ScopedStore.write_ref` | `agents/artifacts/graph.py`, `agents/authz.py` | Typed `derived_from` ref persistence, owner/workspace-scoped | The stub already uses this exact pattern; `*_output` kinds are the documented IN-01 carve-out (no warning) [VERIFIED: graph.py:135–160] |
| `PptResolver` | `agents/capabilities/deliverables/ppt.py` | `unwrap_artifact(sanitize_carousel_deck_html(last_streamed))` | Declared by both revision manifests (`strategy: ppt`); turns the agent's `<artifact>`-wrapped deck into raw HTML [VERIFIED: ppt.py:53–55] |
| pytest 8.3.4 / python3.11 / import-linter 2.11 | system | Offline verification | Targeted parity/gate suite + `/opt/homebrew/bin/lint-imports` [VERIFIED: probed in session] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manifest `planner: skip` (flip data) | New `execute()` param to suppress planner | Kernel edit + signature churn for behavior the manifest layer was BUILT to declare; rejected (INV-5) |
| Manifest `planner: skip` | Keep `planner: run`, set `clarify.mode: off` | Planner still makes a real LLM call (latency + cost) that adds nothing — the parent artifact + instruction is the complete context; rejected |
| Post-dispatch exact-kind `derived_from` write in `_handle_revision` | Thread `derived_from` into `execute()`'s terminal `deliverable` write | Kernel terminal block grows a revision-only param; the post-write reuses the stub's existing pattern with zero kernel-terminal change; rejected |
| Resolve agents inside `_handle_revision` | Resolve at the WS layer and pass in | Both SC-001-clean; in-engine keeps tests calling `_handle_revision` directly self-contained and keeps the WS branch thin — recommend in-engine; either acceptable |

**Installation:** none — no new packages.

## Package Legitimacy Audit

No external packages are installed by this phase. **Packages removed due to slopcheck [SLOP] verdict:** none. **Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
FE revision panel (DashboardLayout.tsx:388–403)
  │  WS frame: {type: "run_revision", parent_run_id, target_artifact_type: "ppt_output"|"od_ppt_output", instruction}
  ▼
websocket.py run_revision branch (≈line 865)
  │  validate instruction/params → create WorkflowRun row (type = WR-06 alias, owner_id=user.id)
  │  [RECOMMENDED: dispatch as background task → per-run event queue → WS drainer,
  │   mirroring run_pipeline — the inline await blocks the receive loop for minutes]
  ▼
ExecutionEngine._handle_revision (engine.py:3656)
  │  1. guards (instruction, owner_id)                      ── KEEP unchanged
  │  2. ScopedStore(owner_id) → assert_owns(parent_run_id)  ── KEEP first (T-5-SEED)
  │  3. FR-014 chain: exact kind → "deliverable" → "summary"── KEEP unchanged
  │  4. compose 3-section revision_context (+planning ctx)  ── KEEP unchanged
  │  5. revision_pipeline_type = WR-06 suffix transform     ── KEEP unchanged
  │  6. DELETE: _RunEventSink/_stamped_send/set_run_scope writeback (execute() owns all of it)
  │  7. NEW: agents = get_pipeline_agents(revision_pipeline_type)  (derived string, no literal)
  │  8. NEW: async for event in self.execute(
  │            agents=agents, user_message=revision_context,
  │            pipeline_run_id=pipeline_run_id, pipeline_type=revision_pipeline_type,
  │            user_id=owner_id, model_id=model_id, parent_run_id=parent_run_id,
  │            od_context=None, gate_agent_ids=[]):
  │          forward event via websocket_send_fn; capture pipeline_complete.final_output
  ▼
execute() chokepoint (engine.py:517)
  │  stamps seq/event_id, persists run_events, creates workspace, set_run_scope,
  │  records run_capabilities(runtime=langchain_deepagents)
  ▼
_execute_impl: compile_for_run("od_ppt_revision") → manifest (planner: skip ← THE DATA FLIP)
  │  skip path: gate_verdict=PROCEED, no planner LLM call, no clarify pause
  │  context_providers [opendesign, previous_run]: both NO-OP here
  │    (od_context=None → opendesign returns {}; revises_existing absent → previous_run returns {})
  ▼
per-step dispatch: od-ppt-revision-agent (or ppt-revision-agent → ppt-revision-assembler)
  │  create_runner → deepagents graph → streams agent_start/chunk/complete
  ▼
deliverable strategy "ppt": unwrap_artifact(sanitize(last_streamed)) → revised deck HTML
  │  terminal block persists kind="deliverable" ref (13-05) + emits pipeline_complete
  │  {pipeline_type: "od_ppt_revision", final_output: <revised HTML>, real duration/tokens}
  ▼
_handle_revision post-dispatch (NEW, replaces stub write):
  │  write exact-kind ref: kind=target_artifact_type, derived_from=original.id,
  │  workspace_id=original.workspace_id, visibility="workspace", content=final_output
  │  (guarded on non-empty final_output; skip on pipeline_failed)
  ▼
FE: pipeline_complete routed by od_ppt_revision/ppt_revision alias → revised deck in preview
```

### Recommended Change Footprint

```
backend/
├── agents/execution_engine/engine.py        # _handle_revision: stub → dispatch + post-write (the only kernel edit)
├── agents/workflows/ppt_revision/workflow.yaml      # planner: run → skip
├── agents/workflows/od_ppt_revision/workflow.yaml   # planner: run → skip
├── app/api/websocket.py                     # run_revision branch: background-task dispatch + terminal-status fidelity + agent_count
└── tests/
    ├── unit/test_revision_intelligence.py   # real-dispatch contract (keep validation/ownership guards as-is)
    ├── unit/test_run_revision_fe_contract.py# assert revised artifact, not context blob; model runs observed
    └── agents/test_manifest_parity.py       # exempt the two run_revision manifests from planner-run trap
```

### Pattern 1: Forward-and-capture dispatch (the core refactor)

**What:** `_handle_revision` becomes: resolve parent → compose context → dispatch `execute()` as an inner async-for, forwarding every event outward and capturing the terminal payload.
**When to use:** exactly here — `execute()` is an async generator; `_handle_revision` is a coroutine with a send-callback.
**Example (shape, not verbatim):**
```python
# Source: engine.py execute() signature (517–533) + current stub (3874–3943)
final_output: str | None = None
terminal_failed = False
async for event in self.execute(
    agents=agents,
    user_message=revision_context,
    pipeline_run_id=pipeline_run_id,
    pipeline_type=revision_pipeline_type,   # WR-06 alias — FE-routed, data-derived
    user_id=owner_id,                        # execute() derives owner_id = user_id
    model_id=model_id,
    od_context=None,                         # settled wrinkle: no template re-resolution
    gate_agent_ids=[],                       # no inter-agent HITL gate on a panel revision
    parent_run_id=parent_run_id,             # data only; previous_run provider no-ops (revises_existing False)
):
    if event.get("type") == "pipeline_complete":
        final_output = event.get("data", {}).get("final_output")
    elif event.get("type") == "pipeline_failed":
        terminal_failed = True
    await websocket_send_fn(event)
```
Note: events arriving here are ALREADY stamped/persisted by `execute()` — `websocket_send_fn` must be the raw sender (the `_stamped_send` wrapper is deleted).

### Pattern 2: Manifest-declared control flow (INV-5)

**What:** suppress planner+clarify for run_revision pipelines by declaring `planner: skip` in the two manifests. The engine's skip branch (engine.py:1200–1205) sets `gate_verdict = "PROCEED"`, builds `_default_planning_context(user_message)`, and emits no planner events — clarify is never reached.
**When to use:** any behavior the manifest layer already declares. Do NOT add an `execute()` parameter for this.

### Pattern 3: Post-dispatch lineage write (preserves FR-014 chain link 1)

**What:** after the dispatch completes, persist the revised content under the EXACT target kind with `derived_from=original.id` — the same `ArtifactGraph().write_ref(...)` + `await store.write_ref(_ref)` block the stub uses (engine.py:3891–3914), with `content=final_output` instead of `revision_context`.
**Why:** revision-of-revision resolves the parent via chain link 1 (exact `target_artifact_type`); `execute()`'s terminal block only writes the generic `kind="deliverable"` ref (chain link 2) and carries no `derived_from`. Both refs coexisting is correct and intentional. `*_output` kinds are the documented IN-01 vocabulary carve-out (graph.py:48–51) — no warning fires.

### Anti-Patterns to Avoid

- **Branching around the stub** (`if real_dispatch: ... else: <stub>`): INV-3/INV-12 violation — the stub write, the fake `pipeline_start`/`pipeline_complete` pair, and the `_rev_sink` stamping path must be deleted in the same change that replaces them.
- **Workflow-name literals in the kernel:** never `if revision_pipeline_type == "od_ppt_revision"`. Everything is derivable: alias via the existing suffix transform, agents via `get_pipeline_agents(<derived>)`, manifest via `compile_for_run(<derived>)`. The banned-pattern gate (`test_banned_patterns.py`) hard-fails `if pipeline_type ==` / `spec.id ==` in `agents/execution_engine/`.
- **Re-stamping events:** any wrapper that mutates `seq`/`event_id` on events yielded by `execute()` corrupts the SAFE-03 contiguous-seq contract and double-writes `run_events`.
- **Auto-answering the clarify questionnaire from `_handle_revision`:** a hack around manifest data; the skip flip is the sanctioned mechanism.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Running the revision agents | A bespoke "revision loop" calling the model directly | `execute()` → `create_runner` → deepagents | INV-13 hard mandate + banned-pattern CI gate; the docstring's "DeepAgent revision loop" means dispatching the existing runtime, not writing a loop |
| Event stamping/persistence for the revision run | Keeping/extending `_RunEventSink` in `_handle_revision` | `execute()`'s chokepoint | One counter, one place (PERSIST-03); execute() also handles workspace + run-scope + run_capabilities |
| Artifact unwrap / deck sanitize | Regex in `_handle_revision` to strip `<artifact>` tags | declared `deliverable: strategy: ppt` resolver | PARITY-07 capability already does sanitize+unwrap in the verified order |
| Suppressing planner/clarify | New engine flag or `_resume_from` abuse | manifest `planner: skip` | INV-5; resume-path abuse would also skip the state-machine "planning" transition semantics |
| Cross-run artifact reads/writes | Raw SQLAlchemy queries | `ScopedStore` (default-deny owner+visibility filter) | AUTHZ-01/03; `visibility="workspace"` rows resolve same-owner cross-run regardless of workspace mint |
| Scripted-model test driving | New fake chat model | `tests/agents/_scripted_model.py` (`ScriptedFakeChatModel`, `_scripts_for`, `_drive` patterns) | Stock LangChain fakes don't drive the deepagents loop; the harness handles RUNS_ROOT, create_runner patching, unique run-ids |

**Key insight:** Phase 13 (13-05 + WR-06) already built every seam this phase needs — the FR-014 chain, the generic alias, the deliverable ref, FE routing, `pipeline_failed` semantics. Phase 14 is a *wiring* phase: connect `_handle_revision`'s composed context to the existing dispatch chokepoint and delete the stub. Resist any temptation to add new mechanisms.

## Common Pitfalls

### Pitfall 1: ClarifyEngine hangs the revision forever
**What goes wrong:** Dispatching with the manifests as-is (`planner: run` + `clarify.mode: auto`) forces `CLARIFY_REQUIRED` on every run; `ClarifyEngine.run` emits `questionnaire_ready` then `await event.wait()` with **no timeout** (clarify_engine.py:134–155). The revision panel never submits answers → permanent hang.
**Why it happens:** clarify-auto was a deliberate parity lock (parity trap #1/#2, 07-05).
**How to avoid:** flip `ppt_revision` + `od_ppt_revision` manifests to `planner: skip`; update `test_manifest_parity.py::test_planner_run_everywhere` (parametrized over ALL `PIPELINE_AGENTS` keys) to expect `skip` for exactly these two ids. Leave `clarify:` blocks untouched (required manifest key; parity trap #2 test on defaults keeps passing). Do NOT touch `prototype_revision` (it HAS a characterization golden and a live run_pipeline FE flow).
**Warning signs:** a test or live run stuck in state `waiting_for_user` with a `questionnaire_ready` event.

### Pitfall 2: Double-stamped events / double run_events rows
**What goes wrong:** keeping `_stamped_send` while forwarding `execute()` events overwrites the chokepoint's `seq`/`event_id` with a second counter and persists a duplicate ledger row per event.
**How to avoid:** delete `_rev_sink`, `_rev_counter`, `_stamped_send`, and the deferred-arm/`set_run_scope` writeback block (engine.py:3697–3823 portions) — `execute()` does workspace mint + `set_run_scope` + sink arming itself (engine.py:756–816). Note the behavior delta: the revision run now gets its OWN workspace (fresh mint) instead of inheriting `original.workspace_id`; cross-run revision-of-revision reads still resolve because the scope filter widens on `visibility IN ('workspace','public')` for the same owner (authz.py:104–117).
**Warning signs:** `seq` deltas ≠ 1 in run_events; duplicate event_ids; IntegrityError warnings on persist.

### Pitfall 3: The inline await freezes the WebSocket
**What goes wrong:** the WS `run_revision` branch awaits `_handle_revision` inline (websocket.py:946). With real model runs (~minutes), the socket's receive loop processes nothing — `cancel_pipeline`, pings, reconnects all stall.
**How to avoid:** dispatch via the existing background-task + `_get_or_create_queue(pipeline_run_id)` + drainer pattern the `run_pipeline` path uses (websocket.py:1498+). Minimum bar if the planner descopes this: explicitly record the inline-blocking limitation as an accepted risk; but the queue pattern is strongly recommended since the infrastructure already exists.
**Warning signs:** live test: send `run_revision`, then `cancel_pipeline` — observe the cancel is processed only after completion.

### Pitfall 4: Terminal-status lies on failure
**What goes wrong:** the WS branch flips the revision `WorkflowRun.status` to `"completed"` unconditionally after `_handle_revision` returns (websocket.py:955–964). A dispatched run that ends in `pipeline_failed` (13-06 total-collapse) or degraded completion would be recorded as a clean success — and the FE revision-of-revision lookup matches `status === "completed"`, so a failed revision becomes a future revision parent.
**How to avoid:** thread the terminal event type (or a return value / captured flag) back to the WS layer; set `failed` on `pipeline_failed`. Also: skip the post-dispatch exact-kind `derived_from` write when `final_output` is empty/None (mirrors the 13-05 `final_output and results` guard).
**Warning signs:** a revision run with zero `agent_complete` events but DB status `completed`.

### Pitfall 5: Stub-pinning tests break in cascades, not cleanly
**What goes wrong:** `test_revision_intelligence.py` (792 lines) pins stub semantics deeply: `pipeline_complete.final_output` contains the three `===` section markers, the stored ref's content IS the context blob, `state_restoration_failed` fires on write failure, and run_events persistence asserts the `_stamped_send` path. `test_run_revision_fe_contract.py` asserts `parent_deliverable in final_output`. After real dispatch, `final_output` is the agent's REVISED artifact — none of those hold.
**How to avoid:** rewrite both suites to the real-dispatch contract in the same plan that changes the engine (success criterion 3 names them explicitly). Keep unchanged: empty/whitespace-instruction ValueError, falsy-owner ValueError, FR-014 ValueError byte-unchanged message, cross-owner PermissionError BEFORE any event. New assertions: scripted revision agent observed (`agent_start`/`agent_complete` for `od-ppt-revision-agent`), `final_output` == scripted revised deck (unwrapped), exact-kind ref persisted with `derived_from == original.id` and `content == final_output`, `pipeline_type == "od_ppt_revision"`. Test wiring: reuse `_scripted_model.py` patterns — patch `factory_mod.create_runner` AND `engine_mod.create_runner`, patch `settings.RUNS_ROOT` to a temp dir, unique `pipeline_run_id` per test (the state machine is a process-wide singleton — a reused id raises StateMachineError). `_scripts_for` has a generic text fallback for unknown agents; add a dedicated `od-ppt-revision-agent` script emitting an `<artifact>`-wrapped revised deck for deterministic unwrap assertions.
**Warning signs:** tests that pass by matching the instruction text inside `final_output` — the instruction may legitimately appear in a real revision too; assert on the scripted deck content instead.

### Pitfall 6: `execute()` requires the compiled plan ↔ registry membership to agree
**What goes wrong:** `_execute_impl` raises `RuntimeError` if `[s.agent_id for s in compiled.steps] != registry membership` (engine.py:1157–1170). Passing a hand-built agent list that diverges from the manifest steps (e.g., filtering agents) breaks dispatch.
**How to avoid:** always pass exactly `get_pipeline_agents(revision_pipeline_type)`. For `ppt_revision` that is TWO agents (`ppt-revision-agent`, `ppt-revision-assembler`) — update the WS row's `agent_count` (currently hardcoded 1) or accept the cosmetic drift consciously.

### Pitfall 7: An unmapped target type now fails later and differently
**What goes wrong:** the stub never dispatched, so any `target_artifact_type` worked. After the change, a target whose derived alias has no manifest (e.g. a hypothetical `foo_output` → `foo_revision`) raises `FileNotFoundError` from `compile_for_run` mid-`execute()` — caught by the WS branch's broad `except Exception` → `revision_error`. Acceptable, but consider a clearer pre-dispatch guard (empty `get_pipeline_agents(...)` → ValueError naming the unsupported target) so the FE gets `revision_validation_error` with an actionable message. Path-traversal is already closed: the alias resolver maps over a closed registry-derived set (T-04-09).

### Pitfall 8: INV-3 scope is exactly "non-revision runs"
**What goes wrong:** over- or under-scoping parity. The 5 goldens (prototype, od_prototype, od_ppt, app_builder, prototype_revision) must stay byte/event-identical — note `prototype_revision` IS one of them and rides `run_pipeline`, NOT `_handle_revision`; nothing in this phase may touch its manifest, the `previous_run` provider, the `revises_existing` gating, or any `execute()` mainline code path. The recommended design changes `execute()` not at all — only `_handle_revision` (never reached by goldens), two manifests with no goldens, and websocket.py's run_revision branch.
**Warning signs:** any diff inside `_execute_impl`, the providers, or the deliverable resolvers.

## Code Examples

Verified key locations (file:line on the current tree):

### The stub to delete (and the write block to repurpose)
```python
# engine.py:3887–3914 — the ONLY block that survives (repointed):
_rev_graph = ArtifactGraph()
_rev_ref = _rev_graph.write_ref(
    run_id=pipeline_run_id, owner_id=owner_id,
    workspace_id=original.workspace_id,
    kind=target_artifact_type,           # exact kind → FR-014 chain link 1
    producer_step="revision",
    producer_agent="revision-agent",     # consider: actual last agent id (IN-05 spirit)
    task_id=None,
    content=revision_context,            # ← becomes final_output (the real revision)
    location=f"artifact_refs/{target_artifact_type}",
    derived_from=original.id,
    visibility="workspace",
)
new_artifact_id = await store.write_ref(_rev_ref)
# engine.py:3876–3885 (fake pipeline_start) and 3931–3943 (fake pipeline_complete,
# total_duration 0.0) are DELETED — execute() emits the real pair.
```

### The WR-06 alias transform (keep verbatim — SC-001 idiom)
```python
# engine.py:3870–3872
revision_pipeline_type = (
    f"{target_artifact_type.removesuffix('_output')}_revision"
)
```

### The manifest flip (data-only)
```yaml
# agents/workflows/od_ppt_revision/workflow.yaml (and ppt_revision/workflow.yaml)
planner: skip   # was: run — bypasses planner LLM call AND the clarify pause
# clarify: block stays untouched (required key; parity trap #2 defaults test unaffected)
```

### The parity-trap test update
```python
# tests/agents/test_manifest_parity.py:70–79 — current form asserts planner == "run"
# for every non-internal PIPELINE_AGENTS key. Update: the run_revision-dispatched
# manifests (ppt_revision, od_ppt_revision) declare planner: skip (Phase 14);
# all others keep "run". The test docstring already says "if this ever flips,
# the manifests + this test must be revisited."
```

### Scripted revision-agent test wiring (mirrors _scripted_model.py:435–545)
```python
# tests pattern — _handle_revision dispatch with scripted models, no live deps:
from app.core.config import settings as _settings
_settings.RUNS_ROOT = tmp_runs_dir                      # RunSandbox is disk-real
factory_mod.create_runner = _patched_create_runner      # injects ScriptedFakeChatModel
engine_mod.create_runner = _patched_create_runner       # engine imported it by name
# planner: skip in the manifest → no planner/clarify patching needed (unlike _drive)
# unique pipeline_run_id per test — the state machine singleton rejects reuse
```

## State of the Art

| Old Approach (pre-Phase 14) | Current Approach (post-Phase 14) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `_handle_revision` echoes composed context as the "revision"; no model runs; `total_duration: 0.0` | Composed context dispatched through `execute()` against the registry revision pipelines; real agents, real deliverable | this phase | F2 closed end-to-end |
| Revision events stamped/persisted by a private `_RunEventSink` duplicate (WR-06) | `execute()` chokepoint owns stamping, workspace, run scope, run_capabilities | this phase | INV-12 single impl; revision runs gain run_capabilities audit rows |
| `ppt_revision`/`od_ppt_revision` manifests declare `planner: run` (parity trap #1) | `planner: skip` for these two ids only | this phase | Revisions go straight to agents; parity test updated; no goldens affected |
| Revision artifact = context blob under exact kind with `derived_from` | Real revised artifact under exact kind with `derived_from` + the generic `deliverable` ref from the terminal block | this phase | Both FR-014 chain links populated for revision-of-revision |

**Deprecated/outdated after this phase:**
- The stub comment "In a full implementation, this would run a DeepAgent revision loop" (engine.py:3888) — gone with the stub.
- The Phase-13 register note "the revision deliverable is still the Phase-3 stub" (IMPLEMENTATION-REGISTER §7 Phase 13) — superseded; the register entry for Phase 14 should record the closure.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| (none new — F2 completion) | SC1: real revision pipeline agents drive the run; deliverable is a revised artifact | Dispatch design (Pattern 1); manifests + agents + ppt resolver verified present; planner-skip flip removes the only hang |
| | SC2: `derived_from` lineage, owner/workspace-scoped, revision-of-revision resolves via chain link 1 | Post-dispatch exact-kind write (Pattern 3); ScopedStore visibility filter verified (authz.py:104–117); `*_output` IN-01 carve-out verified |
| | SC3: stub-pinning tests updated; non-revision goldens byte/event-identical; no kernel name literal | Pitfalls 5 & 8; banned-pattern gate + golden inventory verified; all new strings data-derived |
| | SC4: live Bedrock confirmation at milestone-end pass | Deferred per project convention (defer-live-verification-to-milestone-end); plans must mark it deferred, not blocking |
| | Design wrinkle (od_*_revision injects vs 13-06 ingress guard) MUST be settled | Settled — see Open Questions #1 resolution below: exempt by construction, `od_context=None`, no re-resolution |
</phase_requirements>

## Settled Design Wrinkle: od_*_revision `injects` vs `missing_template_context`

**Recommendation (concrete, evidence-backed): exempt revision dispatch by construction — pass `od_context=None`, keep revision agents inject-free, do NOT re-resolve the parent's template.**

1. **The premise is counterfactual today:** none of the six revision agents (`od-ppt-revision-agent`, `ppt-revision-agent`, `ppt-revision-assembler`, `prototype-revision-agent`, `user-story-revision-agent`, `app-builder-revision-agent`) declares ANY `injects` — verified in all six AGENT.md frontmatters. [VERIFIED: codebase]
2. **The guard is structurally out of the dispatch path:** `missing_template_context` lives only in `_handle_workflow_execution` (websocket.py:1382–1399), the `run_pipeline` ingress. `_handle_revision` → `execute()` never traverses it. The deeper backstop (`factory._compose_injection` raising `TemplateMissingError`) fires only for agents that DECLARE a template inject — none do. [VERIFIED: codebase]
3. **Re-resolution is impossible without schema work:** `WorkflowRun` persists no `template_id`/`design_system_id` (model verified column-by-column); `od_context` is never persisted; the only trace of the parent's template is the best-effort `template_files` seed in the parent's disk sandbox (48h TTL). [VERIFIED: app/models/workflow.py]
4. **The template isn't needed:** the composed revision context embeds the COMPLETE parent deck HTML — the physical realization of the template — and the revision prompts mandate surgical edits that preserve theme/fonts/structure ("NEVER change the visual theme"). Re-injecting the raw template SKILL.md would invite regeneration, the opposite of the surgical contract.
5. **Forward-compatibility:** if a future od revision agent declares `injects: [template, ...]`, the `run_pipeline` ingress guard already protects that path, and the dispatch path would need a template source — at that point the additive fix is persisting `template_id` on `WorkflowRun` (additive migration per Q3) and reloading `load_ppt_od_context` at revision dispatch. Out of scope now; optionally pin the decision with a regression test asserting revision-pipeline agents declare no `template` inject (makes the design choice executable).

## Open Questions (RESOLVED)

1. **WS dispatch concurrency model** — inline await (current) vs background task + queue (run_pipeline pattern).
   - What we know: inline blocks the receive loop for the full model run (Pitfall 3); the queue infrastructure exists and is proven.
   - What's unclear: whether the planner scopes the queue refactor into this phase or accepts inline-blocking as a recorded limitation for SC4's live pass.
   - Recommendation: adopt the queue pattern — it is mostly relocation of the dispatch call, and the live milestone-end pass (SC4) will exercise cancel/reconnect behavior.
   - **RESOLVED:** adopted by plan 14-02 — the WS `run_revision` branch moves onto the background-task + per-run-queue + drainer pattern (`_handle_revision_execution`), with terminal-status fidelity, agent_count derivation, and cancellation pinned by `test_run_revision_ws_dispatch.py`.
2. **Error-event vocabulary for the post-dispatch lineage write** — the stub emits `state_restoration_failed` when its write fails.
   - What we know: tests pin that event today; after the refactor the run itself has already completed when the lineage write runs.
   - Recommendation (Claude's discretion): keep emitting `state_restoration_failed` on lineage-persist failure (preserves the vocabulary and FE handling), but do not fail the run — the deliverable ref from the terminal block still exists (chain link 2 keeps revision-of-revision functional).
   - **RESOLVED:** adopted by plan 14-03 Task 1 — `state_restoration_failed` is kept on lineage-persist failure (event vocabulary preserved) and the run is NOT failed; the terminal-block `kind="deliverable"` ref keeps chain link 2 functional.
3. **`producer_agent` on the exact-kind ref** — stub hardcodes `"revision-agent"`.
   - Recommendation: use the actual final agent id from the dispatched run (mirrors the IN-05 fix in the terminal block); content/kind/hash unchanged, lineage metadata only. No agent-id literal — derive from the resolved spec list.
   - **RESOLVED:** adopted by plan 14-03 Task 1 — `producer_agent=agents[-1].id`, derived from the resolved spec list (no literal, IN-05 spirit).
4. **`user_stories_revision` / `app_builder_revision` / `prototype_revision` scope** — these ride `run_pipeline` (FE verified), not `run_revision`.
   - Recommendation: explicitly out of scope; only the two run_revision-dispatched manifests flip. State this in the plan to prevent scope creep.
   - **RESOLVED:** adopted by plan 14-01 as an explicit scope guard — `prototype_revision`, `user_stories_revision`, and `app_builder_revision` ride `run_pipeline` and are OUT OF SCOPE; only the two run_revision-dispatched manifests (`ppt_revision`, `od_ppt_revision`) flip, pinned by 14-01's INV-3 acceptance criterion (`git diff --stat` zero changes on the three untouched workflows).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3.11 | run/test backend (no venv) | ✓ | 3.11.14 | — |
| pytest | offline test battery | ✓ | 8.3.4 | — |
| deepagents | runtime (INV-13) | ✓ | 0.6.7 (import verified) | — |
| import-linter | `lint-imports` gate | ✓ | 2.11 at `/opt/homebrew/bin/lint-imports` | — |
| Chromium / Bedrock / Postgres | live-gated tests only | ✗ (offline) | — | Targeted offline suite; live deferred to milestone-end pass (SC4) |

**Missing dependencies with no fallback:** none blocking — live Bedrock is pre-declared deferred.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 on python3.11 (no venv) |
| Config file | backend test layout per backend/CLAUDE.md (tests/unit, tests/agents) |
| Quick run command | `cd backend && python3.11 -m pytest tests/unit/test_revision_intelligence.py tests/unit/test_run_revision_fe_contract.py -x -q` |
| Full suite command | targeted battery (below) — the FULL suite hangs offline (Chromium/Bedrock/Postgres-gated); never block on it |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC1 | run_revision drives real revision agents; deliverable is the revised artifact | unit (scripted models) | `python3.11 -m pytest tests/unit/test_run_revision_fe_contract.py -x` | ✅ exists — REWRITE to real-dispatch contract |
| SC2 | `derived_from` lineage + owner/workspace scope + revision-of-revision via chain link 1 | unit | `python3.11 -m pytest tests/unit/test_revision_intelligence.py -x` | ✅ exists — REWRITE storage/lineage tests; keep guards |
| SC3a | non-revision goldens byte/event-identical | characterization | `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_prototype_revision.py -q` | ✅ |
| SC3b | no workflow-name literal in the kernel | gate | `python3.11 -m pytest tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q` | ✅ |
| SC3c | manifest parity (planner flip pinned) | unit | `python3.11 -m pytest tests/agents/test_manifest_parity.py -q` | ✅ exists — UPDATE planner-run-everywhere expectation |
| SC3d | import boundaries | lint | `cd backend && /opt/homebrew/bin/lint-imports` | ✅ (4 contracts kept / 0 broken baseline) |
| SC4 | live Bedrock: FE-exact frame → revised deck in preview | manual-only (live) | milestone-end live pass | ❌ deferred BY CONVENTION (defer-live-verification-to-milestone-end) — not a Wave 0 gap |
| — | revision gating unchanged (`revises_existing` only on prototype_revision) | unit | `python3.11 -m pytest tests/agents/test_revision_gating.py -q` | ✅ unchanged |

### Sampling Rate
- **Per task commit:** the two revision suites + `test_manifest_parity.py` (`-x -q`, < 30s)
- **Per wave merge:** targeted battery — 5 characterization + banned_patterns + migration_ledger + touched suites + lint-imports (~35s, per project memory)
- **Phase gate:** full targeted battery green before `/gsd-verify-work`; live items recorded as deferred

### Wave 0 Gaps
- None structural — both named suites and the harness (`tests/agents/_scripted_model.py`) exist. One additive item: a dedicated `od-ppt-revision-agent` entry in `_scripts_for` emitting an `<artifact>`-wrapped revised deck (the generic fallback works but yields weak assertions).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (unchanged) | WS layer authenticates; `user.id` threads as owner |
| V3 Session Management | no (unchanged) | — |
| V4 Access Control | **yes** | `ScopedStore.assert_owns(parent_run_id)` MUST stay BEFORE any cross-run read AND before dispatch (T-5-SEED); cross-owner `PermissionError` propagates before any event. Pinned by `test_cross_owner_revision_denied` — keep it. |
| V5 Input Validation | **yes** | `target_artifact_type` is untrusted FE data: the suffix transform + closed-set alias resolution + `load_manifest(id, dir)` (T-04-09) prevents traversal; unknown target → clear ValueError/FileNotFoundError → `revision_error`/`revision_validation_error`, never a dispatch |
| V6 Cryptography | no | — |

### Known Threat Patterns for this change

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR on parent run (revise someone else's artifact) | Elevation | `assert_owns` first (existing, keep ordering); owner+visibility-scoped reads only |
| Prompt injection via `instruction` into the revision agent | Tampering | Unchanged surface — the same composed context the stub built now reaches a model; the agents' surgical-edit prompts bound the blast radius; no new tool grants (revision agents are `tools: []` except prototype/app variants out of scope) |
| Resource abuse: revisions now consume model tokens | DoS | `execute()` constructs the per-run `BudgetManager` from compiled limits; revision pipelines are 1–2 single_shot steps; `recursion_limit` backstop applies |
| Stale/forged `pipeline_run_id` reuse | Tampering | state-machine singleton rejects reused run ids; WS layer mints uuid4 per frame |
| Failed run recorded as completed (then used as a revision parent) | Repudiation | Pitfall 4 fix — terminal-status fidelity at the WS layer + empty-output write guard |

## Project Constraints (from CLAUDE.md)

- **INV-13:** every agent on LangChain `deepagents` (`deepagents==0.6.7`); no hand-rolled loop — satisfied by dispatching through `execute()`/`create_runner`; banned-pattern CI gate (R15) enforces.
- **SC-001 / INV-1:** kernel knows no workflow by name — all new strings derived (suffix transform, `get_pipeline_agents(<derived>)`, `compile_for_run(<derived>)`); `test_banned_patterns.py` hard-fails `if pipeline_type ==` / `spec.id ==` in `agents/execution_engine/`.
- **INV-3 / INV-12:** no dual implementations — the stub write, the fake event pair, and the `_rev_sink` stamping path are DELETED in the same change; the 5 characterization goldens (all non-run_revision paths) stay byte/event-identical.
- **INV-5:** manifests are data — planner suppression is a manifest flip, not engine control flow.
- **Q3 (persistence):** additive only — this phase needs NO migration (the optional future `template_id` column is explicitly deferred).
- **Hexagonal boundaries:** import-linter contracts (engine ↛ `app.api`; `agents.workflows`/`agents.capabilities` ↛ kernel) — the design adds no new cross-boundary imports (`agents.registry` is already imported by engine.py:1155).
- **GSD workflow enforcement:** all edits through `/gsd-execute-phase` (planned phase work).
- **Backend commit conventions:** `fix(engine):` / `test(agents):` / scoped prefixes per backend/CLAUDE.md; imperative, <72 chars.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The FE revision panel UX does not WANT a clarifying questionnaire on revisions (planner: skip is the desired product behavior, including for the legacy run_pipeline fallback path of ppt_revision/od_ppt_revision which loses its planner overlay) | Pitfall 1 / manifest flip | Low — a questionnaire on a surgical-edit panel is clearly worse UX; the legacy fallback fires only when no completed run id exists. Confirmable on the milestone-end live pass |
| A2 | Forwarding `execute()` events through `_send_revision_event` (which stamps `section=target_artifact_type`) is compatible with FE pipeline-state handling for the full event vocabulary (agent_start/chunk/tool_call etc., not just the terminal pair) | Architecture | Medium — if the FE revision view mis-renders mid-run events, it's cosmetic; pipeline_complete routing (the SC4 acceptance surface) is verified by WR-06 |
| A3 | `gate_agent_ids=[]` (suppress inter-agent HITL gates) is the right default for panel-driven revisions | Pattern 1 | Low — revision agents declare no static `gate:`; an empty list matches the FE's no-gates contract for this flow |

## Sources

### Primary (HIGH confidence — all verified in-session against the working tree)
- `backend/agents/execution_engine/engine.py` — `_handle_revision` (3656–3943), `execute()`/`_execute_impl` (517–1891), `compile_for_run` (212–230), planner-skip branch (1198–1205), clarify routing (1227–1343), membership assert (1157–1170), workspace/scope/capabilities block (746–835), terminal deliverable write (1799–1837)
- `backend/app/api/websocket.py` — run_revision branch (865–978), `_handle_workflow_execution` + `missing_template_context` guard (1255–1399), run_pipeline queue dispatch (1480–1525)
- `backend/agents/registry.py`, `backend/agents/workflows/{ppt_revision,od_ppt_revision,prototype_revision}/workflow.yaml`, `backend/agents/workflows/manifest.py`
- `backend/agents/prompts/{od-ppt-revision-agent,ppt-revision-agent,ppt-revision-assembler,prototype-revision-agent,user-story-revision-agent,app-builder-revision-agent}/AGENT.md` — zero `injects` declared
- `backend/agents/capabilities/context_providers/previous_run.py` (revises_existing gate), `opendesign.py` (od_context-None no-op), `backend/agents/capabilities/deliverables/ppt.py`
- `backend/agents/authz.py` (visibility-widened scope filter, set_run_scope), `backend/agents/artifacts/graph.py` (ARTIFACT_KINDS, IN-01 carve-out, derived_from)
- `backend/agents/execution_engine/clarify_engine.py` (the indefinite `event.wait()`)
- `backend/tests/unit/test_revision_intelligence.py`, `test_run_revision_fe_contract.py`, `backend/tests/agents/test_manifest_parity.py`, `test_revision_gating.py`, `test_banned_patterns.py`, `_scripted_model.py`, `tests/agents/characterization/golden/` inventory
- `frontend/src/components/layout/DashboardLayout.tsx` (375–467) — run_revision only for ppt/od_ppt; other revisions via run_pipeline
- `.planning/IMPLEMENTATION-REGISTER.md` Phase 13 entry; `.planning/ROADMAP.md` Phase 14; `backend/pyproject.toml` import-linter contracts; project memory notes (offline suite, defer-live, dev runtime)

### Secondary / Tertiary
- None needed — no external-ecosystem research applies to this brownfield wiring phase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; every component read directly
- Architecture: HIGH — dispatch path, chokepoint semantics, provider no-ops, and parity-trap interactions all verified line-by-line
- Pitfalls: HIGH for 1–8 (each anchored to a verified file:line); A1–A3 assumptions are the only soft spots

**Research date:** 2026-06-12
**Valid until:** branch-local — re-verify line numbers if `engine.py`/`websocket.py` change before planning executes (stable estimate: 30 days)
