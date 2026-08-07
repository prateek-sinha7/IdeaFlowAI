# Research Notes: Model-Graded Eval Branch (LLM-as-Judge + Report)

## Decision Log

### Topic: How should model-based ("LLM-as-judge") grading be structured?

- **Options considered**:
  1. Free-text judge output, parsed with regex/heuristics.
  2. Structured output (Pydantic/JSON schema) with a numeric score + verdict + rationale.
  3. Pairwise/comparative grading (judge picks the better of two candidate responses).
- **Recommended choice**: (2) — structured, single-response absolute scoring against a fixed
  rubric.
- **Rationale**: This is the convergent pattern across OpenAI Evals, the Anthropic eval
  cookbook, and Arize Phoenix/traceloop-style pipelines (see spec §1 Background). Structured
  output is what makes scores aggregable across runs (Story 5's "percentage good" requires a
  numeric field, not prose to re-parse every time). Pairwise grading (3) is a real technique but
  requires two candidate responses per judged unit — this repo doesn't generate variant
  candidates today, so it's explicitly out of scope (spec §5) rather than a real alternative for
  v1.

### Topic: Should the new branch reuse `common/live_scenario.py`, or build a new driver?

- **Options considered**:
  1. Add an `output_mode: "file" | "text"` field to the existing `LiveScenario`/
     `run_live_scenario_once`, branching internally.
  2. Build a new, standalone `model_graded/driver.py` with its own dataclasses, sharing no code
     with the existing driver.
- **Recommended choice**: (2).
- **Rationale**: Explicit user direction mid-spec ("this is a new branch of eval... totally
  different than what we already have"). Beyond the direction itself, (1) would have coupled two
  conceptually distinct tracks (deterministic-only vs. model-graded) through one shared function
  with an internal mode switch — a well-known smell (the function's contract becomes "it depends
  which mode") that (2) avoids entirely. `prototype-specify`'s text-only shape (`tools: []`) also
  doesn't fit the existing driver's core assumption (a sandbox file gets edited and read back)
  cleanly enough to be a "mode," it's a genuinely different invocation shape.

### Topic: Judge model selection — same model as the agent under test, or forced distinct?

- **Options considered**: see `clarifications.md` Q1 (A: same fallback chain default,
  overridable; B: forced distinct provider by default; C: no default, explicit flag required).
- **Recommended choice**: A.
- **Rationale**: Full writeup in `clarifications.md` Q1. Summary: forcing a second provider by
  default adds a hard dependency (Mistral credentials) to the common `--judge` path that
  the existing harness has never required for its zero-friction default, and would silently fail
  on any machine that only has `ANTHROPIC_API_KEY` configured (true of this repo's normal local
  dev setup per `backend/CLAUDE.md`).

### Topic: Deterministic pre-check scope for `prototype-specify`

- **Options considered**: see `clarifications.md` Q2 (flat minimum vs. app-type-aware keyword
  inference vs. scenario-declared minimum).
- **Recommended choice**: flat `min_pages` floor (default 4) + optional scenario-level override.
- **Rationale**: A deterministic, no-model-call function should never need a judgment call
  (inferring "is this brief an e-commerce app" from free text is exactly that). This division of
  labor — pre-check verifies facts, judge assesses everything requiring interpretation — is the
  spec's own stated principle (§1 Background, "Deterministic checks stay deterministic").

### Topic: Should the grader dispatch via `create_runner`, or a raw chat-completion call to the
provider API directly?

- **Options considered**: see `clarifications.md` Q9 (dispatch mechanism: raw call / keep
  `create_runner` / hybrid via optional `--agent-id`) and Q11 (revisiting Q9 directly: "what's
  the actual benefit").
- **Recommended choice**: keep `create_runner` — reused as-is, never bypassed.
- **Rationale**: Two independent reasons, not one. (1) Future agents onboarded onto this branch
  will need real tool execution to verify they produced a *correct* result (the user's own
  stated reason for Q9). (2) — surfaced only when directly challenged in Q11 — `prototype-
  specify`'s own `AGENT.md` frontmatter declares `injects: [template, design_system, images]`,
  meaning its body text is not the full production system prompt; only `create_runner`'s
  `_compose_system_prompt`/`_compose_injection` assemble the real one. A raw chat call would
  either grade an incomplete prompt, or require re-implementing that composition logic — which
  is *more* new code than reusing the existing implementation, undermining the "no new code for
  a new agent" goal this framework exists to satisfy. (2) applies to `prototype-specify` today,
  not just hypothetical future tool-using agents, so it's the stronger of the two arguments.

### Topic: Should the judge rubric and deterministic pre-check be Python modules per agent, or
data/config?

- **Options considered**: see `clarifications.md` Q10 (A: data-driven for both, with an optional
  custom precheck hook as an escape hatch; B: both required Python per agent — the original
  design; C: data-driven rubric only, precheck stays required Python).
- **Recommended choice**: A.
- **Rationale**: The user's actual "I don't want to create new code for a new agent or prompt"
  friction turned out to be here, not at the dispatch layer (Q9 confirmed dispatch stays as
  `create_runner`, unchanged). A generic, YAML-configured pre-check (`precheck.py::run_precheck`)
  covers wrapper-tag/min-section-count/forbidden-substring checks — the common case for any
  text-completion agent — with zero per-agent Python. A single shared judge-prompt-builder,
  parameterized by a scenario's own `rubric:` text block, does the same for grading criteria. An
  optional `precheck_module` hook remains for checks the generic config genuinely can't express
  (`prototype-specify`'s nav-target-to-page-section cross-reference needs real parsing) — kept
  deliberately narrow (one function) rather than reopening the door to a full custom module per
  agent.

### Topic: Report storage format

- **Options considered**:
  1. PostgreSQL table.
  2. SQLite file.
  3. Flat JSON Lines file, git-tracked.
- **Recommended choice**: (3).
- **Rationale**: Matches the existing precedent of `backend/tests/evals/logs/` living outside
  the database as plain files. JSONL is diff-friendly and readable with `cat`/`jq` with zero
  extra tooling (Story 3 Acceptance Scenario 3), and this is developer-facing eval-tooling data,
  not application data — a PostgreSQL migration would be disproportionate machinery for it
  (spec §3.3 explicitly rules this in/out).

## Unknowns

- **Judge rubric wording for `prototype-specify`'s `rubric:` YAML block** — the spec states
  *what* the judge should assess (data realism, brief-intent match per page, template/DS usage)
  but the exact prose, scoring granularity (sub-scores per dimension vs. one holistic score),
  and any few-shot examples are an implementation-time detail for Phase 2, informed by iterating
  against the one v1 scenario's actual outputs.
- **Exact `precheck:` YAML config schema** — field names for the wrapper string, the
  section-count pattern/minimum, and the forbidden-substring list are an implementation choice
  for Phase 1 (§File Changes in `plan.md` sketches `wrapper:`/`min_sections:`/
  `section_pattern:`/`forbidden:` as a starting shape, not a locked contract).
- **Exact YAML schema field names** for `model_graded/agents/prototype_specify/scenarios/*.yaml`
  more broadly (e.g. whether the brief is inline `prompt:` or a `prompt_file:` reference,
  matching the existing `instruction`/`instruction_file` dual-mode pattern in
  `workflow/prototype/revision/` scenario YAML) — left as an implementation choice for Phase 1.
- **Whether `run_graded_scenario_once` needs a `design_md`/template fixture parameter for the
  first scenario** — `prototype-specify` optionally consumes an injected template + design
  system (per its `injects` frontmatter, also the basis for Q11's composition-fidelity
  argument). The one v1 scenario may or may not need to supply these to be realistic; deferred
  to Phase 1 implementation.

## References

- `backend/agents/prompts/prototype-specify/AGENT.md` — the agent under evaluation; its own
  stated content/navigation/template-compliance rules are the basis for both the pre-check and
  the judge rubric.
- `backend/tests/evals/common/live_scenario.py`, `backend/tests/evals/workflow/prototype/revision/`
  — the existing deterministic track this new branch deliberately does not extend, but borrows
  conventions from (log-folder shape, YAML scenario format, opt-in cost model).
- `backend/app/agents/model_factory.py::build_model()` — the provider abstraction the judge
  reuses as-is.
- `specs/004-groq-eval-provider/README.md` — prior art for the `provider=`/`model=` opt-in override (that spec is WITHDRAWN; the opt-in mechanism survives, the Groq provider does not)
  pattern on eval-harness model calls; this spec's `--judge-provider`/`--judge-model` follows
  the same shape.
- `.investigations/free-models/` — repo-local research on free model providers, cited in spec §1
  as part of the "standard process" background for model-based grading.
- `backend/CLAUDE.md` — backend architecture guide; source for `create_runner`/`AgentContext`
  usage conventions and the `tests/evals/` folder-organization precedent this plan follows.
