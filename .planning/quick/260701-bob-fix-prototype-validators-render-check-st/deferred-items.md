# Deferred / Out-of-Scope Items — quick-260701-bob

## D1 — od_ppt (and prototype/od_prototype) characterization snapshots are local-env-sensitive to a runtime asset (PRE-EXISTING, not caused by this task)

**Symptom:** `tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot`
fails in the local working tree with a diff at index 3 (an `agent_input` whose
`context_message` gains a `=== TEMPLATE EXAMPLE (example.html): web-prototype ===`
block the committed golden lacks).

**Root cause (proven, NOT this task):**
- The block comes from `get_example_html("web-prototype")` reading the on-disk
  runtime asset `skills/opendesign/design-templates/web-prototype/example.html`.
- Reverting `render_check.py` + `static_check.py` to their pre-task (96dec5a9)
  content STILL fails od_ppt → this task's code is not the cause.
- Moving the asset aside flips the result: od_ppt PASSES but
  `test_characterization_prototype` + `test_characterization_od_prototype` then
  FAIL (they require the example). There is NO local asset-state where all 5
  goldens pass simultaneously — the goldens were recorded in a specific clean
  environment; the local `skills/` runtime assets diverge from it.
- (The earlier git-worktree "pass" at 96dec5a9 was misleading — worktrees are
  disconnected sandboxes in this repo per project memory `worktree-isolation-broken`.)

**Why out-of-scope:** This is a pre-existing environment discrepancy between the
committed characterization goldens and the local `skills/` runtime assets. It is
independent of the render_check / static_check / severity / engine changes in
quick-260701-bob. Per the executor SCOPE BOUNDARY, pre-existing failures in
unrelated files are logged, not fixed. Do NOT edit the golden and do NOT
SNAPSHOT_UPDATE (INV-3).

**INV-3 for THIS task is proven independently:** static_check + render_check raise
ZERO NEW issues on the 3 golden templates (test_nav_coverage scenario 8 +
test_static_check), and the goldens' event streams are unaffected by this task's
code (the only variable is the asset, not the code).

**Recommended follow-up (not this task):** reconcile the committed
characterization goldens with the current `skills/opendesign/design-templates/*`
runtime assets in a dedicated clean-env pass, or gate the example-injection in the
harness so the goldens are asset-independent.
