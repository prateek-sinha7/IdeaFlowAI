---
slug: parallel-subagents-no-html
status: diagnosed
trigger: |
  DATA_START
  User custom workflow "Parallel Sub-agents Test" (workflow id
  76840113-63aa-4828-a6e6-93dd62b61f42) has not produced `output.html` as its
  deliverable in any of the last 10 runs, despite the manifest declaring
  deliverable {strategy: streamed_text, name: output.html}. User: "I am using
  parallel-group to execute group of agents and then get the output to page
  builder and it generates html which it's not doing."
  DATA_END
created: 2026-08-13
updated: 2026-08-13
tdd_mode: false
goal: find_root_cause (diagnosis only — no fix authorized)
classification: config/design mismatch — streamed_text deliverable vs custom-agent write_file delivery instruction; NOT a parallel_group defect
---

# Parallel Sub-agents Test — no `output.html` deliverable

## Verdict

- **Root cause [CONFIRMED]**: the workflow's deliverable strategy is `streamed_text`, but the
  factory's custom-agent prompt composition (`backend/agents/factory.py:558,570-573`) tells the
  final "Page Builder" agent to deliver its answer via `write_file` to
  `1krppp8-wrx4z0-<topic>.md` — because `_deliverable_filename_override`
  (`backend/agents/execution_engine/engine.py:3324-3329`) applies the declared deliverable name
  **only when strategy == `single_file`**. The HTML therefore lands in a machine-named `.md`
  sandbox file, while the `streamed_text` resolver
  (`backend/agents/capabilities/deliverables/streamed_text.py:46-48`) returns the agent's
  *streamed* text (`ctx.last_streamed`) — which is prose, not the HTML. `output.html` is never
  created anywhere, by design of this combination.
- **The parallel machinery is innocent [RULED-OUT]**: run logs show all three children started
  in the same second and the parent ran strictly after them; `parallel_group` + `run_fanout`
  worked exactly as designed on every inspected run.
- **Smoking gun [REPRODUCED]**: run `79a00392` — the parent produced a complete, valid
  `<!DOCTYPE html>` page… inside `1krppp8-wrx4z0-run.md` (59 lines, closes with `</html>`),
  written by the model's own `write_file` (zero `artifact_fallback` events for that step). The
  workflow *did* generate HTML; the deliverable path never looks at it.
- **This combination is the composer's DEFAULT [CONFIRMED]**: "Reset to default" in the composer
  hardcodes `{strategy: "streamed_text", name: "output.html"}`
  (`frontend/src/components/workflow/composer/CanvasView.tsx:881`), and the format picker offers
  `.html` under `streamed_text` (`CanvasView.tsx:503-506`). The user did not mis-configure; the
  default is the broken combination.
- **Recommended fix**: short-term, switch the workflow's deliverable to
  `{strategy: single_file, name: output.html}` (exactly what the working
  `sample_subagents_parallel` template uses). Root fix: make the factory's "How to deliver"
  block strategy-aware, and stop the composer offering `.html` under `streamed_text` (or map it
  to `single_file`).

## Symptoms

- **Expected**: each run ends with an `output.html` deliverable containing the page the
  "Page Builder" parent assembles from three parallel joke-writer children.
- **Actual**: no `output.html` in any run sandbox; the deliverable surfaced to the user is
  non-HTML text. User's phrasing: "it generates html which it's not doing."
- **Exact error**: none — no step fails, no exception; every run completes green. The failure is
  silent content misrouting. [CONFIRMED]
- **Reproduction**: launch workflow `76840113-…` with any brief. All 10 sandboxes under
  `backend/runs/0da2ba7c-af98-4bad-8ae0-e1bf04957a10/` show the same shape [REPRODUCED]:
  - three child artifacts `1krppp8-{a3y2rn,vzlay3,gai0pd}-<topic>.md` (jokes)
  - one parent artifact `1krppp8-wrx4z0-<topic>.md` (sometimes full HTML, sometimes confused
    markdown)
  - **no `output.html`, ever**
- **Timeline**: consistent across all runs on disk (Aug 13, 01:04–12:09). Never worked — this is
  a wrong-combination-from-day-one, not a regression. [CONFIRMED]

### Run-log evidence (run `bcebf499`, `.logs/run-logs.jsonl`) [REPRODUCED]

```
10:03:31 step_start custom-agent:1krppp8-gai0pd   ┐
10:03:31 step_start custom-agent:1krppp8-vzlay3   ├ all three children, same second → parallel OK
10:03:31 step_start custom-agent:1krppp8-a3y2rn   ┘
10:05:44–10:07:37 three step_end events (children)
10:07:37 step_start custom-agent:1krppp8-wrx4z0   ← parent runs LAST, after all children
10:08:55 step_end   custom-agent:1krppp8-wrx4z0
```

## Prior art

| ID | Relationship | What it tells us |
|---|---|---|
| `ISSUES-subagents-strategies.md` (repo root, uncommitted) [HISTORY] | Sibling investigation of `sample_subagents` | Defect #1: the injected "Write your deliverable to `X`" line dominates weak models' output (since mitigated by the headed "## How to deliver" block, `factory.py:564-573`). Defect #4: `_check_artifact_fallback` ignored `deliverable_filename_override` — same family of "prompted filename vs resolved filename disagree"; the working tree now threads `deliverable_filename` into the fallback (`engine.py:4523`). This bug is the *third* member of that family. |
| ADR-0009 [HISTORY] | Background | `mode: parallel` used to be decorative; `parallel_group` (new, this branch) is the fix. Confirms the parallel dispatch path is new but here it works. |
| FIX-110 [HISTORY] | Same symptom class | "Custom workflow with prototype agents shows validator QA text (output.md) instead of HTML" — deliverable content misrouted for a custom workflow. |
| FIX-113 [HISTORY] | Adjacent | ComposerPage.handleRunOnce never injected the `__deliverable__` override — composer↔deliverable plumbing has broken before. |
| FIX-016 / FIX-017 / FIX-058 [HISTORY] | Adjacent | Prior "no HTML deck / HTML deliverable from custom workflow" fixes; establishes the pattern that deliverable-shape mismatches surface as "no HTML". |
| `sample_subagents_parallel/workflow.yaml` [HISTORY] | The working reference this workflow copies | Uses `deliverable: {strategy: single_file, name: page.html}` and parent `spawn_subagents: true`. The custom workflow diverges on **both**; only the deliverable divergence matters (see H1). |

## Hypotheses

| # | Hypothesis | Status | Killing/confirming evidence |
|---|---|---|---|
| H1 | Parent's `spawn_subagents: false` (vs `true` in the sample) blocks child spawning | **[RULED-OUT]** | The compiler wires `parallel_group` purely from the `subagents: {mode: parallel}` block (`compiler.py:654-685`); the `spawn_subagents` *tool* flag only controls binding the model-facing request-emitter tool (`factory.py:960-965`) and is engineer-only for user manifests (`compiler.py:832-841`) — which is *why* it is false here. Run logs prove all three children spawned and ran concurrently. |
| H2 | Fan-out result ordering makes `last_streamed` a child's joke instead of the parent's output | **[RULED-OUT]** | `parallel_group` is strictly two-phase: children via `run_fanout`, then the parent via `run_agent` (`parallel_group.py:189-194`). Run logs show parent `step_start` after every child `step_end`; the parent's result is appended last (`engine.py:4542`), so `results[-1]` at `engine.py:2811` is the parent. |
| H3 | `streamed_text` deliverable vs the factory's unconditional `write_file` delivery instruction — the HTML goes to a file the resolver never reads | **[CONFIRMED — root cause]** | Code path: `engine.py:3324-3329` (override only for `single_file`) → `factory.py:558` (falls back to `artifact_name(instance_id, topic)` = `1krppp8-wrx4z0-<topic>.md`) → `factory.py:570-573` ("Call `write_file` with path `{filename}`. Its content is your answer"). Disk: run `79a00392` has a complete valid HTML page inside `1krppp8-wrx4z0-run.md` and no `artifact_fallback` event (model wrote it itself); no `output.html` in any of 10 sandboxes. Resolver: `streamed_text.py:46-48` reads only `ctx.last_streamed`. |
| H4 | The parent model simply fails to write HTML (model quality) | **[RULED-OUT as root cause]** | Run `79a00392` is the counterexample: the model produced perfect HTML and the deliverable still wasn't it. Model quality is a real *secondary* noise source (run `bcebf499`'s parent emitted a markdown doc about "persistence conventions" — child artifacts + the file-delivery instruction pull it off the "output ONLY HTML" prompt), but it cannot explain 10/10 failure. |
| H5 | `write_files: true` on the parent conflicts with streamed delivery | Subsumed by H3 | Not an independent cause: the conflict is created by the factory *instructing* the write, not by the permission existing. |

## Root cause

**Defect**: `backend/agents/execution_engine/engine.py:3324-3329` (`_deliverable_filename_override`)
returns the declared deliverable name only when `deliverable.strategy == "single_file"`; combined
with `backend/agents/factory.py:558,570-573`, every final custom-agent step under a
`streamed_text` workflow is instructed to deliver its answer through `write_file` into
`artifact_name(instance_id, topic)` — a `.md` file the `streamed_text` resolver never reads.

**Mechanism chain** [CONFIRMED end-to-end]:

1. Composer default run config is `{strategy: streamed_text, name: output.html}`
   (`CanvasView.tsx:881`); the saved workflow carries it.
2. At run time the engine passes `deliverable_filename_override=None` for a non-`single_file`
   strategy (`engine.py:3326-3328`).
3. The factory therefore appends `## How to deliver — Call write_file with path
   `1krppp8-wrx4z0-<topic>.md`. Its content is your answer` (`factory.py:558,570-573`), directly
   contradicting the step's own prompt ("Output ONLY valid HTML… the literal HTML tags ARE the
   file content").
4. The model obeys the delivery block: the HTML goes into the `.md` sandbox artifact via
   `write_file`; the streamed channel carries prose/confirmation (tool-call arguments are not
   streamed text).
5. Deliverable resolution: `engine.py:2811` sets `ectx.last_streamed = results[-1]["output"]`
   (the parent's streamed prose); `StreamedTextResolver.resolve` returns it. The user is shown
   that prose under the name `output.html`. No file named `output.html` ever exists.

**Why it wasn't caught**:
- The only exercised parent+subagents workflow (`sample_subagents_parallel`) uses `single_file` —
  the one strategy for which the override fires. No test or sample covers
  `streamed_text` + custom-agent final step. [CONFIRMED by absence: no such test found]
- The composer UI validates nothing here — it actively offers `.html` under `streamed_text`
  (`CanvasView.tsx:503-506`) and resets to that combination.
- Nothing fails loudly: every step succeeds, the deliverable resolves to a non-empty string, the
  run completes green. Silent-misrouting, the same failure texture as
  `ISSUES-subagents-strategies.md` defect #4.

## Blast radius

- **Every composer-built custom workflow using the default deliverable** (`streamed_text`) has
  the same split-brain: the final agent is told to put its answer in a file while the deliverable
  is read from the stream. Markdown workflows often *appear* to work only when the model happens
  to also stream its answer — deliverable quality is model-mood-dependent. [LIKELY — verified for
  this workflow; other custom workflows inferred from the shared code path]
- `.html` deliverables are the worst-hit because the prose is unrenderable as a page; `.md` names
  merely degrade. [LIKELY]
- Mimetype: `streamed_text.default_mimetype` maps to `text/markdown` regardless of an `.html`
  name (`_mimetype.py` via `streamed_text.py:41-44`) — so even a streamed HTML answer would be
  presented as markdown. Second, independent reason `streamed_text`+`.html` cannot work. [CONFIRMED
  in code, not exercised live — no run ever streamed HTML]
- Non-final custom-agent steps are unaffected (they are *supposed* to write
  `instance-topic.md`). `single_file` and `serialized_sandbox` workflows unaffected. [CONFIRMED]

## Recommended fix

1. **Immediate (config, zero code)**: edit the workflow's deliverable to
   `{strategy: "single_file", name: "output.html"}`. Then `_deliverable_filename_override` fires,
   the parent's prompt says "write output.html", and the `single_file` resolver reads exactly
   that file back — byte-for-byte the working `sample_subagents_parallel` pattern. Risk: none.
2. **Root fix (backend, small)**: make the factory's "How to deliver" block strategy-aware — for
   a final step under `streamed_text`, instruct "your streamed reply IS the deliverable; do not
   write a file", instead of injecting a `write_file` path. Requires threading the deliverable
   strategy (or a `deliver_via_stream` bool) into `AgentContext` alongside the existing override.
   Risk: `tests/agents/test_skill_prompt_baseline.py` pins the composed prompt byte-for-byte —
   goldens will need regeneration; do not break the headed-block form (ISSUES defect #1 showed a
   bare trailing sentence gets echoed as output). Must not violate INV-5 (no new manifest keys)
   — this is engine→factory plumbing only.
3. **Composer guard (frontend, small)**: drop `.html` from `FORMAT_OPTIONS.streamed_text`
   (`CanvasView.tsx:503-506`) or auto-switch strategy to `single_file` when `.html` is chosen,
   and change the reset default (`CanvasView.tsx:881`) to a coherent pair.
4. Optional belt-and-braces: teach `_check_artifact_fallback` / deliverable resolution to warn
   when a `streamed_text` deliverable named `*.html` resolves to text with no `<html` in it —
   turns the silent failure loud.

## Verification plan

- **Fails now**: launch the workflow as configured → assert a file named `output.html` exists in
  the run sandbox and the deliverable body starts with `<!DOCTYPE html>`. Both fail today.
- **Passes after fix 1**: same assertion with `single_file`/`output.html` config.
- **Unit (for fix 2)**: compose the prompt for a final custom-agent step with
  `deliverable.strategy == "streamed_text"` and assert the "How to deliver" block contains no
  `write_file` path; with `single_file` assert it names the declared file (existing behavior).
- **Regression**: `python3.11 -m pytest tests/agents/ tests/unit/` — especially
  `test_skill_prompt_baseline.py`, `test_compiler_subagents.py`, and the 17 golden
  characterization tests, which must stay green (INV-3).

## Open questions

- **[OPEN]** What the DB-persisted deliverable blob actually contains for these 10 runs
  (`agent_outputs` / deliverable column) — inferred from code path, not read back from Postgres.
  Would confirm the exact prose the user saw. Resolve: query the runs table for run
  `bcebf499-…`'s deliverable.
- **[OPEN]** Whether any composer-built `streamed_text`/`output.md` workflow in production is
  currently returning file-write confirmations instead of content (blast-radius bullet 1).
  Resolve: sample recent custom runs' deliverables for tool-confirmation-shaped text.
- **[ASSUMED]** The 10 sandboxes under user `0da2ba7c-…` are the user's 10 failing runs (they
  match the manifest's instance ids `1krppp8-*` and the described shape exactly; the workflow id
  itself is not stored in the sandbox).
