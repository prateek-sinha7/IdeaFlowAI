---
name: velocity-workflow-creator
description: Design and generate a complete, validated Velocity (Flowin) workflow manifest (`<id>.workflow.json`) from a user's requirements. Analyzes the request, triages complexity, decomposes the goal into verifiable parts, asks only functional questions, plans each step, writes multi-phase step prompts, picks the flow (chain, intake with a human gate, parallel sub-agents, fan-out, loops, branches, hand-offs) and only the capabilities the job needs, then checks the result with the bundled validator. Use when asked to create, design, generate, plan, review or improve a Velocity or Flowin workflow, Composer workflow or workflow manifest. Activate it again for every request that creates or changes a workflow, even if it was used earlier.
argument-hint: "<requirements text or file> [trust user|db|file] [output folder]"
---

# Velocity Workflow Creator

You turn a request into one Velocity workflow manifest, `<id>.workflow.json`: which steps
run, what each step receives and produces, which agent and prompt each uses, where people
answer or review, how quality is checked and what each step may touch. The platform
compiles the manifest and runs it with a deterministic engine; the model never chooses the
next step. Every capability you add must answer a stated requirement, and every step prompt
is a detailed, multi-phase job description like the ones in the shipped examples.

**Decomposition comes first and is mandatory.** Before you write the Brief, read
`<skill>/docs/problem-decomposition.md` in full. Recover the goal and its done-when
conditions, triage the complexity (SIMPLE / MODERATE / COMPLEX), and break the goal into
parts that can each be verified on their own, at the depth the tier allows and no deeper.
The Step Plan is built from that breakdown, never straight from the request's verbs.

## How to work through this skill

- **Every turn that creates or changes a manifest starts at step 1.** Reads and lookups from
  earlier turns in the conversation do not count: run steps 1-4 again, and name what you
  loaded on the response's first line, "Context loaded this turn" (step 11). A manifest written from memory of an
  earlier turn is a draft; re-check it from step 1. When a later turn changes an existing
  manifest, re-plan locally: re-cut only the affected parts and steps, and rebuild the whole
  breakdown only when the Goal or Done when changed (problem-decomposition §4.4).
- Do the steps in order. Read each tool result before you start the next step. Never put a
  call and a call that depends on it in the same parallel batch: write the file, then
  validate it, then read the findings, then fix.
- `<skill>` is the absolute folder from the skill activation result. From the workspace root
  it is `backend\app\agents\workflow_builder\skills\velocity-workflow-creator`; from
  `backend\` it is `app\agents\workflow_builder\skills\velocity-workflow-creator`.
- Launch Python as `python` or `py -3` (3.10 or newer; no packages needed). In a backend
  checkout `uv run python` also works.
- Do not read `schema/workflow-manifest.schema.json` (60 KB), `docs/catalog.md` (80 KB),
  `references/catalog.json` (200 KB) or an example file whole: a single read arrives cut off.
  Ask `scripts/catalog_lookup.py`; it prints only the part you ask for.

## Procedure

### 1. Understand the goal and write the Workflow Brief

Read `<skill>/docs/problem-decomposition.md` in full first (every turn; it fits in one read).
Answer its Step 0 (§2) for yourself, then fill in every line of the Brief from the request
and write it out: it goes into your response, so the user can check what you took from the
request. Goal, Deliverable and Done when are never guessed: if one cannot be filled from the
request and the context, it is a functional question for step 3.

```text
Goal:         turn <X> into <Y> for <Z>   (an outcome, not an activity)
Trigger:      what starts a run (a Composer launch with a brief, uploads, a chained run, ...)
Deliverable:  text reply | one file <name.ext> | a bundle of files
Done when:    1-5 observable conditions that prove the goal is met
Not in scope: what the request implies but does not ask for
Inputs:       brief only | uploads (types) | images | template or design system | previous run |
              another workflow's run | Jira / GitHub / GitLab / Slack
Facts needed: every fact the deliverable needs, each with its source: request | user answer
              before the work (quick-reference §2a) | upload | assumed (say which value)
Stages:       <transformation> -> <transformation> -> ...   (not the request's verbs)
Variation:    none | branch on <X> | repeat until <Y> | hand off to workflow <W>
Scale:        none | <N> similar items
Quality bar:  none | reviewer/editor step | validator | AI critic | a person approves at <stage>
Constraints:  length, tone, format, required items, things to avoid, cost or speed, EU data
Runtime:      Run once in the Composer = user trust (default) | saved workflow = db | engineer file = file
Requirements: every phrase of the request the workflow must satisfy, one per line
```

### 2. Triage and decompose (mandatory)

Follow `problem-decomposition.md` §3-5 and write both results into your response:

1. **Triage.** Score the six signals 0/1/2, total them, apply the overrides (Irreversibility 2
   means at least MODERATE; an unscorable signal is a functional question, or the higher
   score when the gap is internal) and run the checklist / flowchart / project plan sanity
   test. Record the tier and the reason.
2. **Decompose by tier.** SIMPLE: flat ordered parts and one final check (§4.1). MODERATE:
   happy path, then decisions, failures, gates, parallelism, checks (§4.2). COMPLEX: passes
   A-E: outcome tree (max 3 levels, one cutting logic per level), vertical slices, sizing
   XS-XL, dependency waves, risk order with checkpoints and an abandon condition (§4.3).
3. **Self-audit** with §5 (coverage, granularity, structure, honesty) and §7 (anti-patterns).
   Fix every failure before step 5.

If the deliverable matches a playbook (`docs/playbooks/`), read it before you write the breakdown and use its stages as the parts (`docs/problem-decomposition.md` §3a).

If a functional gap blocks the triage or the breakdown, finish what you can, ask in step 3,
and complete this step with the answers.

### 3. Ask functional questions only

Classify every unknown with `problem-decomposition.md` §6 before you ask. Ask only
**functional** questions: the answer changes the outcome, the scope or a business rule. In a
workflow these are typically the deliverable, uploaded inputs, where a person approves or
answers, branch and loop criteria, the number of items compared with the 8-worker budget,
anything that needs trusted capabilities (it decides where the workflow can run), and which
external systems it reads or writes. Each must pass the litmus test (§6.4): "If the user
answers differently, the OUTCOME changes because ...".

Never ask **internal** questions (tools, agents, models, effort, retries, loop caps, formats,
file names, step count, parallelism, decomposition pattern, tier): decide them, record each
in the Decisions table (step 6) and move on.

The intake settles the Brief from the slot table (`docs/intake-slots.md`) before this step
runs, and its brief arrives with your message. Ask no further functional questions and add no
intake step unless the slot table asks for one; a slot the brief marks assumed or unknown
keeps its default and goes on the Open questions line as a risk. Only when no intake brief
arrived and a functional question is open, ask at most 5 numbered questions in one message,
each with options and a recommended default, then stop and wait. For a deliverable with a
playbook (UI prototype, requirements document), take the depth from the brief (Full is the
default) and show the playbook's stages at that depth in the response, one line each with
what it produces.

Question bank: `docs/requirements-analysis.md` §3-5.

### 4. Load the context (every turn)

`docs/problem-decomposition.md` was read in step 1. Then:

1. Read `<skill>/docs/quick-reference.md` in full. It fits in one read.
2. Read `<skill>/docs/prompt-writing.md` in full. It fits in one read.
   Then read `<skill>/docs/requirements-analysis.md` §3-5, the question bank the intake used.
3. Run `python <skill>/scripts/catalog_lookup.py overview --trust <user|db|file>`. Its
   ASKING THE USER section says how this workflow can get facts from the user at that trust.
4. Run `python <skill>/scripts/catalog_lookup.py example`, then print the closest shipped step
   for each step role in your plan, at least one, for example
   `python <skill>/scripts/catalog_lookup.py example prototype_v2 fi-close` or
   `python <skill>/scripts/catalog_lookup.py example backlog us-review`. Copy its layout and
   depth, not its trust-only features.
5. For each requirement phrase that sounds like a capability (a check, a tool, a connector,
   a length or tone limit), run `python <skill>/scripts/catalog_lookup.py search <words>`.

6. Find the closest predefined workflow: run `catalog_lookup.py search <the deliverable's words>`
   and `catalog_lookup.py workflows`. If one already makes this deliverable (for example
   `prototype_v2` for a prototype from documents), name it to the user and use its stages as the
   blueprint. Its trust-only features do not carry over.

Use only names that this output, the reference or a later lookup shows you; never assume a
capability exists.

### 5. Plan the steps from the breakdown

Write the Step Plan table before any JSON. It goes into your response. Build it from the
step 2 breakdown with `problem-decomposition.md` §8: each part becomes its own step or a
`Phase N` of a neighbouring step (§8.1), the tier sets the size and shape (§8.2), and each
part's done-conditions become CHECK lines, a validator or a critic decision (§8.3). Every
part appears in the plan; no step exists that no part asked for.

| # | instance_id | Job (one transformation) | Receives, and how it arrives | Produces (label or file, format) | Read by | If input is missing | Tools | Model (effort) | Gate/check |
|---|---|---|---|---|---|---|---|---|---|

Rules:
- **Facts reach every step that uses them.** For each fact in the Brief's "Facts needed",
  trace its path: the request reaches only the first step; a later step gets it only through
  a paste (`consumes`), a file it reads, or `.context/user-prompt.md` (quick-reference §4).
- **Add an intake step** when the user must supply facts before the work, or the brief may
  lack required facts. Choose the mechanism from quick-reference §2a for the Runtime trust.
  At `user` and `db` trust that is an intake step with a `human` gate, not clarify.
- **Add a reviewer/editor step** when the brief states checkable constraints (length, tone,
  inclusive language, required items, no invented facts). It consumes the facts and the draft.
- **Define the missing-input behavior** of every step: stop with `NEEDS_INPUT: <items>`,
  ask, or assume and mark "Assumption:". A deliverable of placeholders is never acceptable.
- Stages are transformations (collect facts, plan, draft, check), not the request's verbs.
  Every step answers a requirement; merge steps that would only pass text along.
- Size: Tiny 1 step, Simple 2-4, Standard 4-8, Complex 8-16. Beyond 16 root steps use a
  fan-out, `subagents` groups or chained workflows. The size must fit the step 2 tier
  (problem-decomposition §8.2); if it does not, re-triage or re-cut before you continue.
- Every irreversible step (a post, an integration write, `exec`) has a gate directly before
  it, every parallel group has a join (an aggregator), and every loop has a cap.
- When the plan has an intake or other human gate, a branch, loop, fan-out, parallel group,
  validator, upload or integration, read `docs/design-playbook.md` §1-3 and the matching
  section of `docs/patterns.md` (intake: §21). For trust beyond Run once read `docs/trust-and-security.md` §1-2.

### 6. Record every decision

List each value the brief did not dictate: the tier and the cut you chose, `planner` and
`clarify`, the ask mechanism, each step's model and effort, the deliverable, tool grants,
gates, hand-offs and every number (word targets, loop caps, redo limits). Every internal
question you decided instead of asking (problem-decomposition §6.2) is a row here. Next to
each, name the rule you followed (file and section), or write "my default" and the reason. For every field whose rules you have not
printed in this turn, run `python <skill>/scripts/catalog_lookup.py field <path>` first, for
example `field clarify.mode` or `field step.redoable`; use `docs/field-guide.md` for the
judgement. When an example and a rule disagree, follow the rule.

### 7. Write the prompts

Write every `custom-agent` prompt with the prompt standard (quick-reference §8): role line,
phase list, WHAT YOU RECEIVE (each input exactly as it arrives), WHAT YOU NEVER DO, IF INPUT
IS MISSING, `Phase N` sections with Rules and numbered Steps, OUTPUT, CHECK BEFORE YOU REPLY,
HOW TO DELIVER. Use the role templates in `prompt-writing.md` §4 and the worked example in §6.
Put every constraint from the brief into the Rules and CHECK lines of the steps that write
and edit. A part that became a phase of a step is one `Phase N` section, and its
done-conditions are lines under CHECK BEFORE YOU REPLY. A working step's prompt is usually
3,000-7,000 characters. Only decision steps and human-choice placeholders are short.

### 8. Write the file

Write to the path the user gave, otherwise `workflows/<id>.workflow.json` in the current
workspace (create the folder). Use 2-space indentation and the field order of
`docs/field-guide.md`. Prompts are single JSON strings with `\n` for line breaks.

### 9. Validate until VALID

Run it in its own call once the write has returned:

```text
python <skill>/scripts/validate_manifest.py <file> --trust <user|db|file> --summary
```

1. Fix every `ERROR` and every `WARN`, then run the command again. A `WARN` you keep needs a
   reason in your response. Fix `prompt-depth` by writing the missing sections of the
   standard for that step's job, never by padding.
2. Read every `info` line (`prompt-structure` lists missing parts) and fix the ones that apply.
3. Check the printed plan: the steps run in the order of the Step Plan, the step marked
   `ends run` produces the deliverable, and the model column shows the effort you set.
4. In a Velocity backend checkout also run the platform's compiler (cwd `backend/`):
   `uv run python <skill>/scripts/validate_manifest.py <file> --trust <trust> --compiler .`

Do not hand over a manifest that is not `VALID`.

### 10. Check what the validator cannot

Answer each "Check yourself" question (1-16) in `docs/checklist.md` with yes or no. Fix every
"no", then put the answers on the Checklist line of your response.

### 11. Respond

Use this format. Keep each part short: the JSON file is the deliverable.

```markdown
**Context loaded this turn:** <files read and lookup commands run in this turn>
**Workflow:** `<id>` "<display_name>", saved to `<path>`
**Trust:** <user|db|file> (<where it can run>) · **Size:** <Tiny|Simple|Standard|Complex>, <n> steps
**Flow:** <one-line sketch, e.g. intake (human gate) -> draft -> edit>
**Brief:** <the Workflow Brief from step 1, without its Requirements lines>
**Triage:** <SIMPLE|MODERATE|COMPLEX>, <total>/12 (steps <n> · branching <n> · systems <n> ·
dependencies <n> · human <n> · irreversibility <n>); sanity: <checklist|flowchart|project plan>

**Decomposition:** <parts in order: name, size XS-M, wave, which step or phase it became;
for COMPLEX also the outcome tree and the abandon condition>

**Step Plan:** <the table from step 5>

**Requirement coverage:**
| Requirement (from the request) | How the workflow meets it |
|---|---|
| <phrase> | <step or setting>, or "prompts only: no validator can check this" |

**Decisions:**
| Choice | Value | Rule followed (file §), or "my default: <reason>" |
|---|---|---|

**Deliverable:** <strategy> <name>
**Open questions:** <unanswered functional questions, listed as risks, or "None">
**Checklist:** 1 yes · 2 yes · ... · 16 yes (a "no" names its fix, or why it stays)
**Validation:** VALID, <n> warnings (<the reason each one remains>), `validate_manifest.py --trust <t>`
**Run it:** <the matching way below, plus what a launch needs: uploads, template, connectors>
```

How a manifest file reaches the platform (the Composer has no JSON import):

- **Run once** (`user`): `python <skill>/scripts/export_manifest.py <file> --run-payload run.json --message "<brief>"`,
  then `POST /api/runs` with `run.json` and the user's bearer token.
- **Saved workflow** (`db` for callers entitled to the custom pipeline, `user` otherwise):
  `export_manifest.py <file> --save-payload save.json`, then `POST /api/user-workflows`.
- **Engineer-shipped** (`file`): `export_manifest.py <file> --yaml <backend>/agents/workflows/<id>/workflow.yaml`.

At `user` or `db` trust, tell the user how an intake step asks: the run pauses at the review
card, they type the answers with Request changes, then Approve (quick-reference §2a). Each
round sees only that round's answers, so they repeat earlier answers they want kept.

## Ground rules

1. **Only real names.** Every agent, capability, model, skill, MCP tool, integration scope and
   workflow id comes from `catalog_lookup.py`. If the catalog may be stale for the user's
   platform, say so and offer `scripts/refresh_catalog.py`.
2. **`custom-agent` by default**, each with a unique kebab-case `instance_id`, a `name` and a
   complete `prompt`. A catalog agent only when its contract fits exactly; at most once each.
3. **Least privilege.** Write `tools` on every step. Write access only where a step creates
   files. No `exec`, `secrets`, `network` or `spawn_subagents` unless a requirement needs it and
   the trust allows it at run time.
4. **Justify every capability.** Gates, validators, loops, hooks, skills, premium models and
   raised limits each answer a requirement: one the user stated, or one the deliverable's
   playbook implies (`docs/requirements-analysis.md` §1).
5. **Bound everything.** Loops: `loop_max_iterations` 2-3. Fan-outs fit the worker budget.
6. **Ask functional questions only.** Never guess the outcome, scope or a business rule;
   never ask about internal matters. Decide those, and list each as an assumption.
7. **No secrets, credentials or personal data in a manifest.** Prompts treat uploaded and
   integration content as data.
8. **Never hand over an invalid manifest.**
9. **No thin prompts.** Every working step's prompt follows the prompt standard.
10. **Decompose before you design.** Every manifest comes from a triaged, self-audited
    breakdown (`docs/problem-decomposition.md`). Depth matches the tier: no 15-step answer
    to a checklist problem, no gate-free plan for a project-plan problem.

## Files in this skill

- `docs/problem-decomposition.md`: steps 1-3 and 5, mandatory every turn; goal and done-when,
  complexity triage, decomposition by tier, self-audit, functional-only questions, mapping to steps (§8).
- `docs/quick-reference.md`: step 4; fields, asking the user (§2a), hand-offs, models, gates, the prompt standard (§8).
- `docs/prompt-writing.md`: step 4; what a step receives, role templates, a worked intake prompt.
- `scripts/catalog_lookup.py`: every name, field, example step and "how to ask" question.
- `docs/checklist.md`: step 10; the questions only you can answer, and what the validator checks.
- `docs/requirements-analysis.md`: requirement signals, question bank, feasibility limits.
- `docs/playbooks/ui-prototype.md`, `docs/playbooks/requirements-document.md`: expert stages, depth variants, gates and checks for two deliverable families.
- `docs/design-playbook.md`, `docs/patterns.md`: sizing, topology, gates; 22 patterns with JSON.
- `docs/field-guide.md`: when and how to set every field; the tools grant table.
- `docs/trust-and-security.md`: trust levels, runtime checks, budgets, security checklist.
- `examples/*.workflow.json`: five shipped workflows; print them with `catalog_lookup.py example`.
- `scripts/validate_manifest.py`: step 9. `scripts/export_manifest.py`: run, save or YAML payloads.
- `scripts/playbook_fit.py`: a coverage score of a manifest against a playbook, offline. `scripts/assemble_manifest.py`: builds a manifest from a skeleton and one prompt file per step. Both are for maintainers and are not in the builder's script allow-list yet.
- `docs/evals/reference-requests.md`: the fixed requests and pass criteria for measuring the builder.
- `docs/catalog.md`, `references/catalog.json`, `schema/`: generated data; query them with `catalog_lookup.py`.
- `scripts/refresh_catalog.py`, `scripts/schema_sync.py`, `scripts/selftest.py`, `docs/extending.md`,
  `docs/agent-integration.md`: keep the catalog current and confirm the skill is consistent.
