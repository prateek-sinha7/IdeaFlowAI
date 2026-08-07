# Feature Specification: Model-Graded Eval Branch (LLM-as-Judge + Report) — first example: prototype-specify

**Spec ID**: 005-prompt-eval-scoring
**Created**: 2026-07-28
**Status**: Clarified (plan.md/design.md/tasks.md/data-model.md now stale — see clarifications.md Q12-Q15; re-run /apex:plan and /apex:design)
**Stack**: typescript, javascript, python | react, nextjs, fastapi | postgresql

---

## 1. Problem Statement

The eval harness (`backend/tests/evals/`) today is entirely **deterministic**: its one live
(real-model) track, covering `prototype-revision-agent` under
`tests/evals/workflow/prototype/revision/`, checks a delivered response with a hand-written
checker function (`checkers.py`) — structural facts only (a route resolves to a section, a
button has a handler, etc.). There is no model-based ("did this response actually satisfy the
request, at the quality level a human reviewer would expect") grading anywhere in the codebase.

This spec introduces that as a **new, separate evaluation branch** — model-graded eval — living
alongside the existing deterministic `workflow/` track, not folded into it. The two tracks answer
different questions (deterministic: "is this structurally correct"; model-graded: "is this
actually good") and are expected to eventually cover overlapping agents from two angles, so they
are built as independent, composable pieces from the start rather than one extending the other.
`prototype-specify` — the **first agent in the `prototype` pipeline**
(`backend/agents/prompts/prototype-specify/AGENT.md`, `order: 1`, `gate: Human_Gate`) — is the
**first example agent** onboarded onto this new branch, chosen because it currently has zero eval
coverage of any kind. The branch itself is a **generic grading framework**: dispatch happens
through the existing `create_runner(agent_id, ctx)`/agent-registry implementation, reused as-is
rather than rebuilt as a from-scratch raw chat call to the provider API (resolved, see
`clarifications.md` Q9, reaffirmed under direct challenge in Q11 — deliberate, not incidental,
for two independent reasons: (1) future agents onboarded onto this branch will need real tool
calls to verify they produced a *correct* result, not just a plausible-sounding response, so a
raw prompt-only dispatch path is a dead end for exactly the agents this framework needs to grow
into; and (2), the one that also applies to `prototype-specify` itself today — its own `AGENT.md`
frontmatter declares `injects: [template, design_system, images]`, meaning the `AGENT.md` body
text alone is *not* the full system prompt that runs in production. `create_runner`'s
`_compose_system_prompt`/`_compose_injection` assemble the real prompt from injected
template/design-system content, guardrails, skills, hooks, and the constitution, then the body.
A raw chat call that skips this would silently grade a prompt that never actually ships — and
making it faithful would mean re-implementing that composition logic inside the grader, which is
*more* new code than reusing `create_runner`, not less). What "generic" actually buys is this:
**onboarding a new prompt/agent needs zero new Python code** — a new scenario YAML naming an
already-registered `agent_id`, with a `rubric:` block and a `precheck:` config block (resolved,
see `clarifications.md` Q10), is the whole unit of work. Adding a second agent later means adding
a new scenario file, not writing a new module.

`prototype-specify` is meaningfully different in shape from `prototype-revision-agent`:

- **Text-only, no tools** (`tools: []` in its frontmatter) — it never touches the filesystem.
  Given a user brief (+ an injected template and design system), it emits one structured
  document wrapped in `<spec>...</spec>` tags as its raw text response. There is no
  `prototype.html` file to read back. The existing live-scenario driver
  (`common/live_scenario.py::run_live_scenario_once`) is hard-coded to a **file-editing**
  agent's shape (it always seeds `prototype.html` into a sandbox, dispatches a revision-style
  message, and reads the file back afterward) — this is one more reason the new branch gets its
  own driver rather than growing a mode flag on that one: a text-response deliverable
  (dispatch a message in, capture the raw response out) is the more general shape for a
  model-graded eval anyway, since most agents worth grading on response *quality* are exactly
  the ones whose output is prose/structured-text, not a file diff.
- Its own prompt (`AGENT.md`) already states a detailed, checkable content contract: a minimum
  page count (4, or 5–6 for specific app types), every page fully specified (no
  "placeholder"/"stub"/"future expansion"), every nav link resolving to a real page, every table
  needing 5+ rows of realistic data, and an output that must both start with `<spec>` and end
  with `</spec>` with no preamble. That contract is exactly the kind of thing a cheap
  deterministic checker can partially verify (structure, counts, forbidden strings) — and
  exactly the kind of thing a deterministic checker **can't** fully verify (is the data
  *actually* realistic and domain-specific, does the page content match the brief's intent, is
  the nav "flow" coherent) — which is precisely the gap an LLM-as-judge grading step is for.

This spec adds a new `backend/tests/evals/model_graded/` branch with four pieces, proven end to
end through `prototype-specify` as the first example:

1. **A generic model-graded driver** — dispatches a message to any named (already-registered)
   agent via `create_runner` and captures its raw response, plus a lightweight, **YAML-configured
   by default** deterministic pre-check (cheap structural sanity before spending judge tokens;
   resolved, see `clarifications.md` Q10 — no Python required for the common case, with an
   optional per-scenario Python hook for logic the generic config can't express).
2. **`prototype-specify` as the first onboarded example** — its scenario(s), a data-driven
   rubric, and a data-driven pre-check (plus one custom precheck hook for its nav-target
   cross-reference — the one check that genuinely needs real parsing, not config), built against
   the generic driver.
3. **An LLM-as-judge grading step** — after a run, a separate model call scores the response
   against the original prompt and a **per-scenario, data-driven rubric** (a plain text/markdown
   criteria block, fed into one shared judge-prompt-builder used by every agent — resolved, see
   `clarifications.md` Q10; for `prototype-specify`: its content/navigation/template-compliance
   rules, expressed as rubric text, not code), returning a numeric score, a pass/fail verdict,
   and a rationale.
4. **A persistent, append-only eval report** — every graded run is recorded as one entry
   (timestamp, agent, scenario, system prompt, prompt, response, deterministic-check verdict,
   judge score + reasoning) in a report that survives across runs and works the same way
   regardless of which agent produced the entry, plus a way to summarize it (overall and
   per-agent/per-scenario "percentage good").

### Standard Operating Procedure this branch exists to support

Resolved, see `clarifications.md` Q8. This is the explicit, repeatable loop the user asked to
have recorded — not just implied by the architecture, written down as the procedure:

1. **Prompt** — already exists (`AGENT.md`). Nothing to build here; the loop starts from
   whatever prompt is currently checked in.
2. **Dataset** — the agent's `model_graded/agents/<agent>/scenarios/*.yaml` (for
   `prototype-specify`: one scenario per `clarifications.md` Q4, exercised over multiple sampled
   runs per Q5 so a "percentage" has an actual denominator).
3. **Grade** — `./tests/evals/model_graded/model-graded.sh graded <scenario-id> --judge --samples N` (Story 6) runs the
   deterministic pre-check and the LLM judge across N samples and appends every run to the
   persistent report (Story 3).
4. **Feedback** — `./tests/evals/model_graded/model-graded.sh report --worst N` (Story 6, resolved per Q6) surfaces the
   lowest-scoring runs' full judge rationale, grouped by which prompt version produced them
   (`system_prompt_hash`) — raw evidence for a human to read, not a synthesized suggestion (see
   Q6 for why synthesis/auto-editing is explicitly not part of this tool).
5. **Improve & repeat** — a human edits `AGENT.md` based on step 4, then repeats steps 3–4. The
   report's `system_prompt_hash`-grouped trend (Story 6, Q7) shows whether the score actually
   moved between prompt versions. `./tests/evals/model_graded/model-graded.sh report --target T` answers "did I hit my bar yet"
   in one line; there is no automated stop condition or automated re-run — every iteration is a
   human-invoked command (per this repo's standing rule that live-model runs are always manual).
6. **Then repeat the whole procedure for the next agent** — once `prototype-specify` converges,
   the same six steps apply to the next agent onboarded onto the branch, using its own
   `model_graded/agents/<agent>/` folder (§3.2 item 2's design is what makes this a data
   addition, not a redesign).

### Background: standard process this follows

Model-based grading for prompt/agent evals is a well-established pattern (OpenAI Evals, the
Anthropic eval cookbook, Arize Phoenix/traceloop-style eval pipelines, and this repo's own
`.investigations/free-models/` research all converge on the same shape):

- **Deterministic checks stay deterministic, even inside a model-graded branch.** Anything a
  checker function can verify precisely — output wrapped in `<spec>...</spec>`, page count ≥ the
  declared minimum, no forbidden placeholder strings ("Lorem ipsum", "TBD", "Coming soon",
  "future expansion"), every nav target listed in the "Navigation Flows" section also appearing
  in the page table — should never be handed to a model: it's cheaper, instant, and has zero
  variance. The existing `workflow/prototype/revision/checkers.py` already does this for the
  revision agent's track; this spec's new branch carries the same discipline forward as a
  no-model-call pre-check, run before the judge call, not instead of it — judging is
  **additive** on top of the pre-check, not a replacement for it. Most of that pre-check is now
  **generic, YAML-configured** rather than per-agent Python (`clarifications.md` Q10) — a
  wrapper-tag check, a min-length/section-count check, and a forbidden-substring check cover the
  common case for any text-completion agent, not just this one. Only a check that needs real
  parsing (`prototype-specify`'s nav-target-to-page-section cross-reference) uses the optional
  per-scenario Python hook, and even that stays a small, focused function, not a whole module's
  worth of agent-specific plumbing.
- **LLM-as-judge for everything else.** For qualities a script can't cleanly check —
  whether the invented data is genuinely realistic and domain-specific (not just present),
  whether each page's content actually matches the brief's intent, whether the template/design-
  system references are used sensibly, whether the overall spec is something a build agent could
  implement well — a second model call ("the judge") is prompted with a fixed rubric, the
  original brief, and the generated spec, and returns **structured output**: a numeric score, a
  pass/fail verdict at a declared threshold, and a short rationale. Structured output (not free
  text) is what makes scores aggregable across runs.
- **The judge should be a separate concern from the model under test**, and ideally a different
  model instance, to reduce self-preference bias (a model preferring its own phrasing). This
  spec reuses the existing `build_model()` provider abstraction (`app/agents/model_factory.py`,
  already extended for Mistral per spec `004-groq-eval-provider`, now withdrawn) so the judge model is a
  normal, swappable config value — not hardcoded to whatever model generated the spec.
- **Every graded run is persisted as one row in an append-only store**, not just printed to a
  terminal and discarded. This is what turns "did this one run pass" into a trend: pass rate
  over time, regressions after a prompt edit, worst-scoring runs to inspect first. The existing
  harness already treats `backend/tests/evals/logs/` as disposable-per-run; the report is the
  new, cumulative layer on top.
- **Grading is opt-in and never free.** A judge call is a second real model call — it costs
  tokens and (per this repo's standing rule — see project memory) must never be triggered
  automatically by an agent. It is invoked exactly when a human runs a live eval, exactly like
  today's `--live` flag.

## 2. User Scenarios & Acceptance Criteria

### Story 1 — Stand up the model-graded eval branch, proven via `prototype-specify` (Priority: P1)

As an engineer, I want a new, generic model-graded eval branch that can dispatch a prompt to any
named (already-registered) agent via the existing `create_runner` implementation and capture its
raw response — independent of the existing file-editing-shaped live harness, and reusing rather
than rebuilding the pipeline-agent dispatch mechanism (resolved, see `clarifications.md` Q9) —
and I want it proven end to end by onboarding `prototype-specify` (which has zero eval coverage
today) as its first example, using only data (scenario YAML + rubric text), no new Python.

**Why P1**: Blocking prerequisite — Stories 2–4 have nothing to run against without this, and the
branch needs at least one working example to be more than scaffolding.

**Acceptance Scenarios**:
1. **Given** `backend/tests/evals/model_graded/` (new, standalone from `workflow/`), **When** a
   scenario names an `agent_id` and a prompt, **Then** the generic driver dispatches that prompt
   to the named agent via `create_runner` and captures its raw response text as the deliverable —
   with no sandbox-file-seeding or file-read-back assumption baked into the driver itself (unlike
   `common/live_scenario.py::run_live_scenario_once`, which stays exactly as-is, untouched, for
   the existing revision-agent track).
2. **Given** `model_graded/agents/prototype_specify/` (the first onboarded example — one folder
   per agent under the new branch, so a second agent added later is a sibling folder, not a
   change to shared code), **When** its scenario(s) are run through the generic driver, **Then**
   `prototype-specify` produces a `<spec>...</spec>` response captured correctly by the driver.
   Q4's original "exactly one scenario" decision is **superseded** (resolved, see
   `clarifications.md` Q15): scenarios now come from a `_template.yaml` (shared, generic
   precheck/rubric config) paired with a `dataset.json` array of `{id, industry, prompt}`
   entries — one `GradedScenario` per entry, `scenario_discovery.py::load_dataset_scenarios()`.
   `prototype-specify` ships with 11 entries spanning 11 industries (SaaS billing, healthcare,
   logistics, e-commerce, education, real estate, fintech, HR, manufacturing, legal,
   hospitality). Adding prompt #12 is one new `dataset.json` entry — zero new Python or YAML.
3. **Given** the generic, YAML-configured deterministic pre-check built into the framework
   (resolved, see `clarifications.md` Q10 — no per-agent Python required for this), **When** a
   generated spec response is checked, **Then** it verifies, purely from the scenario's
   `precheck:` config block: the response is wrapped in the configured tag (`<spec>...</spec>`)
   with no preamble/postamble text, a minimum section count is met (page count, via counting the
   configured heading pattern — flat minimum of 4, or the scenario's own `min_pages` override,
   per `clarifications.md` Q2), and none of the configured forbidden placeholder strings appear.
   **Given** `prototype-specify`'s one check the generic config cannot express — every navigation
   target referenced in the "Pages & Navigation" table having a corresponding page specification
   section, which needs real parsing, not a count/substring check — **Then** its scenario YAML
   declares an optional custom `precheck_module` hook for that one check only, not a full
   replacement of the generic config. This pre-check is a per-scenario plug-in point in the
   branch's design (config by default, code only as an escape hatch) — a second agent supplies
   its own `precheck:` block and, only if it needs one, its own narrow custom hook.

---

### Story 2 — LLM-as-judge grades a graded `prototype-specify` run (Priority: P1)

As an engineer iterating on `prototype-specify`'s prompt, I want each run through the new
model-graded branch graded by a judge model against the original brief — not just checked by the
new deterministic pre-check — so I know not just "is the document well-formed" but "is this
actually a good spec a build agent could implement well."

**Why P1**: The core capability the spec exists to add.

**Acceptance Scenarios**:
1. **Given** a run through `model_graded/driver.py` has completed (Story 1) — producing the
   brief, the `prototype-specify` system prompt actually used, and the raw `<spec>...</spec>`
   response — **When** grading is requested (opt-in — see Story 4), **Then** a judge model call
   is made with all three of those plus the pre-check's verdict, and returns a structured result:
   a score (0–100), a pass/fail verdict against a declared threshold, and a written rationale
   that speaks to content quality (realistic/domain-specific data, brief-intent match, template/DS
   usage), not just structural well-formedness (which the pre-check already covers).
2. **Given** the judge call fails (network error, malformed structured output), **When** grading
   is requested, **Then** the run's pre-check-based pass/fail result is still reported (grading
   failure never masks or blocks the existing deterministic result) and the judge fields are
   recorded as errored, not silently omitted.
3. **Given** a run where the pre-check already reports PASS (well-formed, right page count, no
   placeholders), **When** the judge grades it, **Then** the judge can still report a lower score
   (e.g. technically compliant but generic/shallow content, or pages that don't actually fit the
   brief) — the two signals are independent and both surfaced, not collapsed into one.

---

### Story 3 — Per-run report files, readable in place (Priority: P1)

**Revised** (resolved, see `clarifications.md` Q12 — supersedes the original single shared
`eval_report.jsonl` design below, which the user found unreadable: a single-line JSON blob per
run, full response inlined, unusable opened directly).

As an engineer, I want every run's record readable on its own, without wading through a
giant shared file — so I can review eval history without re-running anything.

**Why P1**: Grading a single run (Story 2) without persisting it doesn't answer the user's
actual ask — reviewable eval history over time.

**Acceptance Scenarios**:
1. **Given** a `graded` invocation completes, **When** it finishes, **Then** a `run.json` is
   written into that run's own `model_graded/logs/<run_id>/` folder (pretty-printed, `indent=2`)
   containing: timestamp, `run_id`, scenario id, agent id, requested `provider`/`model`, the
   **actually resolved** `resolved_model_id` (off the built model instance — always populated,
   even when `provider`/`model` were never passed — resolved, see `clarifications.md` Q14), the
   system prompt path + content-hash, the brief/prompt text, the generated response (inlined —
   no separate artifact file exists for this branch's deliverable), the pre-check verdict +
   reason, and token counts. Written for **every** `graded` invocation, judged or not.
2. **Given** `--judge` was passed, **When** grading completes, **Then** a `grade.json` is
   written alongside `run.json` in the same run folder: judge score, pass/fail, **strengths:
   []**, **weaknesses: []** (resolved, see `clarifications.md` Q13 — not just one prose
   rationale paragraph), rationale, `judge_resolved_model_id`, and errored state.
3. **Given** many runs exist across many folders, **When** the report is summarized, **Then**
   it is a **computed view** (`report.py::load_run_entries()` scans every run folder and merges
   `run.json` + `grade.json`) — there is no separate accumulating store to keep in sync; a bad
   entry is a normal git diff on one small file, not a corrupted shared file.

---

### Story 4 — Reachable from the existing `./tests/evals/eval.sh` entry point (Priority: P2)

As an engineer, I want the new model-graded branch reachable via the same `./tests/evals/eval.sh` entry
point I already use, rather than a separate script to learn, while keeping it as a distinct
`graded` subcommand rather than a flag grafted onto the unrelated existing `--live`/`benchmark`
commands (which stay exactly as they are).

**Why P2**: Supporting/integration work — Stories 1–3 are the actual capability; this is what
makes it reachable without a second invocation surface.

**Acceptance Scenarios**:
1. **Given** `./tests/evals/model_graded/model-graded.sh graded <scenario-id>`, **When** run without `--judge`, **Then** the
   scenario runs through the driver and pre-check only (no judge call, no report entry — a free
   sanity check, mirroring how a bare scenario name never spends tokens on the existing track);
   **When** `--judge` is also passed, **Then** the run is graded per Story 2 and appended to the
   report per Story 3. `--samples N` (default 1) is available on both forms and repeats the same
   scenario N times, one independent report entry each when `--judge` is set (Story 6).
2. **Given** the existing `./tests/evals/eval.sh <scenario-id> --live` and `benchmark` commands, **When**
   this spec ships, **Then** their behavior is completely unchanged — the new `graded`/`report`
   subcommands are additions, not modifications, to `./tests/evals/eval.sh`.
3. **Given** no `ANTHROPIC_API_KEY`/Bedrock/Mistral credential resolves to a usable judge
   model, **When** `--judge` is passed, **Then** the CLI fails fast with a clear error before
   spending any tokens on the run itself under test — not after.

---

### Story 5 — Report summary / aggregate view (Priority: P2)

As an engineer, I want to see an aggregate "percentage good" across the accumulated report —
overall and broken down per scenario — so I can answer "is this prompt getting better or worse"
without manually reading every entry.

**Why P2**: The report from Story 3 is only useful as raw data until it can be summarized;
without this, each entry has to be read by hand to spot a trend.

**Acceptance Scenarios**:
1. **Given** a populated report store, **When** a summary command is run
   (`./tests/evals/model_graded/model-graded.sh report`), **Then** it prints: total graded runs, overall pre-check pass rate,
   overall judge pass rate (at the declared score threshold), and average judge score — both in
   aggregate and broken out per agent id and per scenario id (a single agent today —
   `prototype-specify` — but the breakdown is by field, not hardcoded to it).
2. **Given** the summary command, **When** run with a `--last N` or date-range filter, **Then**
   it summarizes only that subset of entries (so a prompt-change comparison isn't polluted by
   older runs against a prior prompt version).
3. **Given** an empty report store (no graded runs yet), **When** the summary command runs,
   **Then** it reports zero entries clearly rather than erroring.

---

### Story 6 — Iterative prompt-improvement loop: multi-sample runs, feedback, and version
tracking (Priority: P1)

As an engineer running the Standard Operating Procedure above, I want to run a scenario N times
in one invocation (so a "percentage" is statistically meaningful, not one coin-flip), pull up
the worst-scoring runs' rationale as concrete feedback, and see whether my score actually
improved after editing the prompt — all without any of it happening automatically.

**Why P1**: This is the loop the user explicitly asked for (`clarifications.md` Q5) — without
it, the branch can grade one run at a time but cannot support the "create dataset → grade →
feedback → improve → repeat" procedure that is this spec's actual purpose, not an add-on to it.

**Acceptance Scenarios**:
1. **Given** `./tests/evals/model_graded/model-graded.sh graded <scenario-id> --judge --samples N`, **When** the command
   runs, **Then** the scenario is dispatched to the agent N times sequentially (mirroring the
   existing `benchmark` command's own N-run shape on the deterministic track), each run is
   independently pre-checked and judged, and each gets its own report entry — no batching or
   averaging that would lose per-run detail (consistent with the existing per-run granularity
   principle already established for the deterministic track's `benchmark` command). The command
   prints a running pass rate (pre-check and judge, separately) as it goes, and a final summary
   line at the end.
2. **Given** a populated report, **When** `./tests/evals/model_graded/model-graded.sh report --worst N` is run, **Then** it
   prints the N lowest-`judge_score` entries in full — prompt, response (or a readable excerpt),
   and judge rationale — sorted worst-first, with no synthesis or suggested fix (resolved, see
   `clarifications.md` Q6: raw evidence for a human to read, never a proposed prompt edit).
3. **Given** report entries spanning more than one `system_prompt_hash` (i.e. `AGENT.md` was
   edited between runs), **When** `./tests/evals/model_graded/model-graded.sh report` is run, **Then** the summary breaks
   down average judge score and pass rate **per `system_prompt_hash`**, in chronological order,
   so a score change between prompt versions is visible without manual diffing of the JSONL
   (resolved, see `clarifications.md` Q7). **Given** an optional `--target T` is also passed,
   **Then** each prompt-version row additionally prints whether it clears `T` ("TARGET MET" /
   "TARGET NOT MET (81% < 90%)") — no automated re-run or stop condition is triggered by this;
   it only changes what gets printed.
4. **Given** any of the above, **When** the loop is repeated for a second agent (a different
   `model_graded/agents/<agent>/` folder), **Then** every capability in this story works
   identically — `--samples`, `--worst`, `--target`, and the `system_prompt_hash` grouping are
   all agent-agnostic (no code path here reads `agent_id` to special-case behavior).

---

## 3. Technical Design

### 3.1 Tech Stack Context

From `.apex/stack.json`:
- **Language**: Python (this feature is entirely backend eval-tooling; no frontend/TypeScript
  surface).
- **Framework**: none of FastAPI/React apply directly — this is a `pytest`/CLI-adjacent tooling
  addition inside `backend/tests/evals/`, following that folder's existing non-pytest-driven
  scripts (`live_benchmark.py`, `validate_scenario.py`, `dump_prompts.py`).
- **Database**: PostgreSQL is unaffected — the report store is a flat JSON Lines file
  files inside each run's own log folder (`clarifications.md` Q12), consistent with how `logs/`
  outside the database. No migration needed.
- **Version constraints**: use the existing `build_model()` provider abstraction as-is
  (Anthropic/Bedrock/Mistral, per the withdrawn spec `004-groq-eval-provider`); no new model SDK
  dependency required — the judge is just another `build_model()` call with a structured-output
  request (existing LangChain `with_structured_output`/Pydantic pattern already available via
  `langchain-core`).

### 3.2 Architecture Fit

Purely additive: a brand-new `backend/tests/evals/model_graded/` package, standing alongside the
existing `common/` + `workflow/` deterministic track. **`common/live_scenario.py` and
`workflow/prototype/revision/` are untouched by this spec** — no shared code is modified, no
mode flag is added to the existing driver, and the two tracks stay independently runnable and
independently understandable. No changes to `agents/factory.py`, `DeepAgentRunner`, or
production code paths. Six new pieces:

1. **`model_graded/driver.py`** (new) — the generic driver. Exposes
   `run_graded_scenario_once(scenario: GradedScenario, *, provider=None, model=None) ->
   GradedRunResult`: builds an `AgentContext` from `scenario.prompt`, calls
   `create_runner(scenario.agent_id, ctx)`, streams the response exactly like
   `live_scenario.py` already does (same event/log-file conventions — `log.txt` per run under
   `model_graded/logs/<run_id>/`, reusing the pattern, not the code), and returns the raw
   response text plus token counts. No sandbox file seeding, no file read-back — every agent
   onboarded onto this branch is invoked the same, minimal way regardless of its own shape,
   which is what makes a second agent later a pure data addition.
2. **`model_graded/precheck.py`** (new, **generic**, shared by every agent — resolved, see
   `clarifications.md` Q10) — one function, `run_precheck(response: str, config: dict) ->
   tuple[bool, str]`, driven entirely by a scenario's `precheck:` YAML block: a required wrapper
   string/tag (`wrapper: "<spec>"`), a minimum count of a configurable heading pattern
   (`min_sections: 4`, `section_pattern: "^### "`), and a list of forbidden substrings
   (`forbidden: ["Lorem ipsum", "TBD", "Coming soon", "future expansion"]`). No agent-specific
   code lives here — this module has no idea `prototype-specify` exists.
3. **`model_graded/agents/prototype_specify/`** (new — first example; one folder per agent under
   this branch going forward) — `scenarios/*.yaml` (`agent_id: prototype-specify`, the brief, a
   `precheck:` config block per item 2 — wrapper `<spec>`, `min_sections`/`section_pattern`
   tuned to `AGENT.md`'s page-heading format, forbidden placeholder strings, an optional
   `min_pages` override defaulting to 4 per `clarifications.md` Q2 — a `rubric:` text block per
   item 4, and an optional template/design-system fixture), plus **one narrow custom hook**,
   `nav_cross_reference_check.py` (a single function, not a full `precheck.py` module — the one
   check the generic config in item 2 cannot express: every navigation target referenced in the
   "Pages & Navigation" table having a corresponding page specification section, which needs real
   parsing), wired via the scenario YAML's optional `precheck_module:` field.
4. **`model_graded/judge.py`** (new) — the grading module, generic over agent. Exposes
   `grade_run(scenario: GradedScenario, result: GradedRunResult, *, provider=None, model=None) ->
   JudgeVerdict`. Builds a judge model via `build_model()` — **default**: no forced distinct
   provider, the same fallback chain every other caller uses (resolved, see `clarifications.md`
   Q1 — keeps `--judge` frictionless on a machine with only `ANTHROPIC_API_KEY` configured, the
   normal local-dev case), overridable via `provider=`/`model=` (surfaced as `--judge-provider`/
   `--judge-model` on the CLI — §3.4) when a distinct judge model is wanted to reduce
   self-preference bias. Builds the grading prompt via **one shared prompt-builder function**
   (not a per-agent module — resolved, see `clarifications.md` Q10) from the agent's system
   prompt + the prompt + the response + the scenario's own `rubric:` text block, and parses a
   structured response into a `JudgeVerdict` dataclass: `score: int` (0–100), `passed: bool`
   (score ≥ `DEFAULT_JUDGE_THRESHOLD = 70`, a single global module-level constant — resolved, see
   `clarifications.md` Q3, not a per-agent value — overridable per-run via `--judge-threshold`),
   `rationale: str`, `errored: bool`, `error_reason: str | None`. For `prototype-specify`, its
   `rubric:` text explicitly asks the judge to assess what the pre-check cannot: data
   realism/specificity, brief-intent match per page, and template/design-system usage — not to
   re-check structural facts the pre-check already covers.
5. **`model_graded/report.py`** (new) — the persistent store, agent-agnostic. `append_entry(...)`
   writes `run.json`/`grade.json` into the run's own `model_graded/logs/<run_id>/` folder (per
   shared file across every agent onboarded onto the branch, distinguished by `agent_id` per
   entry — Story 5's per-scenario/per-agent breakdown reads off that field);
   `summarize(entries, *, group_by="agent_id"|"scenario_id"|"system_prompt_hash", target=None)`
   computes the aggregate stats for Story 5 and, when grouped by `system_prompt_hash`, the
   per-prompt-version trend and optional target-met line for Story 6 (resolved, see
   `clarifications.md` Q7); `worst(entries, n)` returns the `n` lowest-`judge_score` entries in
   full, for Story 6's feedback view (resolved, see `clarifications.md` Q6 — raw entries only, no
   synthesis). Report entry schema (one JSON object per line):
   ```json
   {
     "timestamp": "2026-07-28T15:08:02Z",
     "run_id": "260728150802-graded-prototype_specify_admin_console-c076d1ce",
     "scenario_id": "prototype_specify_admin_console",
     "agent_id": "prototype-specify",
     "provider": null,
     "model": null,
     "system_prompt_path": "backend/agents/prompts/prototype-specify/AGENT.md",
     "system_prompt_hash": "sha256:...",
     "prompt": "Build an admin console for a SaaS billing platform...",
     "response": "<spec>\n# Prototype Specification: ...\n</spec>",
     "run_dir": "backend/tests/evals/model_graded/logs/260728150802-graded-prototype_specify_admin_console-c076d1ce",
     "precheck_passed": true,
     "precheck_reason": "...",
     "judge_score": 82,
     "judge_passed": true,
     "judge_rationale": "...",
     "judge_errored": false,
     "tokens_in": 1234,
     "tokens_out": 3456
   }
   ```
   The system prompt is stored by path + content hash (not inlined in full on every entry) —
   `AGENT.md` can be several KB and is already version-controlled; the hash lets a report reader
   detect "this entry's prompt version differs from the current file" without bloating every
   line. The generic driver captures a raw text response with no separate on-disk artifact to
   point to (Story 3 Acceptance Scenario 1) — the full response is stored directly in the entry,
   with `run_dir` kept alongside for the full transcript/log. This shape is agent-agnostic: a
   second agent's entries look identical except for `agent_id`/`system_prompt_path`/rubric
   content.
6. **`model_graded/cli.py` (or a `./tests/evals/eval.sh` subcommand delegating to it)** — the entry point
   (Story 4): `./tests/evals/model_graded/model-graded.sh graded <scenario-id> [--judge] [--samples N]` runs one scenario
   through the driver N times (default 1), optionally grades each run, and appends each to the
   report; `./tests/evals/model_graded/model-graded.sh report [--last N] [--worst N] [--by system_prompt_hash] [--target T]`
   scans every run folder via `report.py::load_run_entries()` and prints
   Story 6). Kept as a **new** subcommand namespace (`graded`), not a flag bolted onto the
   existing `--live`/`benchmark` commands, so the two tracks' CLI surfaces stay as separable as
   their code.

### 3.3 Data Model Changes

None — no PostgreSQL schema changes. The report store is a flat file
— per-run `run.json`/`grade.json` files (`clarifications.md` Q12), matching the existing precedent
`backend/tests/evals/logs/` living outside the database.

### 3.4 API Design

No new HTTP/WebSocket endpoints — this is developer-facing CLI tooling only, invoked via
`./tests/evals/eval.sh`, matching every other file in `backend/tests/evals/`. New internal
functions/CLI surface, entirely under the new `model_graded/` package:
- `model_graded/driver.py::run_graded_scenario_once(scenario, *, provider=None, model=None) ->
  GradedRunResult`
- `model_graded/judge.py::grade_run(scenario, result, *, provider=None, model=None) ->
  JudgeVerdict`
- `model_graded/report.py::append_entry(entry: dict) -> None`
- `model_graded/report.py::summarize(entries, *,
  group_by="agent_id"|"scenario_id"|"system_prompt_hash", last_n=None, target=None) -> dict`
- `model_graded/report.py::worst(entries, n: int) -> list[dict]`
- `./tests/evals/model_graded/model-graded.sh graded <scenario-id> [--judge] [--samples N] [--judge-provider P]
  [--judge-model M] [--judge-threshold T]` — `--samples` defaults to 1 (Story 6, resolved per
  `clarifications.md` Q5); the judge-related flags are only meaningful with `--judge`; default
  judge is the same `build_model()` fallback chain as the agent under test, threshold defaults to
  70 (`clarifications.md` Q1, Q3).
- `./tests/evals/model_graded/model-graded.sh report [--last N] [--worst N] [--by system_prompt_hash] [--target T]` — `--worst`
  and `--by system_prompt_hash`/`--target` resolved per `clarifications.md` Q6, Q7.

### 3.5 Component / Module Design

- `tests/evals/model_graded/driver.py` — new: `GradedScenario`/`GradedRunResult` dataclasses,
  `run_graded_scenario_once()` (dispatch via `create_runner`, no filesystem assumptions —
  `clarifications.md` Q9).
- `tests/evals/model_graded/precheck.py` — new: **generic**, `run_precheck(response, config)`,
  driven entirely by a scenario's `precheck:` YAML block (wrapper tag, min section count,
  forbidden substrings) — no agent-specific code (`clarifications.md` Q10).
- `tests/evals/model_graded/judge.py` — new: `JudgeVerdict` dataclass, `grade_run()`, and **one
  shared** rubric-prompt-builder function that takes a scenario's `rubric:` text as a plain
  string argument — not a per-agent module lookup (`clarifications.md` Q10).
- `tests/evals/model_graded/report.py` — new: `append_entry()`, `summarize()`, `worst()`, JSONL
  read/write helpers, agent-agnostic.
- `tests/evals/model_graded/scenario_discovery.py` — new: discovers every
  `model_graded/agents/*/scenarios/*.yaml`, mirroring the existing
  `common/scenario_discovery.py` pattern but scoped to this branch (kept separate rather than
  extending the existing one, since the two tracks' `LiveScenario`/`GradedScenario` shapes
  differ). Also resolves each scenario's `precheck:` config and `rubric:` text, and loads its
  optional `precheck_module:` custom hook when declared.
- `tests/evals/model_graded/agents/prototype_specify/` — new (first example agent folder):
  `scenarios/*.yaml` (with inline `precheck:` config and `rubric:` text — no Python needed for
  either), plus one narrow custom hook, `nav_cross_reference_check.py`, for the single check the
  generic `precheck.py` config cannot express.
- `tests/evals/model_graded/cli.py` — new: implements the `graded`/`report` subcommands.
- `./tests/evals/eval.sh` — add `graded` and `report` subcommand dispatch to
  `model_graded/cli.py`, alongside (not replacing) the existing commands.
- No separate `reports/` directory — `run.json`/`grade.json` live in each run's own `logs/<run_id>/`
  run and committed to the repo (git-trackable eval history).
- `backend/tests/evals/model_graded/logs/` — new; per-run transcript folders, mirroring
  `tests/evals/logs/`'s convention but under the new branch.

## 4. Non-Functional Requirements

| Requirement | Target | Measurement |
|------------|--------|-------------|
| Cost | Grading only runs when `--judge` is explicitly passed; the `graded` command with no `--judge` is a free (no judge call) driver+pre-check run, like the existing track's default | Manual/opt-in — never auto-invoked by an agent, per standing project rule |
| Judge determinism | Judge model called at low/zero temperature where the provider supports it, to reduce score variance run-to-run for the same input | Manual spot-check: same brief/response pair graded twice yields scores within a small tolerance |
| Backward compatibility | Zero behavior change to `common/live_scenario.py`, `workflow/prototype/revision/`, `live_benchmark.py`, or the existing `./tests/evals/eval.sh` commands — the new branch is purely additive, sharing no modified code with the existing track | Existing eval scripts, the current `prototype_multi_issue_repair` scenario, and `tests/agents/`/`tests/unit/` suites pass unmodified |
| Report integrity | Append-only; a failed/errored judge call still produces a report entry (with `judge_errored: true`), never a skipped or corrupted line | Unit test asserts one well-formed JSON line is written even when the judge call raises |
| Judge default/threshold | No forced distinct judge provider by default (same fallback chain as the agent under test); pass/fail threshold is a single global constant (70), not per-agent | `clarifications.md` Q1, Q3 — verified by `judge.py`'s default `build_model()` call taking no `provider=` override and `DEFAULT_JUDGE_THRESHOLD` being module-level, not scenario/agent-scoped |
| Test Coverage | New `driver.py`/`precheck.py`/`judge.py`/`report.py` modules and `prototype_specify`'s scenario YAML config + `nav_cross_reference_check.py` covered by unit tests (mocked model calls, no network; JSONL read/write round-trip) | `pytest backend/tests/unit/` and/or `tests/evals/model_graded/` |
| Zero-code onboarding | A new agent/prompt requires only a new scenario YAML (`precheck:` config + `rubric:` text) — no new Python file, unless a scenario needs a custom precheck hook beyond the generic config | `clarifications.md` Q10 — verified by `prototype-specify`'s own scenario needing exactly one custom hook (nav cross-reference), not a full `precheck.py`/`rubric.py` pair |
| Loop stays human-in-the-loop | `--samples`, `report --worst`, and `report --target` never trigger a model call, a re-run, or a prompt edit on their own — every iteration of the Standard Operating Procedure (§1) is a separate, explicit CLI invocation | `clarifications.md` Q5/Q6/Q7 — verified by `worst()`/`summarize()` being pure read functions over the existing JSONL, with no code path that calls `run_graded_scenario_once`/`grade_run`/writes to `AGENT.md` |

## 5. Out of Scope

- Onboarding any agent other than `prototype-specify` onto the new branch in this spec — it's
  the first example, proving the branch end to end; `prototype-revision-agent` keeps its
  existing deterministic-only coverage on the separate, untouched `workflow/` track. Other
  pipeline agents (`prototype-plan`, `prototype-build`, `prototype-tasks`,
  `prototype-validate`, etc.) are likewise out of scope for this spec, but the branch's
  per-agent-folder design (§3.5) is what makes each of them a follow-on data addition rather
  than a redesign.
- A frontend/dashboard UI for browsing the report — v1 is a flat JSONL file plus a CLI summary
  command, not a web view.
- Moving the report into PostgreSQL or any database-backed store.
- CI gating / automatically failing a build on a low judge score — grading stays a manual,
  opt-in developer action, never wired into CI or run automatically by an agent (per the user's
  standing instruction that live-model eval runs are always manual).
- Pairwise/head-to-head comparison grading (judging two candidate spec documents against each
  other) — this spec only covers single-response absolute scoring against a rubric.
- Multi-judge ensembling (querying several judge models and combining scores) — out of scope for
  v1; the design's `provider=`/`model=` parameters leave room for it later without a rework.
- Automated prompt editing / an unattended improve-and-re-run loop — Story 6 covers multi-sample
  runs, feedback surfacing, and prompt-version score tracking, all human-invoked per iteration;
  the tool never edits `AGENT.md` itself and never re-runs on its own (resolved, see
  `clarifications.md` Q5/Q6/Q7 — ruled out for the same standing-rule reason live-model runs are
  always manual). **Note**: an earlier pass at this spec listed "a `benchmark`-style multi-run
  command" as out of scope entirely; that is superseded by Story 6/`clarifications.md` Q5 — N-run
  sampling (`--samples`) is now in scope, only full automation of the edit/re-run cycle stays out.

## 6. Dependencies & Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Building an entirely new branch (`model_graded/`) rather than extending the proven `workflow/` track means this spec is doing first-of-its-kind setup, not just adding a judge to existing scaffolding | High (known going in — this is the deliberate tradeoff for keeping the two tracks independent, per explicit direction) | Medium — more surface area than a pure grading add-on | Explicitly scoped as Story 1/P1; borrows the proven `workflow/prototype/revision/` conventions (log-folder shape, YAML scenario format, opt-in cost model) wherever they transfer, without coupling code to that track |
| Judge model self-preference bias (scoring generously because the judge and the agent under test share model lineage) | Medium | Medium — inflated scores mask real quality regressions | Default judge provider/model is configurable independent of the agent's model via existing `build_model(provider=, model=)`; document choosing a different provider/model as the judge where practical |
| Judge scoring is non-deterministic (LLM variance) | Medium | Low — a single graded run's score may wobble a few points | Story 5's aggregate/summary view (average over multiple runs) is the intended way to read judge scores, not any single run in isolation |
| Structured-output parsing failures from the judge call | Low | Low | `JudgeVerdict.errored` path (Story 2 Acceptance Scenario 2) ensures a parse failure degrades to "ungraded" rather than crashing the run or corrupting the report |
| Report file grows unbounded over time (git-tracked JSONL), and inlining full spec responses (Story 3) makes lines larger than the file-referenced revision-agent equivalent would be | Low | Low | Out of scope for v1 rotation/archival; flagged here for a future spec if the file becomes unwieldy |
