# Phase 44 — Deferred / Out-of-scope items

## From 44-05 (W3b run_revision retirement, Strategy A)

### DEF-44-05-1 — Pre-existing red: 3 mocked `ts-u.revisions` specs (harness drift)
- **Discovered:** running the flag-OFF mocked suite as the 44-05 gate.
- **Failing specs:** `TS-U-01` (od_ppt revise sends run_revision + renders revised deck),
  `TS-U-02` (revision run shows no clarify questionnaire), `TS-U-07` (user-story revise
  sends a `user_stories_revision` run_pipeline frame).
- **Verified pre-existing:** the same 3 fail IDENTICALLY on the pre-44-05 baseline
  (`1b06e122`) with the two 44-05 files reverted — so they are NOT caused by the
  run_revision REST rewire. The flag-OFF WS `run_revision` path is byte-identical to
  baseline, and `TS-U-07` (user-story revision) is untouched by 44-05 yet still red.
- **Root cause (characterised, not fixed):** harness/timing drift from the Phase 39/40
  UI redesign that absorbed the per-preview Revise bar into the settled run-lane composer.
  The revise composer renders (page snapshot shows the "Ask for a change or a follow-up…"
  placeholder + chat-send), but `mockWs.waitForClientFrame("run_revision" | "run_pipeline
  user_stories_revision")` times out — the settled-lane send seam no longer emits the frame
  the mock expects in the timing the spec asserts (`TS-U-07` shows a `run_pipeline` frame
  DID arrive, but with a different `pipeline_type`). Matches the known e2e-staleness note.
- **Owner:** W5 / 44-09 re-points the mocked harness to REST `/revisions` and reconciles
  these specs to the settled-lane composer send seam. Do NOT delete — reconcile.
- **Scope call:** out of scope for 44-05 (pre-existing, unrelated to the rewire; deviation
  scope-boundary rule — do not auto-fix pre-existing suite reds).
