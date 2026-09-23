# pdf_to_prototype — stabilization plan

Investigation of all 23 `pdf_to_prototype` / `_v2` runs (2026-09-02 → 2026-09-04),
DB `workflow_runs` + `run_events` + on-disk sandboxes under `runs/c6b9b61f-…/`.

## Outcomes

| outcome | runs | cause |
|---|---|---|
| completed | 1 | b80eff36 (v2, 50-screen doc set) |
| degraded, usable artifact | 2 | 5130337e, a786cc27 — review-loop cap |
| failed / cancelled: model auth | 12 | "The model rejected this request." = expired Bedrock bearer token, surfaced as a generic message; readers burn 5 × retries before anyone notices |
| failed: JSON task list | 3 | 0ebe5f41, c01479ba, 861db5e9 — plan-lead / review-planner narrated instead of emitting the ```json fence |
| cancelled after gate re-fire | 4 | c01479ba, 9432cf6c, 51c54b2d, 7e8a8e71 — every `run_resuming` re-opens an already-approved gate, sometimes two steps back |
| other cancelled | 1 | early cancel |

## Artifact defects on the runs that got far

| step | defect | evidence |
|---|---|---|
| journey-designer | declares screens MISSING that are fully documented in `synthesis.md` and `notes/doc-N.md` | 2ef8f6c8 MISSING=6; a786cc27 screens 5,6,7,8; the screen-6 checkbox loss in 5130337e traces here, not to the builder |
| story-layer | rewrites the draft from memory via `read_file → write_file`, truncating it | 7e8a8e71 v2=89 KB (11 sections/30 inputs) → v3=29 KB (1/0), prototype 2.4 KB; a786cc27 v2=66 KB → v3=19 KB (1/0); 5130337e lost 12 KB |
| review-verdict | decision is `bad` in 4/4 runs that reached it; flags cosmetic deviations (an extra `<h2>`, a fieldset legend) as defects while `review/r*.md` reports `SCREENS 2/2` | loop cap `loop_max_iterations=2` trips every time → `degraded` |
| review-revision | worker conflates the target-file `write_file` with the deliver-`.md` `write_file`, writes `screens/2_fixed.html` sidecar that nothing reads | a786cc27 pass 3 |
| plan-lead / review-planner / review-verdict | task list only reaches the engine via a ```json fence in the reply; `build/tasks.json` is ALSO written to disk but the parser never reads it | 3 runs died at 0 s with a perfect file on disk |
| story-layer (engine) | `_check_artifact_fallback` wrote the reply narration into `prototype.html`; the single-file readback then adopted it as the step output | fixed 2026-09-04 (engine + test) |
| FilesTab | "Build incomplete — No application code was written" rendered on any failed/degraded status, above a listed, validated `prototype.html` | `FilesTab.tsx:873` |

## Structural observations

- 15 steps, 5 human gates (journey-designer, plan-lead, shell-builder[before], structure-check, story-layer). Only 2 steps carry validators (plan-lead: `spec_plan_coverage`; assembler: `html_static`,`html_render`). The steps that lose the most content (journey-designer, story-layer, screen-builder) have **no deterministic check** between them and the next step — every gate is a human eyeballing prose.
- The review loop is a 5-step cycle with two independent caps of 2. One repair cycle + one recheck exhausts it.
- Names: `Story Layer & Presenter`, `Assembler & Wiring`, `Review Revision Router`, `Screen Builders` — compound, not verbs.

## Work items and agent assignment

Model tags are the pre-classification the dispatch rule requires. `[sonnet]` = needs
judgment (investigation, design, multi-file). `[haiku]` = mechanical, fully specified.

| id | item | owns | model |
|---|---|---|---|
| A1 | Deterministic artifact validators: `journeys_coverage`, `html_element_floor`, `fragment_field_coverage` + registry + tests. Proposal for yaml wiring. | `agents/capabilities/validators/*`, `agents/capabilities/registry.py`, new tests | [sonnet] senior |
| A2 | `json_tasks` reads `task_source.target` from the sandbox first, reply fence second + tests. Proposal for the one-line engine call site. | `agents/capabilities/task_parsers/json_tasks.py`, its test | [sonnet] senior |
| A3 | Resume re-opens approved gates / re-enters at the wrong step. Root-cause + fix + test. | `agents/execution_engine/engine.py`, `agents/capabilities/gates/*`, tests | [sonnet] senior |
| A4 | Pre-flight model-credential check at run launch + honest error text instead of "The model rejected this request." | `app/agents/model_factory.py`, `app/agents/llm_errors.py`, launch API path, tests | [sonnet] senior |
| A5 | FilesTab banner gated on deliverable absence, not status. | `frontend/src/components/results/FilesTab.tsx` + test | [haiku] junior |
| A6 | PROPOSAL: review loop — verdict severity split, revision write target, caps, router. | proposal file only | [sonnet] senior |
| A7 | PROPOSAL: self-validation blocks for every producing step (readers → assembler). | proposal file only | [sonnet] senior |
| A8 | PROPOSAL: short function-tied names; gate audit (which of the 5 human gates earn their keep once A1 validators exist). | proposal file only | [sonnet] senior |
| A10 | Mechanical `publish` step kind: runs NO model; engine copies the highest `draft.v*.html` to `prototype.html` and streams the file as the step's output. New step `publish` after `story-layer` (user request 2026-09-04: "copy the last draft into prototype.html and stream the file. That's it."). Story-layer becomes validate-only. | `agents/workflows/plan.py`, `agents/workflows/compiler.py`, new `agents/capabilities/publish_step.py`, tests; PROPOSAL for the engine dispatch hook | [sonnet] senior |
| A9 | Integrate A6/A7/A8/A1/A2/A10 proposals into `workflow.yaml` + engine hook lines; compile; run the workflow test file. Runs after A1–A8, A10. | `workflow.yaml`, engine hook lines | [sonnet] senior |

File ownership is exclusive. Nobody edits `workflow.yaml` except A9.
Proposals go to `/Users/bilala/.claude/jobs/c4e98527/tmp/proposals/<id>.md`.
