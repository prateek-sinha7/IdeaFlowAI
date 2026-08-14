# Spec 012 — bugs (fixed)

Every defect found and fixed while getting composed (custom) workflows to run correctly
under this spec: the `custom-agent` template, the `parallel_group` strategy, prompt
composition, and the manifest save/resume paths it introduced.

Tracked here, not in `.planning/FIX-REGISTER.md` — that register is for issues reported
through Jira and then fixed. Everything below was found directly while implementing and
live-testing this spec, with no Jira ticket behind it. See `issues.md` in this same
folder for the defects that were **not** fixed (WONTFIX / BY DESIGN / DEFERRED / NOT
REPRODUCED).

**IDs are `SPEC012-BUG-NN`, stable and sequential — cite these, not the `Ref` column.**
`Ref` is the letter used in the source investigation this item came from, kept only so
the file:line evidence in those documents stays findable.

Sources:
- [reports/outstanding-bugs.md](reports/outstanding-bugs.md) — the custom-workflow
  prompt-contract session (2026-08-13), refs **A**–**O**
- [reports/composer-ui-findings.md](reports/composer-ui-findings.md) — Composer UI sweep,
  refs **P**–**S**
- [reports/sample-subagents-findings.md](reports/sample-subagents-findings.md) — live
  `sample_subagents` run findings, refs **T**–**W**

---

| ID | Ref | Defect | Root Cause | Fix | Blast Radius |
|---|---|---|---|---|---|
| **SPEC012-BUG-01** | 0 | No `output.html` produced across 10 runs | `streamed_text` deliverable ignores the declared `name` — only `single_file` honours it | DB manifest config: `streamed_text` → `single_file` | Config-only. 12+ subsequent runs produce it; byte-verified on run `44bb9a9d` |
| **SPEC012-BUG-02** | D, D2 | `planner: skip` still rendered a fabricated `## Planning Context` block, echoing the brief | `_compose_context_message` rendered the block whenever a context dict existed, regardless of whether a planner produced it | Gate on `planner_ran is False AND step.prompt` in `engine.py` | Registry pipelines (0 steps declare `prompt`) unaffected — `PLAN-KEPT` verified on ppt/od_prototype×2/prototype_revision, goldens byte-identical. (D2: an initial claim that the fix was bypassed on 3 of 5 paths was investigated and withdrawn — `_rehydrate_planning_context` has exactly one caller, which stamps the flag right after. Shipped as a rename, `planner_skipped` → `planner_ran: False`, no behavioural change) |
| **SPEC012-BUG-03** | B1, B2 | Parallel children got `Task N of M` with no task list; block leaked to parent + every later step | `run_worker` numbered every worker unconditionally; `parallel_group` sends `input=""` by design | `kernel_services.py`: `task_number` only set when the worker carries task text | Bottle run: all 5 agents clean; `prototype-build`'s legitimate `Task i/N` unaffected |
| **SPEC012-BUG-04** | J | Sequential composed steps had no handoff mechanism — only parallel parents got a roster | Compiler only synthesizes `depends_on` for `subagents:` nesting | `depends_on` derived from position at serialise time (`userWorkflows.ts`), emitted on every step | Live-verified twice (`fan`, `glasses`) — Writer's prompt names Brief Builder correctly |
| **SPEC012-BUG-05** | O | Roster told a sequential step its predecessor was a "sub-agent" | Wording predates `depends_on` covering peers | String only: `"Earlier steps produced:"` | None — string change, 3 assertions updated |
| **SPEC012-BUG-06** | E, M | 4 Canvas tool-grant toggles the runtime can't honour; 2 could make a workflow unsaveable | `write_files`/`read_files` don't gate the native tools; `exec`/`spawn_subagents` rejected by the compiler for `db`-trust manifests | Grants fixed (ADR-0012): `read_files`/`write_files` always `true`, `exec`/`spawn_subagents` removed from palette | Frontend only; no manifest flag changed runtime behaviour |
| **SPEC012-BUG-07** | F | `CLAUDE.md` claimed `task` tool "always excluded" — true of tool, false of prompt | `SubAgentMiddleware` injects `TASK_SYSTEM_PROMPT` independent of tool binding | Doc corrected with a callout naming the mechanism + removal path | Docs only |
| **SPEC012-BUG-08** | — | Resumed composed runs reported every step as "Custom Agent", losing composer names | `execute()` overlays `display_name`; `resume_run()`/`_derive_offset()` didn't | New `_specs_from_plan()` helper, all 3 call sites now share it | Fresh-run path untouched (straight extraction); proved offline against the real `sample_subagents` manifest |
| **SPEC012-BUG-09** | K | A manifest whose DAG can't compile could be saved with a 200 | `POST`/`PATCH` validated structure only, never compiled | `_compile_check_manifest` hands it to the real compiler at `trust="db"` | **NOT YET VERIFIED** — 4 tests written, never run |
| **SPEC012-BUG-10** | P | Sub-agent wiring never reached `ComposerPage` — "+ Sub-agent" always minted a blank node | `ComposerPage.tsx` never passed `onRequestAddSubAgent`/`onAddAsSubAgent` down to `CanvasView`/`AgentLibrary` | Wired the props through | Frontend only, e2e-verified (`composer-subagents.spec.ts`) |
| **SPEC012-BUG-11** | Q | Simple view silently hid sub-agents | Same investigation, task 2 | — | Frontend only |
| **SPEC012-BUG-12** | R | **DATA LOSS** — reloading a saved custom workflow dropped the entire sub-agent tree | Task 2, flagged "CHECK THIS" in the source report | — | Frontend only — the most serious item in this file: silent data loss |
| **SPEC012-BUG-13** | S | Canvas rename pencil unclickable — sat under the remove (×) button | `CanvasNode.tsx`: absolute-positioned × button overlapped the pencil's hit area for short names | Added `pr-6` to reserve the strip | One CSS class; reverting it reproduces the timeout (confirmed) |
| **SPEC012-BUG-14** | T | Delivery instruction echoed back as a leaf agent's entire output (e.g. `joke-mountain.md` contained the instruction, not a joke) | Bare trailing sentence read by the model as content, not meta-instruction | `factory.py`: headed `## How to deliver` block + explicit "never this instruction" | Same failure family as `issues.md`'s **SPEC012-ISSUE-02**, distinct manifestation. Verified fixed in current source |
| **SPEC012-BUG-15** | U | `tool_call`/`tool_result` pairing in `agent_outputs` was LIFO not FIFO — misattributed results between same-named calls | `run_commands.py` matched by tool name only, walked newest-first | Walks oldest-unresolved-first; the fix comment names the bug verbatim | Verified fixed in current source. Corrupted the only API-visible tool-call audit trail for custom workflows |
| **SPEC012-BUG-16** | V | Stale dot-separated filename example in a step prompt contradicted the real hyphen convention (ADR-0007) | Prompt authored before ADR-0007's hyphen fix | `workflow.yaml`'s example now hyphenated | Verified fixed in current source. Recovered via `glob` on Bedrock Haiku; would have hard-failed on the small-model target ADR-0007 was written for |
| **SPEC012-BUG-17** | W | Artifact-fallback safety net ignored `deliverable_filename_override`, writing a duplicate file for the deliverable-producing step | `_check_artifact_fallback` hardcoded `artifact_name(...)`, never checked the override the prompt composer already used | New `deliverable_filename` param, defaults to override | Verified fixed in current source. Worse-case (fallback targeting the wrong file entirely) was reasoned but not reproduced live |

---

## Jira cross-reference

Checked 2026-08-13 against the full `KAN` bug list (87 bugs, `KAN-62`–`KAN-170`). **None of
the above duplicate an existing Jira ticket** — nothing about `custom-agent` template
naming, the resume display-name bug, tool_call LIFO/FIFO, the delivery-block echo, DAG
validation at save, or the Composer sub-agent tree wiring appears anywhere in Jira.

Four tickets are adjacent (same failure family, different specific defect — not
duplicates):

| Jira | Title | Relation |
|---|---|---|
| [KAN-112](https://velocityai-hex.atlassian.net/browse/KAN-112) | Custom Workflow: HTML prototype output broken, plus 3 confirmed gaps | Same family as **SPEC012-BUG-01** (deliverable strategy/name mismatch) |
| [KAN-121](https://velocityai-hex.atlassian.net/browse/KAN-121) | Custom workflow with prototype agents shows validator QA text instead of HTML | Child of KAN-112, same family as **SPEC012-BUG-01** |
| [KAN-120](https://velocityai-hex.atlassian.net/browse/KAN-120) | Resume Run: DB race, agent statuses reset to idle, task data lost | Same shape as **SPEC012-BUG-08** — different specific defect |
| [KAN-125](https://velocityai-hex.atlassian.net/browse/KAN-125) | Concurrent pipeline runs cause agent progress corruption | Adjacent to **SPEC012-BUG-03** — concurrent *separate* runs, not intra-run parallel sub-agents; likely a different mechanism |

If KAN-112/121 are still open when this spec ships, **SPEC012-BUG-01** is direct evidence
toward closing them — worth a comment on those tickets rather than a new one.

## Not yet verified

1. **SPEC012-BUG-09** — `pytest tests/unit/test_user_workflows.py` has never run.
2. **SPEC012-BUG-06** and **SPEC012-BUG-05** — `npm test -- userWorkflows` and
   `npm run build` have never run.
3. **SPEC012-BUG-08** — needs a resumed custom workflow (backend restart mid-run, or a
   gate resume) with `agent_start.name` checked in `run_events`.
