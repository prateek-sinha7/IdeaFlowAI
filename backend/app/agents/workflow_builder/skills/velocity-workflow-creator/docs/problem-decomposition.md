# Workflow problem decomposition (mandatory)

Read this file in full on every turn that creates or changes a workflow, before you write
the Workflow Brief (SKILL.md step 1). It fits in one read. It is not optional: SKILL.md
steps 1 (Brief), 2 (triage and decompose), 3 (questions), 5 (Step Plan), 6 (Decisions),
10 (checklist) and 11 (response) depend on it.

Your job here is to turn a goal into parts that can each be built and verified
independently. This file does not choose the output format or the manifest fields; those
come from `quick-reference.md`, `design-playbook.md` and `field-guide.md`. It decides the
STRUCTURE of the breakdown: the parts, their boundaries, their order and their
dependencies. Section 8 maps that structure onto a Velocity manifest.

Do not use it for single-action requests that are not a workflow, or for running a
workflow that is already approved.

---

## 1. Core principles

1. Users bring goals, not tasks. Recover the goal before cutting anything.
2. Decomposition is a graph decision, not a list. Every cut is a place where an error is
   either contained or amplified. Cut where verification is possible.
3. Match depth to complexity. Over-decomposing a simple problem is as much a defect as
   under-decomposing a complex one.
4. Every part must be independently checkable. If you cannot say how you would know a part
   is done, it is not a part yet.
5. Act only on leaves. A part that is still vague must be split, not built.
6. Decide internal matters yourself. Ask the user only about functional intent. Record every
   internal choice as an explicit assumption.

---

## 2. Step 0: understand before cutting

Before decomposing, answer these for yourself. Do not skip this even for simple requests:
it takes seconds and prevents most bad breakdowns.

- **GOAL**: what outcome must exist when this is finished? State it as a result ("supplier
  is paid and notified"), not an activity ("call payment API").
- **TRIGGER**: what starts it?
- **INPUTS AVAILABLE**: what do we have at the start?
- **OUTPUTS REQUIRED**: what must exist at the end (artifacts, state, messages)?
- **DONE-WHEN**: 1-5 observable conditions proving the goal is met.
- **NOT IN SCOPE**: what the user implied but did not ask for.

If GOAL, OUTPUTS or DONE-WHEN cannot be filled from the request and available context, you
have a FUNCTIONAL gap. The intake closes these gaps before you run: take them from the intake
brief, whose readiness rule (`scripts/intake_readiness.py`, `docs/intake-slots.md`) decides
when nothing more is asked. Ask (section 6) only when no brief arrived. Never guess the
outcome. Everything else you may assume.

These answers go into the Workflow Brief (SKILL.md step 1: Goal, Trigger, Inputs,
Deliverable, Done when, Not in scope).

---

## 3. Step 1: complexity triage

Score six signals, each 0 / 1 / 2:

| Signal | 0 | 1 | 2 |
|---|---|---|---|
| Expert stages the deliverable needs (for example research, analysis, design, build, check) | one stage | 2-4 stages | 5 or more stages |
| Branching | none | 1-2 decisions | nested or data-dependent paths |
| Systems or tools involved | 1 | 2-3 | 4+ or unknown |
| Dependencies | strictly linear | some fan-out | graph with joins or loops |
| Human involvement | none | one approval | multiple roles or approvals |
| Irreversibility | read-only | internal writes | external side effects (payments, emails, posts, deletions) |

Total gives the tier:

- 0-3: **SIMPLE**
- 4-7: **MODERATE**
- 8-12: **COMPLEX**

Overrides:

- Irreversibility = 2: treat as at least MODERATE (it needs a gate).
- A signal cannot be scored because information is missing: if the missing information is
  FUNCTIONAL, ask first; if INTERNAL, assume the higher score and continue.

Sanity test against your own bias: you will tend to over-classify, because you can see every
possible branch. Ask: "Would a competent person doing this manually write a checklist, a
flowchart or a project plan?" Checklist: SIMPLE. Flowchart: MODERATE. Project plan: COMPLEX.

Record the tier and the reason. The tier decides which procedure in section 4 you follow.

---

## 3a. Deliverable playbooks (input to step 2)

A playbook lists the expert stages of one kind of deliverable: what an expert does, in what
order, and what each stage produces. Read the playbook for the deliverable before you
decompose it, when one matches: `docs/playbooks/ui-prototype.md` (UI prototype) and
`docs/playbooks/requirements-document.md` (specification, PRD, user stories, backlog). The
playbook's stages are the candidate parts. The request decides which stages apply and how
deep the work goes; it does not decide whether an expert stage exists.

- The depth variant (Full or Lite) follows the user's answer to "Fast or Thorough?". Without
  an answer, use Full.
- A stage the playbook names is not dropped because the request does not mention it
  (requirements-analysis §1, requirement classes).
- A deliverable with no playbook is triaged with §3 alone. Say so in the response.

---

## 4. Step 2: decompose according to tier

### 4.1 SIMPLE problems: flat, ordered, minimal

How to break it down:

1. Write the steps in execution order. Typically 3-6.
2. Each step = one action, one system, one expected result.
3. Add a single final check that confirms DONE-WHEN.
4. Failure handling: one shared rule ("retry once, then stop and report"). Do not design
   per-step error branches.
5. Stop.

What NOT to do:

- Do not introduce sub-steps, parallel branches or approval gates (unless Irreversibility =
  2, in which case add exactly one gate before the irreversible step).
- Do not add "nice to have" steps the user did not ask for.
- If you find yourself past about 8 steps or adding decisions, re-triage: it was not simple.

### 4.2 MODERATE problems: happy path first, then decisions, then failures

How to break it down:

1. **Happy path**: write the sequence when everything goes right. This is the spine;
   everything else hangs off it.
2. **Decisions**: for each step on the spine ask, "Can this step's result change what
   happens next?" If yes, mark it as a decision point, name every branch, and make sure every
   branch either ends or rejoins the spine.
3. **Failures**: for each step that can fail, decide the business-visible outcome (retry,
   fallback path, escalate to a person, stop). Group identical handling into one shared
   handler rather than repeating it.
4. **Gates**: place an approval point immediately before any irreversible step.
5. **Parallelism**: mark steps that do not consume each other's results as able to run
   together. Do not force parallelism where it adds nothing.
6. **Checks**: verify after the happy path completes, and after each failure handler resolves.

Stopping rule: about 12 nodes at most. Beyond that, re-triage as COMPLEX.

### 4.3 COMPLEX problems: hierarchical, then sliced, then sized, then graphed

Work top-down in five passes. Do not skip a pass.

**Pass A: outcome tree (max 3 levels)**

- Level 0: the goal.
- Level 1: 2-5 sub-outcomes that are together NECESSARY and SUFFICIENT.
  - Sufficiency test: if every Level-1 item is true, is DONE-WHEN satisfied? If not,
    something is missing.
  - Necessity test: can one be removed with DONE-WHEN still holding? If yes, remove it.
- Level 2: for each sub-outcome, 2-6 concrete parts.
- Stop at Level 2. If a part still feels too big, that is a sizing problem (Pass C), not a
  depth problem. Deeper trees lose the overview and multiply hand-off overhead.

Use ONE cutting logic per level (by stage, by case type, by actor, by data domain, by
system). Mixing logics at one level is the root cause of almost every overlap and gap.
Before committing to a cut, generate two or three candidate cuts and pick the one with the
cleanest boundaries for THIS goal; the first cut you think of is rarely the best.

**Pass B: slice vertically, not horizontally**

- Horizontal (avoid): "all extraction, then all transformation, then all notifications."
  Nothing works until everything works, and errors from the first layer propagate silently
  into every later layer.
- Vertical (prefer): "complete path for case type A, complete path for case type B, then
  shared reporting." Each slice is verifiable on its own, early slices de-risk later ones,
  and partial completion still has value.

**Pass C: size every part**

| Size | Meaning | Action |
|---|---|---|
| XS | one action, one system | fine; consider merging with a neighbour |
| S | 2-3 actions, one system | ideal |
| M | 4-6 actions, one or two systems | ideal |
| L | 7+ actions or 3 systems | split |
| XL | cannot state "done" in 3 conditions or fewer | must split |

Split when ANY of these is true:

- The title needs the word "and".
- It spans two independent systems.
- Its completion needs more than 3 conditions to describe.
- It mixes mechanical work (fetch, format, validate) with judgement work (classify, decide,
  write). Separate them: mechanical parts can then be deterministic and cheap.

Merge when two adjacent parts always run together, share the same system, and neither is
separately verifiable.

**Pass D: dependency graph**

1. For each part, list what it PRODUCES and what it CONSUMES.
2. Draw a dependency wherever one part's output is another's input.
3. Parts with no incoming dependencies form wave 1; remove them and repeat to find wave 2,
   3, and so on. Parts in the same wave can run in parallel.
4. If two parallel parts share a data shape or contract, add an explicit "define the
   contract" part that both depend on. Define contracts first, then parallelise.
5. Reject cycles. If A needs B and B needs A, either it is one part, or an intermediate
   artifact is missing.
6. Check error containment: at every edge where a wrong upstream result would silently
   corrupt downstream work, there must be a verification point. If there is none, add one or
   move the cut.

**Pass E: order by risk and insert checkpoints**

- Pull the highest-uncertainty and highest-irreversibility parts as EARLY as dependencies
  allow. Fail fast, cheaply.
- Insert a checkpoint (a verification point) after each wave. Section 8 says when a
  checkpoint is a human gate and when it is a validator, critic or check.
- Add review loops only where a reviewer can meaningfully reject work, and always with an
  iteration cap.
- State explicitly the condition under which the plan should be abandoned and re-planned
  rather than pushed through.

### 4.4 Re-plan locally, not globally

When a part fails or new information appears mid-way, revise only the smallest subtree that
is affected. Do not throw away the whole breakdown. Restart from the root only if the GOAL or
DONE-WHEN itself changed. On a later turn that changes an existing manifest, this means:
change the smallest set of affected steps, and rewrite the Brief from scratch only when the
Goal or Done when changed.

---

## 5. Step 3: self-audit before handing off

Check every item and fix failures before you turn the breakdown into the Step Plan. The
answers feed checklist questions 13-16 (`checklist.md`).

**Coverage**

- [ ] The union of all parts satisfies every DONE-WHEN condition.
- [ ] Every available input is used by at least one part (or explicitly marked unused).
- [ ] Every path, including failure paths, reaches an end.

**Granularity**

- [ ] No part is L or XL.
- [ ] No two parts could be merged without creating an "and".
- [ ] Mechanical and judgement work are not mixed inside one part.

**Structure**

- [ ] No cyclic dependencies.
- [ ] Every parallel group has a join point.
- [ ] Every irreversible action has a gate directly before it.
- [ ] Every loop has an iteration cap.
- [ ] One cutting logic per level; no overlaps between siblings; no lazy "other" bucket
      hiding a real category.

**Honesty**

- [ ] Every internal decision is written down as an assumption (the Decisions table).
- [ ] Every open functional question has been asked, not silently assumed.
- [ ] The tier you chose matches the structure you produced.

---

## 6. Clarification policy: functional questions only

When you are confused, classify the confusion before you ask anything.

### 6.1 FUNCTIONAL: ask the user (batch, max 5 per round)

Ask when the answer changes the OUTCOME, the SCOPE or a BUSINESS RULE. Typical examples:

- Missing outcome: "When this finishes, what must the customer have received?"
- Business rule: "Should amounts above a threshold need approval? If so, what threshold and
  whose approval?"
- Scope boundary: "Should cancelled orders be included, or only completed ones?"
- Conflicting requirements: "You asked for real-time processing and for an overnight batch.
  Which one applies here?"
- Actors and authority: "Who is allowed to approve or reject at this step?"
- Definition of success: "What counts as a 'resolved' case?"
- Meaning of data (not format): "Does 'active customer' mean logged in recently or holding a
  paid plan?"
- Business-visible failure behaviour: "If the supplier system is down, should requests
  queue or be rejected?"

In a Velocity workflow these usually concern: the deliverable, the inputs the user will
upload, where a person approves or answers, branch and loop criteria, how many items a run
handles, where the workflow will run, and which external systems it reads or writes
(SKILL.md step 3).

### 6.2 INTERNAL: never ask; decide and record as an assumption

Do not ask about:

- Which tool, library, service, model, agent or API to use.
- Retries, timeouts, batch sizes, concurrency, caching, loop caps, effort levels.
- Data formats, schemas, field names, file names, paths, step ids.
- Step order when the order has no business meaning.
- Whether or how to parallelise (parallel group, fan-out, waves).
- How many parts or steps to create, how to size them, how deep to go.
- Error-handling mechanics (as opposed to business-visible outcomes).
- Logging, monitoring, observability, hooks.
- Anything the user could reasonably answer with "you're the engineer, you decide."

For each of these: pick the safest reasonable default, write it down as an assumption with a
one-line reason (a row in the Decisions table, SKILL.md step 6), and move on. Assumptions are
reviewed with the breakdown; that is far cheaper than an interruption.

### 6.3 Question quality rules

- Ask only if a different answer would change the breakdown. If every answer leads to the
  same structure, do not ask.
- Offer options ("A / B / something else") and mark a recommended default. Users answer
  options faster and more accurately than open questions.
- Never ask the user to classify complexity or choose a decomposition pattern. That is your job.
- Never ask something already answered in the request, the project context or an existing
  predefined workflow.
- The number of question rounds is set by the intake readiness rule
  (`scripts/intake_readiness.py`, at most `BUILDER_INTAKE_MAX_ROUNDS`); reaching the limit
  means "use the defaults". When an intake brief arrived, ask no further functional questions.
- If the user says "just do it" or "you decide", proceed on assumptions and list the
  unanswered functional questions prominently as risks (the response's Open questions line).

### 6.4 The litmus test

Before asking, complete this sentence:

> "If the user answers differently, the OUTCOME changes because ______."

If you cannot finish it with a business consequence, the question is internal. Decide it
yourself.

---

## 7. Anti-patterns: reject your own breakdown if you see these

| Anti-pattern | Why it hurts | Fix |
|---|---|---|
| "Implement the process" as one part | unverifiable | split until done-ness fits in 3 conditions or fewer |
| Horizontal layers | nothing works until all works; errors propagate silently | vertical slices |
| Depth beyond 3 levels | lost overview, hand-off overhead | collapse to goal, sub-outcome, part |
| Simple request with 15 nodes | over-engineering | strip to a checklist |
| Complex request with no gates or checkpoints | irreversible actions unprotected; errors amplify | gate before irreversible, checkpoint per wave |
| Loop without a cap | unbounded cost | cap iterations |
| Same failure handling copied into every part | noise | one shared handler |
| Mixed cutting logics at one level | overlaps and gaps | one logic per level |
| Lazy "other" bucket | hides a real category | name it or justify it |
| Asking "which tool should I use?" | internal decision pushed to user | decide, record assumption |
| Asking nothing on a vague goal | guessing the outcome | one batched round of functional questions |
| Restarting the whole plan after one failure | wasted work | re-plan the affected subtree only |

---

## 8. Applying the breakdown to a Velocity manifest

A **part** is a unit of verification. A manifest **step** is a unit of execution, and every
step costs a model call that re-reads the context (`design-playbook.md` §1). So parts and
steps are not always one to one.

### 8.1 Parts become steps or phases

- Make a part its own step when it needs a different model or effort, a different tool
  grant, its own gate, validator or verification point, a person between it and the next
  part, or when it repeats per item (fan-out).
- Otherwise make it a `Phase N` of the step that holds its neighbours, and turn its
  done-conditions into that step's CHECK BEFORE YOU REPLY lines.
- Mechanical and judgement parts stay separate parts in every tier. They become separate
  steps when that buys something real (a cheap model on the mechanical step, a validator on
  its output); in a Tiny or Simple workflow they may be separate phases of one step.

- A stage whose output another stage or a validator reads (requirements, gaps, spec, screen plan,
  design) is its own step, not a phase. The next step then reads a file, and the check has a
  file to check. Phases of one prompt are for work that no other stage reads.

### 8.2 Tier to workflow size

| Tier | Size (`design-playbook.md` §1) | Shape |
|---|---|---|
| SIMPLE | Tiny or Simple: 1-4 root steps | Linear chain. One shared missing-input rule. The final check is the last step's CHECK lines, or a reviewer step when the brief has checkable constraints. One gate only if Irreversibility = 2. |
| MODERATE | Simple or Standard: 2-8 root steps, about 12 nodes counting gates and branches | Spine as `depends_on` chain; decisions as classifier + `conditional` route; failure handlers as missing-input rules, `fix`, `on_loop_exhausted`; gates before irreversible steps; independent steps as a parallel group with an aggregator. |
| COMPLEX | Standard or Complex: 4-16 root steps; beyond 16, fan-out, `subagents` groups or chained workflows | Level-1 sub-outcomes become stages or `subagents` groups; vertical slices become branches or fan-out per case type; waves become `depends_on` layers or `wave_scheduler`; contract parts become a planner step whose task list or work file the parallel parts consume. |

If the tier and the size disagree (a SIMPLE triage with 9 steps, a COMPLEX triage with 2),
one of them is wrong. Re-triage or re-cut before writing the Step Plan.

### 8.3 Term map

| Decomposition term | In the manifest |
|---|---|
| DONE-WHEN of the goal | Brief "Done when" lines; the final step's CHECK lines; the requirement coverage table |
| Done-conditions of a part | the step's CHECK BEFORE YOU REPLY lines; a validator; a critic decision |
| Decision point | classifier step + `gates: ["conditional"]` + `route.outcomes` |
| Loop with a cap | critic routes back with `feedback`; `loop_max_iterations` 2-3; `on_loop_exhausted` |
| Gate before an irreversible step | `human` or `before-human` before a Slack post or an integration write; `security` + `approval` on `exec` |
| Shared failure handler | one IF INPUT IS MISSING rule style for the whole workflow, plus `retry` or `fix` where needed; no per-step error branches |
| Parallel group with a join | `subagents.mode: parallel` under an aggregator step, or fan-out + aggregator |
| Waves | `depends_on` layers, or `wave_scheduler` over `json_tasks` with `depends_on` |
| Contract part | a planner step whose output (a `json_tasks` list or a named work file) every parallel worker reads |
| Checkpoint after a wave | a verification point: a validator, a critic, or the next step's input check. It is a `human` gate only where the user asked for review, or before an irreversible or expensive wave; keep to 1-2 human gates (`design-playbook.md` §5). |
| Abandon condition | `NEEDS_INPUT` stop, `on_loop_exhausted: "fail"`, or a person rejecting at a gate |
| Assumption | a row in the Decisions table (SKILL.md step 6) |
| Functional question | SKILL.md step 3 |

### 8.4 What to write in the response (SKILL.md step 11)

- **Triage:** the tier, the total and each of the six scores, and the checklist / flowchart /
  project plan sanity answer.
- **Decomposition:** the parts in order with their size (XS-M) and wave, and which step or
  phase each one became. For COMPLEX add the outcome tree (goal, sub-outcomes, parts) and the
  abandon condition.
- Every internal choice from this file goes into the Decisions table with
  "problem-decomposition §<n>" as the rule followed.
