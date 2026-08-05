# Clarifications: 005-prompt-eval-scoring

Resolved during `/apex:clarify`. Each item below has been folded back into `spec.md` — this
file is the record of *why*, kept for future reference (matches the convention already used by
the withdrawn `specs/004-groq-eval-provider/`).

---

## Q1 — What model/provider is the judge by default?

**Context**: §3.2 item 3 (`model_graded/judge.py`) says the judge is built via `build_model()`,
"overridable via `provider=`/`model=`," and the Risks table flags self-preference bias (a model
grading generously because it shares lineage with the model under test) as a real risk — but the
spec never actually states what the judge uses when no override is passed.

**Options**:
- **A. Same fallback chain as the agent under test (no forced distinct provider).** Zero extra
  setup — works with whatever credentials are already configured (per the backend `CLAUDE.md`,
  local dev is `ANTHROPIC_API_KEY` → Haiku). Self-preference bias risk stays live by default,
  but `provider=`/`model=` remains available to point the judge elsewhere when that risk matters
  for a specific comparison.
- **B. Force a different provider by default (e.g. Mistral via spec `004`) whenever
  credentials for one are available, falling back to A otherwise.**
- **C. Require `--judge-provider`/`--judge-model` explicitly — no default, hard error if omitted.**

**Recommendation**: **A**, with a documented override path (`--judge-provider`/`--judge-model` on
the `graded`/`report` CLI, matching `provider=`/`model=` already on `judge.grade_run()`). Forcing
a second provider by default (B) adds a hard dependency on Mistral credentials being present
just to run a smoke check, which conflicts with Story 4's "free sanity check" framing for the
no-`--judge` path and would make the `--judge` path fail on machines that only have
`ANTHROPIC_API_KEY` — a worse default than the existing track's own zero-friction bar. Requiring
an explicit flag always (C) adds friction to the common case for a bias risk that's real but
secondary. A keeps the default frictionless and documents the override for when it matters —
consistent with how the risk is already framed as "mitigated by configurability," not "must be
prevented by default."

**Decision**: **A** — resolved into §3.2 item 3 and a new NFR row.

---

## Q2 — Deterministic pre-check page-count minimum: flat, or app-type-aware?

**Context**: Story 1 Acceptance Scenario 3 says the pre-check verifies "the page count meets the
minimum the brief's app type implies (≥4, per `AGENT.md`'s stated minimums)." But `AGENT.md`'s
minimums are type-specific prose ("Analytics dashboard: 5 pages," "E-commerce: 5 pages," "Any
other app: minimum 4 pages") — inferring "app type" from a free-text brief deterministically
(no model call) is unreliable, and the pre-check is specified as a **cheap, no-model-call**
function.

**Options**:
- **A. Pre-check enforces a flat minimum of 4 for every scenario, regardless of brief content.**
  Type-specific stricter minimums (5–6) become a judge-rubric concern instead — the judge reads
  the brief and can dock the score if a SaaS/e-commerce brief only got 4 generic pages.
- **B. Pre-check infers app type via simple keyword matching on the brief ("dashboard",
  "e-commerce", etc.) and enforces the matching stricter minimum.**
- **C. Each scenario YAML declares its own expected minimum page count explicitly** (a
  scenario-level field, not inferred at all).

**Recommendation**: **A** for the pre-check, **C** as a complementary scenario-level override
where a specific scenario wants to assert a known minimum. Keyword-based type inference (B) is
exactly the kind of fragile heuristic a "cheap, deterministic, no-model-call" pre-check is meant
to avoid — it would produce false pre-check failures on briefs that don't use the exact keywords
`AGENT.md` lists, undermining the "deterministic checks stay deterministic" principle from the
spec's own Background section (a pre-check should never need judgment calls). Delegating the
nuanced, type-aware standard to the judge (which already reads the brief in full) is the correct
division of labor per the spec's own stated split between pre-check and judge.

**Decision**: **A + C** — resolved into Story 1 Acceptance Scenario 3 and §3.2 item 2 (scenario
YAML schema gains an optional `min_pages` field, defaulting to 4 when absent).

---

## Q3 — Judge pass/fail score threshold: fixed default, or configurable?

**Context**: §3.2 item 3 states `passed: bool (score ≥ a configured threshold, default 70)` —
"configured" is never defined further: configured where, by whom, per-agent or global?

**Options**:
- **A. A single global constant (`DEFAULT_JUDGE_THRESHOLD = 70`) in `judge.py`, overridable via
  a CLI flag (`--judge-threshold`) for one-off runs, no per-agent override.**
- **B. Per-agent threshold, declared in each agent's rubric module (`rubric.py`).**
- **C. No threshold at all — report only the raw score, no derived pass/fail.**

**Recommendation**: **A**. A single global default keeps the first example simple and the
threshold's meaning consistent across agents when the report is later read in aggregate (Story
5's per-agent breakdown is more legible if "pass" means the same score cutoff everywhere).
Per-agent thresholds (B) is a reasonable follow-on once more than one agent is onboarded and
their score distributions are actually observed to differ, but is speculative before that data
exists. Dropping pass/fail entirely (C) would break Story 5's "overall judge pass rate"
acceptance criterion outright.

**Decision**: **A** — resolved into §3.2 item 3 (already stated as 70; this clarifies it is a
single module-level constant with a CLI override, not a per-agent value) and §3.4.

---

## Q4 — How many `prototype-specify` scenarios ship in this spec?

**Context**: Story 1 Acceptance Scenario 2 and §3.2 item 2 say "at least one live scenario
YAML" — leaving open whether v1 should ship with a single scenario (proving the pipeline) or a
small suite (giving the report something to aggregate immediately).

**Options**:
- **A. Exactly one scenario for v1** — mirrors the existing revision track's own precedent
  (`prototype_multi_issue_repair` is the *only* scenario in `workflow/prototype/revision/`
  today), proving the branch end-to-end without over-investing before the pattern is validated.
- **B. Three to five scenarios spanning different brief types** (dashboard, e-commerce, SaaS
  settings-heavy app) to stress different parts of `AGENT.md`'s page-count/content rules from
  the start.

**Recommendation**: **A**. The existing revision track's precedent (one deliberately
comprehensive scenario, not a matrix) is the closest analog in this codebase and this spec
already leans on that precedent elsewhere (log-folder shape, YAML format, opt-in cost model, per
§6's first risk mitigation). More scenarios are a cheap, low-risk follow-on once the branch and
its one example are proven — consistent with the "first example" framing throughout this spec.

**Decision**: **A** — resolved into Story 1 Acceptance Scenario 2 ("exactly one scenario for
this spec — additional scenarios are a follow-on, not blocking").

---

## Q5 — The user wants an explicit, standard iterate-on-the-prompt loop: "create dataset → run
grader → after N runs get feedback → improve the prompt → repeat until max percentage." Does
this fit inside the existing single-run design, or does it require new capability?

**Context**: The spec as planned covers one graded run at a time (Story 2) plus a static
aggregate summary (Story 5). The user's loop needs two things the current design doesn't
explicitly provide: (1) a **percentage that means something statistically** — one run of one
scenario is a single coin-flip-ish sample against a probabilistic model, not a "percentage";
and (2) **feedback surfaced FROM the report, aimed at editing the prompt** — today's Story 5
summary gives aggregate numbers but no surfaced detail on *why* runs are failing. This also
directly reopens a decision from the original planning pass: §5 Out of Scope explicitly listed
"a `benchmark`-style multi-run (N repetitions) command" as a follow-on, not part of this spec —
the user's step 4 ("after X runs feedback...") requires exactly that multi-run capability now.

**Options**:
- **A. Bring N-repeated-sample runs into this spec's scope** (`./tests/evals/model_graded/model-graded.sh graded <id> --judge
  --samples N`, mirroring the existing `benchmark` command's `--n` shape on the deterministic
  track) so "percentage" has an actual denominator > 1, and add a `report --worst N` / `--show
  -failures` view that prints the lowest-scoring entries' full judge rationale (the "feedback" a
  human reads before editing `AGENT.md`) — still no automated prompt editing.
- **B. Keep this spec strictly single-run (as originally planned) and defer the entire iterate
  loop — multi-sample, feedback surfacing, and convergence tracking — to a follow-on spec.**
- **C. Go further than A: have the tool itself propose `AGENT.md` edits automatically based on
  judge feedback, looping until the threshold is hit with no human in the loop.**

**Recommendation**: **A**. The user explicitly described this loop as "the first step" of a
process they intend to repeat per-agent — it is not a nice-to-have on top of the branch, it *is*
the workflow the branch exists to support (the spec's own Problem Statement already frames the
branch as answering "is this actually good," which only means something as a rate, not a
single sample). B would ship a branch that technically works but can't do the one thing the user
asked for first. C crosses this repo's standing rule that live-model runs are always
human-triggered, never agent-automated — auto-editing `AGENT.md` based on an agent's own
judgment of its own eval results is a materially different (and riskier) feature than what was
asked; "feedback and improve the prompt" in the user's own step 4 reads as a human action
informed by tool output, not a delegated one.

**Decision**: **A** — resolved into a new Story 6 ("Iterative prompt-improvement loop") and
folded into §3.2/§3.4 (`--samples`, `report --worst`), superseding the earlier "`benchmark`-style
multi-run is out of scope" line in §5 (updated accordingly).

---

## Q6 — How is "feedback" (step 4) actually surfaced — read the raw report, or does the tool
synthesize it?

**Context**: Once Q5 brings multi-sample runs into scope, "feedback" could mean anything from
"open the JSONL and read it" to "the tool writes you a synthesized improvement memo."

**Options**:
- **A. The tool surfaces raw material only** — `report --worst N` prints the N lowest-scoring
  entries' full prompt/response/rationale, sorted, ready to read; no synthesis, no
  cross-rationale summarization, no suggested edits. The human reads and decides.
- **B. The tool additionally synthesizes** — an extra model call reads the last N rationales and
  writes a "common failure themes" paragraph.
- **C. The tool proposes concrete `AGENT.md` diffs.**

**Recommendation**: **A**. B adds a third kind of model call (beyond agent-under-test and judge)
whose own output would itself need trust/verification — disproportionate machinery for what a
human can do by reading 3–10 judge rationales directly, especially for a single-scenario v1
where failure patterns are likely to repeat within just a few entries. C is the same
automated-prompt-editing concern as Q5 option C, ruled out for the same reason. Keep the tool's
job strictly at "make the evidence easy to find," leave judgment to the human — consistent with
this spec's existing division of labor (deterministic pre-check does facts, judge does
judgment, human does prompt edits).

**Decision**: **A** — resolved into new Story 6 Acceptance Scenario 2 and §3.2 item 4
(`report.py` gains a `worst(entries, n)` helper alongside `summarize()`).

---

## Q7 — "Repeat until we get the max percentage": does the tool enforce or track a target
threshold across prompt iterations, or is that purely a human decision?

**Context**: The user wants to iterate "until max percentage." The report schema already
records `system_prompt_hash` per entry (added in the original design specifically so prompt
drift between entries is detectable), which is the mechanism that makes "did score improve
after I edited the prompt" answerable — but nothing today groups/trends by it, and there's no
stated target percentage or stop condition.

**Options**:
- **A. No hardcoded target in the tool.** `report --worst`/`summarize` groups by
  `system_prompt_hash` so a human can see "prompt version A: 62% avg, version B (after my
  edit): 81% avg" and decide for themselves when it's good enough. No automated stop condition.
- **B. A configurable target threshold in scenario YAML or CLI** (e.g. `--target 90`) that makes
  the summary command print an explicit "TARGET MET" / "TARGET NOT MET (81% < 90%)" line, still
  with no automated looping.
- **C. A fully automated loop**: the tool re-runs the scenario, re-grades, and only stops when
  the target is hit or a max-iteration count is reached, unattended.

**Recommendation**: **A base, B as a lightweight addition.** "Max percentage" is a product/
quality-bar decision the user makes per-agent, not a constant the codebase should hardcode or
own (per-agent thresholds were already rejected for the *pass/fail* threshold in Q3 for the same
reason — speculative before more agents exist). B is cheap to add on top of A (the summary
already computes an average; printing whether it clears an optionally-supplied bar is a small
extension) and directly serves "repeat until we get the max percentage" by making "did I hit my
bar yet" a one-line answer instead of a manual comparison. C is ruled out for the same standing
-rule reason as Q5/Q6 option C — every run in this loop still requires a human to explicitly
invoke `--judge` (and now `--samples`); the tool must never loop on its own.

**Decision**: **A + B** — resolved into new Story 6 Acceptance Scenario 3 and §3.2 item 4
(`summarize()` gains `group_by="system_prompt_hash"` and an optional `target` parameter).

---

## Q8 — The user says "we'll do this as the first step then repeat what we're doing with this
agent to other agents." Does this change scope, or just confirm existing framing?

**Context**: The spec already frames `prototype-specify` as "the first example agent" and the
per-agent-folder design as what makes onboarding a second agent a data addition, not a redesign
(§1, §5). The user's statement confirms this is the intended sequencing, but also asks
explicitly that the *process* — not just the code — be "recorded" as a repeatable procedure.

**Options**:
- **A. No scope change** — the existing per-agent-folder architecture already satisfies this;
  no new artifact needed.
- **B. Add an explicit, named 5-step "Standard Operating Procedure" to the spec's Problem
  Statement**, spelling out the loop the user described (prompt exists → build dataset → run
  grader → gather feedback (Q6) → improve prompt → repeat (Q7) → then repeat the whole procedure
  for the next agent) as the documented process this branch exists to support — not just an
  implied consequence of the architecture.

**Recommendation**: **B**. The user asked twice, in different words, that this be "recorded" —
once implicitly (the report itself, already in scope) and once explicitly (the process). A
named, written-down procedure costs nothing to add to the spec and directly answers "please make
sure we're recording this" at the process level, not just the data level.

**Decision**: **B** — resolved into a new "Standard Operating Procedure" subsection in §1
(Problem Statement).

---

## Q9 — Should the grader dispatch via `create_runner`/the agent registry (current design), or
call the model directly, bypassing it — so "a new agent" needs zero new code, just a new
argument?

**Context**: The user described wanting "a grader framework which will get the prompt.md as
input then user instructions and run it against a given model... I do not want to create new
code for a new agent or prompt but using the same framework and passing new argument." Taken
literally, this could mean routing around `create_runner`/`agents/factory.py`/the registry
entirely (a raw `build_model().invoke(prompt_file_content, instructions)` call, no
`AgentContext`, no tools, no sandbox). But `create_runner` is also what gives an agent real
filesystem tools (`write_file`/`edit_file`/etc.) — necessary for verifying whether a tool-using
agent (e.g. `prototype-revision-agent`) actually produced a correct *result*, not just a
plausible-sounding response.

**Options**:
- **A. Bypass `create_runner` entirely** — a fully decoupled raw prompt+instructions+model
  runner. Simplest possible mechanism, but permanently unable to grade any agent that needs
  tool calls to verify its output (rules out ever extending this branch to
  `prototype-revision-agent` or any future tool-using agent).
- **B. Keep dispatching through `create_runner(scenario.agent_id, ctx)`** (the design as already
  specified in `spec.md` §3.2/§3.5, `plan.md`, `design.md` Task T2) — reuses the existing,
  proven pipeline-agent implementation (registry, tool binding, sandbox, `DeepAgentRunner`
  event stream) as-is. A new agent still needs zero new *driver* code — `run_graded_scenario_once`
  already takes `agent_id` as data, not a code branch — the only thing "new" is a new scenario
  YAML pointing at a different (already-registered) `agent_id`.
- **C. Both, via an optional flag** — more surface area for a case not yet asked for.

**User's answer** (verbatim, asked directly): "What is best approach given that our work will
require tool calling etc only then we'll be able to see if it generated the correct results. i
want to use the implementation what we already have and re use it."

**Decision**: **B**. This is not a change from the original design — `driver.py`'s
`run_graded_scenario_once()` was already `create_runner`-based and already agent-id-generic
(spec §3.2 item 1: "every agent onboarded onto this branch is invoked the same, minimal way").
The user's actual "no new code for a new agent" pain point turns out to be about the *grading*
side (rubric/pre-check), not the *dispatch* side — resolved separately as Q10. No change needed
to `driver.py`'s design; `create_runner` stays.

---

## Q10 — Should the judge rubric and deterministic pre-check become pure data/config instead of
a required Python module per agent?

**Context**: Once Q9 confirmed dispatch stays via `create_runner` (no rework needed there), the
real "new code for a new agent" friction is in the original design's `precheck.py`/`rubric.py`
per-agent-folder pattern (`spec.md` §3.2 item 2, Task T4/T7 in `tasks.md`) — onboarding any new
agent currently means writing two new Python files.

**Options**:
- **A. Data-driven for both.** Rubric becomes a plain text/markdown criteria block — inline in
  the scenario YAML (`rubric: |`) or a referenced `.md` file — fed into **one shared**
  judge-prompt-building function used by every agent (no per-agent Python). Pre-check becomes a
  small, generic, YAML-configurable check set built into the framework itself (a required
  wrapper string/tag, min length or min "section" count via a configurable heading pattern,
  a list of forbidden substrings) — covers `prototype-specify`'s actual needs (`<spec>` wrapper,
  page count via counting `### ` headers, forbidden placeholder strings) without writing
  `precheck.py`. An **optional** Python precheck hook stays available, only for a scenario that
  genuinely needs logic the generic config can't express (e.g. `prototype-specify`'s nav-target-
  to-page-section cross-reference, which needs real parsing, not a substring/count check).
- **B. Keep both as required Python modules per agent** (original design).
- **C. Data-driven rubric only; pre-check stays required Python.**

**User's answer**: "Data-driven for both (Recommended)."

**Decision**: **A**. Onboarding a new agent onto the branch now requires, at minimum, **zero
new Python files** — a new scenario YAML (prompt/instructions reference via the existing
`agent_id`, a `rubric:` block, and a generic `precheck:` config block) is sufficient for the
common case. A custom `precheck.py` remains available as an escape hatch (per-scenario, declared
in the YAML, e.g. `precheck_module: prototype_specify.custom_precheck`) for checks the generic
config genuinely cannot express — `prototype-specify`'s nav-target cross-reference is exactly
such a case and is expected to use this escape hatch, not the generic config, for that one
check. This changes `spec.md` §3.2 item 2, the `GradedScenario` shape in `data-model.md`, and
`tasks.md` Tasks T4/T7 — **`plan.md`/`design.md`/`tasks.md` are now stale relative to this
decision and should be regenerated via `/apex:plan`/`/apex:design` rather than hand-patched
again, given the size of this change.**

---

## Q11 — Revisiting Q9: what's the actual benefit of `create_runner` over a from-scratch raw
chat call (Python → provider API directly), skipping the pipeline/sandbox entirely?

**Context**: The user asked this directly as a "what if" — reopening Q9, not just accepting its
prior resolution at face value. Q9's original justification was tool-calling (future agents need
it to verify correctness). That's real, but it under-sells the case for `prototype-specify`
itself, which is text-only and doesn't need tools — so on tool-calling grounds alone, a raw chat
call would work identically *for this one agent*. A sharper reason was missing.

**Options**:
- **A. Raw chat call**: `build_model(model, provider=provider).invoke([SystemMessage(AGENT.md
  body text), HumanMessage(instructions)])`. No `AgentContext`, no `DeepAgentRunner`, no sandbox.
  Fewer moving parts for a text-only agent.
- **B. Keep `create_runner`** (Q9's existing decision).

**The missing argument, surfaced by asking "what's the benefit" directly**: `prototype-specify`'s
`AGENT.md` **frontmatter declares `injects: [template, design_system, images]`**
(`backend/agents/prompts/prototype-specify/AGENT.md`). The body text of that file is *not* the
full system prompt the agent actually runs with in production — `create_runner`'s
`_compose_system_prompt`/`_compose_injection` (`agents/factory.py`) assemble the real prompt from
the injected template + design-system content, guardrails, skills, hooks, and the user's
constitution, **then** the `AGENT.md` body, in a fixed order. A raw `SystemMessage(AGENT.md
content)` skips every one of those injection sources. Grading that raw body text means grading a
prompt that **never actually runs for a real user** — the eval's pass rate would say nothing
reliable about production behavior. Making option A prompt-faithful would require re-implementing
`_compose_system_prompt`'s injection logic from scratch inside the grader — which is *more* new
code than reusing `create_runner`, not less, and directly undermines the original "no new code
for a new agent" goal this whole framework exists to satisfy (Q9/Q10).

**Recommendation**: **B**, reaffirmed — now for a stronger reason than Q9 gave. Two independent
justifications, not one: (1) tool-calling fidelity for future agents (Q9's original point), and
(2) **prompt-composition fidelity for every agent, including this one** — a raw call risks
silently grading a different prompt than the one that ships. (2) applies even to `prototype-
specify` today, so it isn't a "wait until we need tools" concern — it's already load-bearing.

**Decision**: **B** — Q9's decision stands, with (2) added as the primary justification in
`spec.md` §1 (the original text only cited tool-calling — that undersold the case for a
text-only agent like `prototype-specify` and is corrected here).

---

## Q12 — Report storage: readability broke the JSONL design

**Context**: The shipped implementation writes one entry per run to a shared
`eval_report.jsonl`. In practice, the user found this unreadable — a single-line JSON blob
per run, with the full `<spec>` response inlined, is unusable when opened directly.

**Decision**: Replaced the shared JSONL file entirely with **per-run files inside each run's own
`model_graded/logs/<run_id>/` folder**: `run.json` (prompt, response, precheck result — written
for every `graded` invocation, judged or not) and `grade.json` (score, verdict, rationale —
written only when `--judge` is used). Both pretty-printed (`indent=2`). The "report" (aggregate
summary/worst/by-hash) is now a **computed view** — `report.py::load_run_entries()` scans every
run folder and merges `run.json` + `grade.json` on the fly — not a separately persisted store.
`backend/tests/evals/reports/` no longer exists. Supersedes spec §3.2 item 5, §3.3, and every
`eval_report.jsonl` reference in the original spec text.

## Q13 — Judge output: strengths/weaknesses, not just one rationale paragraph

**Context**: The user asked for the judge's output to include explicit weaknesses/strengths,
not just a score and one prose paragraph, so `report --worst` output is scannable.

**Decision**: `JudgeVerdict`/the judge's structured-output schema gained `strengths: list[str]`
and `weaknesses: list[str]` fields alongside `score`/`rationale`. `report --worst` prints each
strength/weakness as its own line. Supersedes the original `judge.py` schema description in
spec §3.2 item 4.

## Q14 — Observability gap: requested model vs. actually-resolved model

**Context**: `run.json`'s `model`/`provider` fields (and `grade.json`'s `judge_model`/
`judge_provider`) only ever recorded the raw CLI argument passed in — `null` whenever `--model`/
`--judge-model` was omitted (the common case), which made it impossible to tell which model
actually ran, especially when the default fallback chain silently resolved to an unexpected
provider (discovered live: a broken Bedrock credential silently won the fallback chain over a
working Mistral key).

**Decision**: Added `resolved_model_id` (agent) and `judge_resolved_model_id` (judge) fields,
populated from the actually-built model instance (`DeepAgentRunner.model_id` /
`app.agents.model_factory.model_identifier()`) — always present, even on an errored judge call.
The requested `model`/`provider` fields are kept as-is (honest record of what was asked), with
the resolved fields as the new source of truth for "what actually ran." Also added `--provider`/
`--model` flags to `graded` (previously only `--judge-provider`/`--judge-model` existed, which
scoped to the judge only and left the agent-under-test with no override lever at all).

## Q15 — Scenario count: from "exactly one" to a generic multi-prompt dataset

**Context**: `clarifications.md` Q4 decided v1 ships with exactly one scenario. The user then
asked for a dataset of 10+ prompts spanning multiple industries, with the shared grading
config (precheck/rubric) generalized to not assume any one vertical.

**Decision**: Introduced a second scenario-authoring shape alongside the original standalone-YAML
one: a `_template.yaml` (agent_id + generic `precheck:`/`rubric:`/optional `precheck_module:` —
no prompt of its own) paired with a `dataset.json` array of `{id, industry, prompt}` entries.
`scenario_discovery.py::load_dataset_scenarios()` combines them into one `GradedScenario` per
entry, all sharing the template's grading config. `prototype-specify`'s scenarios now ship with
11 entries (10 new industries + the original billing-console brief, re-homed into `dataset.json`)
under one reworded, industry-agnostic rubric. Adding prompt #12 is one new `dataset.json` entry —
zero new Python or YAML. This **supersedes Q4's "exactly one scenario"** decision and Story 1
Acceptance Scenario 2's "exactly one scenario ships with this spec" wording.
