---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
reviewed: 2026-06-09T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/agents/capabilities/strategies/task_loop.py
  - backend/agents/capabilities/strategies/single_shot.py
  - backend/agents/capabilities/registry.py
  - backend/agents/capabilities/deliverables/ppt.py
  - backend/agents/capabilities/deliverables/single_file.py
  - backend/agents/capabilities/deliverables/serialized_sandbox.py
  - backend/agents/capabilities/deliverables/streamed_text.py
  - backend/agents/capabilities/context_providers/opendesign.py
  - backend/agents/capabilities/context_providers/previous_run.py
  - backend/agents/capabilities/compaction/html_skeleton.py
  - backend/agents/capabilities/task_parsers/heading_tasks.py
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/od_context.py
findings:
  critical: 3
  warning: 4
  info: 3
  total: 10
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-09
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

This phase lifts the prototype-coupled engine behavior into registered capabilities
(strategies, deliverable resolvers, context providers, task parser, compaction) and
routes the engine through them by manifest name (SC-001 / INV-1). The structural
decoupling is clean — the registry seam, the deliverable resolvers, the task parser,
and the html_skeleton compaction are faithful, import-pure verbatim lifts, and the
previous_run ownership gate (L16) is correctly preserved and tested.

However, the **OpenDesign context provider is NOT a faithful lift of the legacy L12
injection branches**, and the divergences directly violate INV-3 (byte/semantic-event
parity) on a path the in-scope parity tests do not assert. Three independent behavioral
regressions are folded into `opendesign.py`:
1. the design-system instruction preamble is dropped from the injected block;
2. the example.html now leaks into the `tools:[]` planning agents (prototype-specify /
   prototype-plan), which the legacy code explicitly guarded against;
3. the build-task-2+ injection skip is lost, so the full DS + template + example are
   re-injected on every build task.

Because the offline `_drive` harness DOES seed `od_context` for prototype/od_prototype,
the first divergence changes the `agent_input.context_message` golden — meaning the
characterization snapshots (out of this review's file scope) must have been regenerated
to bake in the regression rather than catch it. These are the load-bearing SC-001
parity findings and are classified BLOCKER.

A secondary cluster: the `task_loop` strategy's internal fix-loop (`_run_validation_fix_loop`
+ the `run_fix_agent` contract) is dead on the live path but is the ONLY path the
`test_strategies.py` suite exercises — the tests validate dead code while the live
`KernelServices.run_validation_fix_loop` path goes unasserted by the strategy suite.

## Critical Issues

### CR-01: OpenDesign provider drops the design-system instruction preamble (INV-3 parity break)

**File:** `backend/agents/capabilities/context_providers/opendesign.py:53-58`
**Issue:** The legacy L12 design-system block (engine.py @ diff-base lines ~3327-3338)
injected an instruction preamble inside the block body:

```
=== ACTIVE DESIGN SYSTEM: {ds_id} ===
Apply these tokens to ALL colors, fonts, and spacing. Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.
{ds_body}
=== END ACTIVE DESIGN SYSTEM ===
```

The provider emits only `{ds_id: ds_body}` as the block content, so the generic injector
(`_compose_context_message`, engine.py:2940-2942) wraps it as
`=== ACTIVE DESIGN SYSTEM: {ds_id} ===\n{ds_body}\n=== END ...` — the entire "Apply these
tokens..." instruction line is **gone**. The `_drive` harness seeds `ds_body` for
prototype/od_prototype (`_scripted_model.py:500-504`), so this changes the
`agent_input.context_message` byte stream for every prototype agent — a direct INV-3
violation. If the characterization goldens pass, they were regenerated to accept the loss.

**Fix:** Restore the preamble inside the provider's block content so the composed message
is byte-identical:
```python
if include_ds:
    blocks[f"ACTIVE DESIGN SYSTEM: {ds_id}"] = (
        "Apply these tokens to ALL colors, fonts, and spacing. "
        "Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
        f"{ds_body}"
    )
```

### CR-02: example.html leaks into the `tools:[]` planning agents (behavioral regression + parity break)

**File:** `backend/agents/capabilities/context_providers/opendesign.py:67-74`
**Issue:** Legacy L12 gated the `TEMPLATE EXAMPLE (example.html)` block on
`_is_builder = bool(set(spec.tools) & {"prototype_emit_only", "prototype"})` — it was
injected ONLY for the build agent, with an explicit comment: *"Planning agents
(prototype-specify / prototype-plan, tools=[]) must NOT see a full working HTML doc — it
nudges them to copy/continue it instead of writing the spec / decomposing into tasks."*

The provider has no access to `spec.tools` and gates the example only on
`if template_body:`. `_compose_context_message` consults the provider for any agent that
declares `injects` (engine.py:2925-2926). `prototype-specify` and `prototype-plan` both
declare `injects: [template, design_system]` with `tools: []` (verified in their
AGENT.md), so they now receive the full example.html — the exact regression the legacy
gate prevented. This is both a behavior change and an INV-3 parity break. (It is masked
offline only when `web-prototype/example.html` is absent from the test env; it manifests
in production where the example exists.)

**Fix:** Re-introduce the builder gate. Pass the consuming `spec` (or its tool set) to the
provider via `ctx`/the runner handle and gate the example block on it, e.g.:
```python
spec_tools = set(getattr(getattr(ctx, "current_spec", None), "tools", []) or [])
is_builder = bool(spec_tools & {"prototype_emit_only", "prototype"})
...
if template_body:
    blocks[f"ACTIVE TEMPLATE (SKILL.md): {template_id}"] = template_body
    example_html = runner.template_example(template_id) if is_builder else None
    ...
```
The kernel must thread the current agent spec onto the context before invoking the
provider in `_compose_context_message`.

### CR-03: build-task-2+ injection skip is lost — full DS/template/example re-injected every task

**File:** `backend/agents/capabilities/context_providers/opendesign.py:50-79` and
`backend/agents/execution_engine/engine.py:2923-2942`
**Issue:** Legacy L12 computed `is_build_task_2_plus = (spec.id == "prototype-build" and
task_num_str not in ("", "1"))` and skipped the design-system body, the template body,
AND the example for build tasks 2+ (engine.py @ diff-base ~3326, ~3342). The whole point
of the html_skeleton compaction is that task 2+ receives the compact skeleton INSTEAD of
the growing full DS/template/example. The new provider path has no task-number awareness
and `_compose_context_message` runs the provider loop unconditionally whenever `injects`
is set, so on build task 2+ the full DS body + template body + example are re-injected on
top of the skeleton. This both diverges from legacy byte output (INV-3) and re-introduces
the O(n) prompt-growth the compaction was designed to remove.

**Fix:** Gate the DS/template/example composition on the build-task scratch. Either pass
`ectx.build_task_number` to the provider and skip the heavy blocks when it is not in
`("", "1")`, or have `_compose_context_message` suppress the provider blocks for the build
agent on task 2+ (mirroring the legacy `is_build_task_2_plus` predicate) so only the
strategy-injected skeleton rides through.

## Warnings

### WR-01: task_loop's internal fix-loop is dead on the live path but is the only path the strategy tests exercise

**File:** `backend/agents/capabilities/strategies/task_loop.py:288-302, 368-503`
**Issue:** On the live path `KernelServices` exposes `run_validation_fix_loop` (it
delegates to the engine's `_run_validation_fix_loop`), so the `hasattr(runner,
"run_validation_fix_loop")` branch (task_loop.py:288) is always taken and the strategy's
own `_run_validation_fix_loop` (lines 368-503) — which calls `runner.run_fix_agent` — is
never reached. `KernelServices` has NO `run_fix_agent` method (grep confirms it exists
only in task_loop and the test fake), so the fallback path would `AttributeError` if it
ever ran. The `test_strategies.py` `_FakeRunner` deliberately omits
`run_validation_fix_loop` and provides `run_fix_agent`, forcing every fix-loop assertion
(N=2 bound, attempt counting, fix-message wording) down the DEAD fallback path. The result
is a test suite that validates code the production engine never executes, while the live
`run_validation_fix_loop` wiring goes unasserted by the strategy suite.

**Fix:** Either (a) delete the dead `_run_validation_fix_loop` + the `run_fix_agent`
contract from task_loop (INV-12 — it is a second implementation of the fix-loop the engine
already owns), and update `test_strategies.py` to drive a fake that exposes
`run_validation_fix_loop`; or (b) if the fallback is intentional defensive code, add a test
where the fake exposes `run_validation_fix_loop` so the live branch is covered, and add
`run_fix_agent` to `KernelServices` so the fallback cannot `AttributeError`.

### WR-02: `_index_for` silently returns 0 for an unknown spec, masking a wiring bug

**File:** `backend/agents/execution_engine/kernel_services.py:289-293`
**Issue:** `_spec_for` raises a clear `RuntimeError` when the step's `agent_id` is not in
`ordered_agents`, but `_index_for` silently returns `0` if the spec is not found. Since
`_index_for` is only called with a spec already resolved by `_spec_for`, the miss path is
currently unreachable — but if the two ever drift (e.g. a synthesized step), index 0 would
silently route the wrong agent's identity into the `agent_start`/`agent_complete`
`index`/`total` fields, corrupting the UI ordering with no error. Defensive-but-silent
fallbacks of identity values are how parity bugs hide.

**Fix:** Mirror `_spec_for` — raise on a miss rather than returning 0:
```python
def _index_for(self, spec) -> int:
    for i, s in enumerate(self._ordered_agents):
        if s.id == spec.id:
            return i
    raise RuntimeError(f"KernelServices: spec {spec.id!r} not in ordered agents")
```

### WR-03: `_now()` formats differ between the kernel and the strategy — non-identical timestamps in parity-sensitive events

**File:** `backend/agents/capabilities/strategies/task_loop.py:81-83` vs
`backend/agents/execution_engine/engine.py:153-155`
**Issue:** The engine's `_now()` returns `datetime.now(timezone.utc).isoformat()` (e.g.
`2026-06-09T12:34:56.789012+00:00`), while task_loop's `_now()` returns
`time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())` (no microseconds, `Z` suffix). The
`task_loop_progress` event (task_loop.py:254-263) is emitted with the strategy's `_now()`,
whereas the legacy build loop's progress events used the engine's `_now()`. The `timestamp`
field is volatile and typically stripped from the characterization multiset, so this likely
does not break goldens — but it is a silent format divergence in a migrated event payload
that downstream consumers parsing the timestamp could trip on.

**Fix:** Have the strategy reach the kernel's timestamp helper through the runner handle
(e.g. expose `runner.now()`), or align the format exactly to the engine's
`datetime.now(timezone.utc).isoformat()`.

### WR-04: opendesign provider double-truncates the example (correct vs legacy, but fragile and undocumented)

**File:** `backend/agents/capabilities/context_providers/opendesign.py:70-74`
**Issue:** `runner.template_example` -> `engine._load_template_example` ->
`get_example_html(template_id)` already truncates to 8000 chars and appends
`"\n...[truncated]"` (od_context.py:154-155). The provider then slices `[:8000]` again and
appends `"...[truncated]"`. This happens to reproduce the legacy double-truncation
byte-for-byte (verified against diff-base engine.py ~3361-3363), so parity holds — but the
behavior is accidental, undocumented, and brittle: any change to `get_example_html`'s
truncation marker or `max_chars` silently desyncs the two layers. The `max_chars=8000`
magic number is duplicated across three sites (od_context.py, the runner fake, opendesign).

**Fix:** Document the intentional double-truncation with a comment referencing
`get_example_html`, or push truncation to a single owner (pass `max_chars` through the
handle so the provider does not re-truncate) and add a regression test pinning the
post-8000-char output byte string.

## Info

### IN-01: `model_catalog` vs `model` registry-kind mismatch in the `_KNOWN` comment

**File:** `backend/agents/capabilities/registry.py:44, 61`
**Issue:** The header comment (line 44) documents the data capability as `model: default`,
but the actual `_KNOWN` entry (line 61) is `("model_catalog", "default")`. The comment
mislabels the kind; a future reader resolving `("model", "default")` would hit a spurious
`KeyError`.

**Fix:** Update the line-44 comment to `model_catalog: default`.

### IN-02: `persist_task_html` swallows a missing-file as a no-op but logs nothing

**File:** `backend/agents/execution_engine/kernel_services.py:258-276`
**Issue:** When `sandbox.read("prototype.html")` returns falsy the method returns silently.
The legacy per-task dual-write skipped a missing file too, so this is parity-safe, but a
task that produced no HTML now leaves no trace at the dual-write site (the validation loop
does log a "wrote no prototype.html" warning, so the signal exists elsewhere). Consider a
`logger.debug` here for symmetry with the other best-effort sites.

**Fix:** Add `logger.debug("persist_task_html: no prototype.html for task %d — skipping", task_num)`
before the early return.

### IN-03: `_extract_task_title` is new behavior not present in the legacy lift

**File:** `backend/agents/capabilities/task_parsers/heading_tasks.py:71-85`
**Issue:** The module docstring states the parser is a "clean verbatim lift" of the engine's
two pure staticmethods (`_count_plan_tasks` + `_extract_task_block`). `_extract_task_title`
is a third, NEW helper with no legacy counterpart. It is non-load-bearing (the build prompt
uses `Task.body`, not `Task.title`), so parity holds, but the "verbatim lift" framing is
inaccurate and could mislead a future reviewer into assuming title parsing is also
characterized.

**Fix:** Adjust the docstring to note `_extract_task_title` / `Task.title` is new,
best-effort, and non-load-bearing (not part of the byte-identity contract).

---

_Reviewed: 2026-06-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
