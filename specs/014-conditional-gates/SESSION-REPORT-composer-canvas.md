# Session Report — Composer Canvas & Conditional Gates

**Date**: 2026-08-21
**Branch**: `feat/conditional-gates`
**Status**: **NOT STABLE** — see [Known issues](#known-issues) before building on this.

Work on the Composer's visual canvas (spec 014's R-22/R-23/R-24 surface) plus two
backend correctness fixes found along the way. Everything here is type-checked and
lint-clean; **none of it has been verified in a browser end to end**.

---

## 1. Backend correctness

### 1a. A blocking gate now stops the run (§8b)

`engine.py`'s pre-step gate loop treated `block` and `wait_human` as one `_halted`
flag whose only effect was `cursor += 1; continue`. A security/approval gate refusing
a step emitted `gate_blocked`, then the run **carried on through every downstream
step and finished as `pipeline_complete`** — a refused run was indistinguishable from
a clean pass at the run-status level.

`block` now takes the same single-terminal shape as the fan-out child-failure abort
(KRN-004): transition to `failed`, budget snapshot, one `pipeline_failed` naming the
blocked step, `return`. `wait_human` keeps the old skip-and-continue path — it is a
pause the human resolves, and a rejection there already arrives as `cancel`.

`_evaluate_gates` itself is unchanged, so `tests/agents/test_gates.py` (which asserts
on the outcome/event stream, not on run continuation) is unaffected.

### 1b. Tool grants are real, and now author-editable

The Composer's Tools tab was hardcoded on, with a comment claiming `write_files: false`
"never actually gated the native tools". That was **wrong**. Enforcement is complete:

```
compiler.py  → caps the grant onto Step.tools
factory.py   → permission_caps.denied_tools(ctx.step_tools)
runner       → unions that into the graph's excluded-tool set
```

`has_write_access` additionally drops the "How to deliver" write instruction from the
prompt. `read_files` / `write_files` are now live toggles threaded through
`StepSelection.tools` → `agentToManifestStep` → back on reload via
`manifestStepsToGateSelections`. Defaults stay read+write ON, so an untouched step
serialises byte-identically. `exec` stays fixed off — the untrusted cap zeroes it for
db-trust manifests, so a toggle would grant nothing.

---

## 2. Correctness fixes in the canvas

| Fix | What was wrong |
|---|---|
| Branch exclusivity | Both branches of a 2-way gate executed. `deriveDependsOn` auto-wired a chain `depends_on` onto route targets, so `_compute_is_leaf` (R-26) saw them as non-leaf regardless of which branch fired. |
| Blank canvas on New | `pipelineAgents` fell back to a hardcoded library template instead of `[]`. |
| "USER STORIES · Composer" | Three call sites trusted the shared mutable `workflowType`; ComposerPage only ever legitimately means `"custom"`, so all three are hardcoded. |
| Gate lost on reopen | `gates` lives on `selections`, not `AgentDef`, so a reopened manifest restored the route but showed the gate as Off. New `manifestStepsToGateSelections`. |
| Saved workflow opened in the wrong surface | `base_pipeline_type` is immutable after create (PATCH strips it), so a row stamped with a stale type could never be corrected. New `isComposerWorkflow()` routes on **manifest evidence** (`custom-agent` steps) with the stamped type as fallback — existing bad rows self-heal. |
| Workflow picker collapsed to a chevron | `WorkflowTargetPicker` still carried `w-0 min-w-0 flex-1` from when it lived in a flex row; in the rail's grid cell `flex-1` is inert and `w-0` collapses it to zero. |
| Picker showed literal "Rocket"/"Presentation" | `manifest.icon` is a **Lucide component name**, not an emoji. Now uses the shared `getWorkflowIcon()` resolver. |
| Rules-of-hooks violation | `useWorkflowPickerOptions` was called after the `!agent` early return in the rail, so clearing the selection changed hook order. |

---

## 3. The arrangement contract

Auto-arrange was index-based and produced a diagonal staircase with overlaps. It is
now an explicit contract, documented in `CanvasView.tsx`:

**Two axes.** Step→step is horizontal (180°); step→sub-agent is vertical (90°).

- **R1 — the spine is straight.** Every non-branch-target sits at row 0.
- **R2 — branch rows.** For `n` forward targets, stack one card apart
  (`top(i) = i·(cardH + ROW_GAP)`), then anchor:
  - odd `n` → middle target level with the source (`delta = row(S) − ((n−1)/2)·step`)
  - even `n` → stack centred (`delta = row(S) + cardH/2 − H/2`)

  Verified numerically for n = 1…6: always symmetric about the source, odd always puts
  exactly one target on the spine, adjacent cards never closer than `ROW_GAP`.
- **R3 — the sub-agent band.** Every fan starts at one shared Y below the lowest root
  node. Fans move down rather than columns spreading apart. With no branches every row
  is 0, so the band lands directly under the spine — no regression on a linear workflow.
- **R4 — column X.** `x(c+1) = x(c) + max(NODE_W + NODE_GAP, fanW(c) + fanW(c+1) + NODE_GAP)`.
  Collapses to uniform spacing when nothing has sub-agents.

**Equal-height cards.** All root cards are padded to the row's tallest natural height,
so "port at the card's centre" and "edge dead horizontal" stop being contradictory.

> **Incident.** The first attempt derived that min-height from `offsetHeight`, which
> reports the box *after* min-height applies — taller box → taller max → taller
> min-height, until React's update-depth limit tripped and the canvas white-screened.
> The measurement now sums the card's in-flow children (immune to the constraint) and
> a `MAX_REMEASURE` backstop makes any future layout loop degrade into a slightly-off
> diagram rather than a crash.

---

## 4. Edges

- **Forward route edges** use the same horizontal cubic as the blue structural edges —
  leave the diamond horizontally, enter the target's left horizontally.
- **Loops** (`loopArcPath`) leave the **top** of the source, crest above both nodes and
  drop into the **top** of the target, with vertical tangents at both ends. Side anchors
  dragged a back-edge straight through the main flow line. Staggered per loop index.
- **Dashed = conditional; colour = selection.** The dash carries the semantics, so route
  edges rest neutral and go amber only when an endpoint is selected — the same rule the
  structural edges already followed. Labels track the same state.
- **One incoming edge per node.** A route target no longer also receives a blue chain
  edge from its array neighbour, and a branching step draws no outgoing chain edge.
  Mirrors `deriveDependsOn`, so the drawing and the compiled graph agree.
- **Loop edges name their cap** — `dutch ↺5`.

---

## 5. Detached (orphan) steps

Removing a line used to silently re-join the target to whatever preceded it in the
array — an edge the author never drew, and one that also changed the saved
`depends_on`.

New authoring-only `AgentDef.detached`. A step is detached when **nothing feeds it**:
not nested, not first, and its chain predecessor branches away. Derived, not sticky —
losing a route does not orphan a step that still has a real predecessor, and deriving
also catches the mirror case a diff missed (turning a gate ON orphans its successor).

- Dashed amber border + an on-card banner.
- **Save is blocked** with a named message.
- Reconnect by pointing a route at it, or by dragging from any node's right circle
  onto the orphan — which moves it to sit immediately after that node. Position *is*
  the connection here, so no new edge field was needed.

**Never persisted.** Save refuses while any step carries the flag, so a saved manifest
can never contain one — the derive-from-position invariant for `depends_on` stays fully
intact on disk. No manifest change, no migration.

---

## 6. UI

- **Route editing is sidebar-only.** The drag-to-connect gesture, its outcome picker,
  the edge grab-band and the preview line were all removed rather than left unreachable.
- **Config rail**: Condition + Type on one row, Target full width beneath. Clicking a
  node's Gate chip or Route badge jumps the rail to Config.
- **One diamond**, replacing the circle in place, decorative. All route edges originate
  from that single point.
- **External workflow nodes** (R-22) — a `trigger: "workflow"` outcome now renders as a
  compact reference node (`(PPT) / Pitch an idea / DIVERTS RUN`), selectable and
  draggable. Deliberately **not** the target's inlined steps: that run is a separate
  `WorkflowRun` under `parent_run_id`, `self` would recurse, and the steps aren't
  editable from here.
- **`WorkflowPickerModal`** — replaces a `<select>` that could only render a string.
  Search, LibraryPage-style group chips (All / System / Revision / Yours) with live
  match counts, cards with icon + description + step count, fixed 520px list height,
  select-then-confirm, portalled to `document.body`.
  - **Revision pipelines are now offered.** They declare `user_launchable: false`, which
    means "not on the dashboard launcher" — but a trigger target always has a parent
    (`run_trigger_workflow` sets `parent_run_id_override`), and R-10 never restricted
    targets to launchable ids. Beta workflows stay excluded.
- **Dot grid** scales with zoom (power-of-two LOD, 12px floor) instead of staying a
  fixed screen texture; **zoom buttons** now compensate `pan` like the wheel already did,
  instead of zooming about the viewport's top-left corner.
- **Branch cap** raised 3 → 5. Frontend-only; the compiler never counts outcomes.

---

## Known issues

1. **Nothing here is browser-verified.** Type-check and lint only. This is the single
   biggest gap and should come before further feature work.
2. **`DashboardLayout.tsx:2313` is a type error** — `headerPage` maps `mainView === "settings"`
   to `"settings"`, but `AppHeader.currentPage` has no such member. This is an in-flight
   edit that is not part of this work; it will block a production build.
3. **Deleting a node that is a route *source* does not cascade** — its targets are not
   marked detached (that path runs through `onRemoveAgent`, not `handleRouteChange`).
4. **`ORIGINAL USER REQUEST` injection** (`engine.py`) — the brief is prepended to every
   step including those with their own authored prompt. Not changed: it needs a golden
   fixture regenerated (`sample_subagents_parallel.events.json` captures the literal
   string) and a live model run to judge. See `audit.md` §10a.
5. **Four `sample_conditional_*` fixtures not re-run** since the §6/`agent_skipped`/§8b
   fixes. See `audit.md` §10b.
6. **`target: "self"` is no longer selectable** — the picker's self row was removed as
   redundant with the saved-workflow entry. An outcome already saved with `self` shows
   nothing selected in the modal (the rail label still reads correctly).
7. **Loop cap is read-only** — surfaced from `RouteSpec.loop_max_iterations` (default 5,
   enforced at `engine.py:2996`) but not author-editable.
8. **~45 root-level PNG screenshots** were already staged and are included in this
   commit. They are QA debris, not deliverables, and can be dropped in a follow-up.

---

## Files

**Backend**: `agents/execution_engine/engine.py`, `specs/014-conditional-gates/audit.md`

**Frontend**: `composer/CanvasView.tsx`, `composer/CanvasNode.tsx`,
`composer/CanvasConfigRail.tsx`, `composer/ComposerPage.tsx`,
`composer/WorkflowPickerModal.tsx` *(new)*, `composer/treeLayout.ts`,
`store/api/userWorkflows.ts`, `layout/DashboardLayout.tsx`, `app/[...view]/page.tsx`,
`lib/api.ts`, `types/index.ts`, `workflow/AgentsPopup.tsx`
