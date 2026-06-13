# Live + Playwright Verification Campaign — Phases 16–19 (2026-06-13)

**Mandate (user):** after fixing the deep-investigation backlog via GSD phases, run a live + Playwright pass on the `default` Bedrock profile — visually confirm every FE-affecting fix and close the deferred live re-confirms. "check each and every detail."

**Environment (verified ready):**
- Backend `:8000` — restarted fresh (the previous process was stale, started 09:44 before Phases 16–19); now loads Phase 16–19 code (engine error-arm/cancel/chunk-sanitizer, deliverable mimetype, api_prefix validator). `AWS_PROFILE=default` (acct 473293451041, DS_Admin), Bedrock Haiku 4.5 eu-central-1, alembic=0020, 🟢 ready. Live Bedrock smoke: **OK** (direct converse, 17 tok).
- FE `:3000` — `next dev` (hot-reloads the Phase 16/18 FE code on request).
- Harnesses: `/tmp/flowin-ui-driver.py` v2, `/tmp/flowin-ui-launcher.py` (sample/fanout/ui_custom_proto admission), `/tmp/wave_panel_probe.py`. Fixtures present (ui_custom_proto 5 agents, sample_wave, sc001_fanout).

## Verification matrix (the Phase 16–19 fixes to confirm live/visually)

| # | Fix | What to confirm | Verdict |
|---|-----|-----------------|---------|
| V1 | ISS-019 (P18) wave-fold | "WAVE / SUBAGENT TREE" heading visible at 1440×950 without scroll | **PASS** — heading y=884, bottom 900 ≤ 950 (was 963); empty-state visible in-viewport. Probe `/tmp/flowin-ui-evidence/S09-sample_wave/probe-fullpage.png` |
| V2 | ISS-021 (P18) custom HTML deliverable | a custom/unknown-type HTML deliverable renders in a sandboxed iframe (Preview) | **PASS (live)** — `ui_custom_proto` ran end-to-end (fanout+gate+build, 190s, $0.17); `pipeline_complete.deliverable_mimetype=text/html`; Preview shows the live HTML ("Habit Tracker" app) in a **"Deliverable Preview" iframe** (generic renderer). `07-preview.png` |
| V3 | ISS-017 (P16) degraded affordance | a terminal-empty/failed run shows the degraded panel (not "Output will appear here") | pending |
| V4 | ISS-007 (P16) cancel delivery | real Stop → `pipeline_cancelled` on the wire → in-flight agent card clears | **PASS (live)** — real Stop click; `terminal=pipeline_cancelled` **delivered to the FE wire** (count 1); after-cancel agent badges `[]` (no stuck RUNNING); header "Pipeline stopped". Closes ISS-002 too. `11-after-cancel.png` |
| V5 | ISS-008/009 (P16) reconnect | mid-run reload → replay rebuilds panels (revision section faithful) | **PASS (live, partial)** — mid-run reload → **`pipeline_reconnected` fired** with the full contract (`live`, `replayed_through_seq`, `status` all present; `live=False` since the run finished by reconnect time). ISS-009's "always set `live` explicitly" confirmed in the ack; the specific `live:true` value + ISS-008 revision-`section` are offline-proven (cluster-B tests, sample_wave isn't a revision) |
| V6 | ISS-014 (P18) composer | the dead capability-palette composer is gone; the live agent-composer still works | **PASS** — `WorkflowComposer.tsx` + `CapabilityPalette.tsx` deleted (0 imports; 3 grep hits are explanatory comments; tsc clean); live `AgentsPopup` composer renders ("Workflow configuration / Agents / Skills & Hooks / + Add agent") **with the relocated "PER-AGENT MODEL" picker** (MODEL-03 live). `02-agent-composer.png` |
| V7 | ISS-004/005/006 (P19) live re-confirm | ONE live app_builder run | **ISS-005 ✅ LIVE** (infra-generator `/api/v1`×6, 0 bare-`/api/` violations — was 0× pre-fix); **ISS-006 ✅ LIVE** (`getDatabase`×8, `getDb`×0 — TS2305 gone); **ISS-004 = offline-proven** (the 25-min driver timeout closed the browser before `app-sdlc-governance` ran — the disconnect-cancel that ended the run incidentally re-confirmed ISS-007's keep-destructive-cancel-on-disconnect; the chunk-sanitizer + prompt fix are deterministically offline-proven). 11/15 agents ran ($~2) |
| V3/V8 | ISS-016/017 (P16) model-error → pipeline_failed + degraded affordance | a model error → `pipeline_failed` (not empty success) + FE degraded panel | **PASS (live, on the original trigger)** — ran a `user_stories` pipeline on a **srini-backed backend** (every Bedrock call → the exact `ValidationException: Operation not allowed` that spawned ISS-016). Backend: each agent "runner surfaced an error event — marking failed (no completion)" → **6 `agent_error` / 0 `agent_complete`** → `terminal=pipeline_failed`. FE (`06-terminal.png`): 6× **ERROR** badges, per-agent sanitized *"The model rejected this request."* (WR-02 — raw exception server-side only), and a **"This run did not complete successfully"** degraded panel with the FAILED-AGENTS list + "View details / retry" — NOT the pre-fix DONE-badges + empty "Output will appear here". |
| B  | Baselines (regression) | pipelines render post-16/18 | **PASS** — user_stories questionnaire + agent panels (V1), the full SC-001 custom pipeline fanout+gate+build (V2), app_builder 11 agents (V7), cancel/reconnect (V4/V5) all rendered + behaved correctly on the Phase 16–19 code |

## Verdict

**Every Phase 16–19 fix confirmed — 8 live (incl. the major ISS-016 on its original trigger) + 1 offline:**

- **Live + visually confirmed (8):** ISS-016 (model-error → `pipeline_failed`, 6 agent_error/0 agent_complete, on the srini `ValidationException`) + ISS-017 (degraded "did not complete successfully" panel + FAILED-AGENTS + retry; WR-02 sanitized text); ISS-021 (custom HTML in the generic "Deliverable Preview" iframe — the headline); ISS-007/002 (cancel ack on the wire + cards clear); ISS-019 (wave-fold above the fold); ISS-014 (composer deleted + relocated model picker); ISS-005 (infra `/api/v1`×6, 0 violations); ISS-006 (`getDatabase`×8, no `getDb`).
- **Live mechanism + offline-backed (1):** ISS-008/009 (reconnect/`pipeline_reconnected` contract live; revision-`section`/`live:true` offline cluster-B tests).
- **Offline fault-injection proven (1):** ISS-004 — `app-sdlc-governance` is deep in the 15-agent app_builder sequence (didn't reach before the 25-min driver timeout) and produces no chunks on the srini failure path; the chunk-sanitizer split-XML fault-injection + the P15 prompt fix are deterministic offline proof.

No product defect surfaced in the live pass. The one snag was a **harness** gap (the SC-001 `ui_custom_proto` manifest had been removed from the tree to keep it ship-clean; temporarily reinstalled for V2, removed at campaign end). Real Bedrock spend ~$3–4 across V2/V4/V5/V7 on `default` (acct 473293451041).

## Results

### V1 · ISS-019 wave-fold — PASS (2026-06-13)
`/tmp/wave_panel_probe.py` at 1440×950 → `headingInfo: {y:884, h:16, visible:true}`, `bodyScrollH==viewportH==950` (no page overflow). The "WAVE / SUBAGENT TREE" heading + "No waves running." empty state are rendered within the viewport (bottom 900 ≤ 950), vs the pre-fix y=963 (~13px below the fold). The P18 flex-budget split (column `flex flex-col overflow-hidden`; agent wrapper `flex-1 min-h-0`; wave wrapper `flex-shrink-0 max-h-[40%]`) is confirmed live. Populated-wave groups scroll within the panel's `max-h-[40%]` (not captured here — the probe stalled at the questionnaire; the layout claim is the heading position, which holds).

*(Remaining scenarios run next.)*
