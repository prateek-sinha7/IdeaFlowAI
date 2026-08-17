# Clarifications — 012-per-agent-skills-custom-agents

Resolved with the requester on 2026-08-10 before planning. Each entry records the question,
the decision, and why the alternatives lost — so a later reader does not reopen a settled call.

---

## Q1 — How does a main custom agent drive its sub-agents?

**Decision: engine-orchestrated.** `workflow.yaml` declares the children and a strategy; the
VELOCITY engine schedules them deterministically, collects their sandbox artifacts, then runs
the parent.

**Rejected:** deepagents-native `subagents=` with the `task` tool (non-deterministic, requires
re-enabling a tool the runner deliberately withholds at `deep_agent_runner.py:366-375`, and
small local models delegate unreliably); and the hybrid, which would leave two execution paths
to debug for one feature.

## Q2 — Where does the custom `workflow.yaml` live?

**Decision: the DB is the source of truth; YAML is its serialized form.** Existing built-in
workflows keep their on-disk `workflow.yaml`. Custom workflows are generated and stored the way
user workflows are stored today — `workflows.manifest_json`.

**Consequence:** `manifest.py` needs a public `build_manifest_from_dict()` so both origins pass
through one validator (R-26). Rejected: writing per-user files to disk, which introduces
per-tenant filesystem state, collisions, and container-persistence problems.

## Q3 — What happens to run-level skill attach?

**Decision: skills are known per agent from the start.** The agent's own declaration is
authoritative, and the agent is told in its prompt to read and follow the attached skill before
doing its work. For an existing built-in agent, a line is added at the top of its prompt to
that effect (R-13).

Run-level `attached_skills` becomes a one-time migration source (R-29), not a parallel mechanism.

## Q4 — How does an agent learn to name its artifact?

**Decision: a baked prompt preamble** on the custom agent, naming the exact target filename.
Deterministic, cheap, and nothing extra for the model to open.

**Rejected:** an auto-attached base skill teaching tool usage — progressive disclosure means
small models frequently never read it, which is precisely the case the naming rule must survive.

**Added during design:** because the preamble is model-trusted, the engine verifies the artifact
afterwards and writes the streamed text to the expected path if it is missing (R-20). The
instruction is the happy path; the check is the guarantee.

## Q5 — How should `compatible_agents` work for user-named custom agents?

**Decision: a filter hint for built-in agent ids; custom agents unrestricted.** A custom agent
has no stable registry id to match against, so any skill may be attached to it. The field
filters and sorts the picker for built-ins and is never enforced server-side (R-34).

## Q6 — What topologies are legal?

**Decision: two levels maximum.** A step may own children, and a child may own grandchildren.
Deeper nesting is a validation error (R-05).

**Rejected:** arbitrary nesting (needs cycle detection, depth caps, and a substantially harder
canvas and scheduler for no demonstrated use case).

## Q7 — Internet access

**Decision: ship the switch now, the tool later.** The manifest field, UI toggle, capability
provider, and engine plumbing land in this spec, wired to stubs that return
`"internet access is not yet available."` (R-25).

**Why:** no web tool of any kind exists in the backend today — this is net-new capability, not a
toggle over something already built. Provider selection, API-key handling, and egress policy
deserve their own spec rather than a footnote in this one.

## Q8 — How does the parent receive its children's work?

**Decision: sandbox files only.** Children write artifacts; the parent's prompt lists the
filenames and it reads them with its filesystem tools.

**Rejected:** injecting every child's full text into the parent's context — with three children
and long outputs that is the fastest route to a blown context window, and it would make the
feature unusable on exactly the models the engine must stay agnostic about.

## Q9 — How is a blank, renamed custom agent represented?

**Decision: one base `custom-agent` on disk plus per-instance overrides in the manifest.**
Identity (`instance_id`), display `name`, `prompt`, and `skills` live in the stored manifest.

**Rejected:** materializing a real `AGENT.md` per instance — the same per-user disk-state
problem already rejected in Q2.

## Q10 — Who writes the "we have the following sub agents" text?

**Decision: the engine auto-appends the roster.** The user writes only the purpose; the engine
appends the children's names and the files they produced (R-15).

**Why:** the screenshot's hand-written list goes stale the moment a child is renamed or removed,
and the failure is silent — the parent would look for a file nobody wrote.

## Q11 — What do the three strategies mean?

**Decision:** `parallel` = declared children concurrently, bounded by `max_parallel`.
`sequential` = declaration order, each child seeing prior siblings' artifacts. `fanout` = one
child template cloned per task from an upstream task list, requiring `task_source` (R-18).

## Q12 — Do per-agent skills apply to built-in pipelines too?

**Decision: yes — any step in any workflow.** `hello_html`, `prototype`, and `app_builder` can
pin skills per agent exactly as a custom workflow can. One skill model, not two.

## Q13 — Sandbox permissions

**Decision: every agent — custom, existing, and new — has read and write access to its
sandbox.** `exec` stays opt-in and declared (R-22).

**Side effect worth naming:** this removes the D-02 failure mode where a text-only agent's
`write_file` call silently produced an empty deliverable. It also changes every agent's tool
set, which has destabilized small local models before — hence AC-19.

## Q14 — Deliverable and logging

**Decision:** `serialized_sandbox`, as today, **plus** an engine-written
`.logs/run-logs.jsonl` capturing engine and agent lifecycle events. Agents never write to it,
and the `.logs/` prefix is filtered out of the delivered artifact tree (R-23, R-24).

## Q15 — Models

**Decision: the engine stays model-agnostic.** It is built the way it is built today; the
engine does not know which model backs a run. If a small Ollama model cannot follow a preamble,
that is not the engine's problem — which is exactly why the artifact check in R-20 is an engine
guarantee rather than a prompt instruction.

## Q16 — The existing `custom` workflow

**Decision: untouched.** `backend/agents/workflows/custom/workflow.yaml` and its nine agents
keep working as the built-in template. The canvas builder is additive (R-30).

## Q18 — Reusing one blank agent many times collides with the engine's agent-keyed identity

**Found while writing the plan, not during the interview.** The engine keys every step by
`agent_id` — `_steps_by_agent = {s.agent_id: s for s in compiled.steps}` recurs at
`engine.py:2185, 6557, 7333, 7506`, `ordered_agents` is a list of `AgentSpec`, and the compiler
explicitly rejects *"a duplicate agent id"*. Three steps declaring `agent: custom-agent` would
collide before anything ran. Agent identity **is** step identity throughout the kernel.

**Decision: synthesize a unique agent id per instance** — `custom-agent:research-a`.
`load_agent_spec()` resolves the colon suffix by loading the base spec and overlaying the
instance's id, display name, and composed prompt (R-03a).

**Rejected: thread a `step_key = instance_id or agent_id` through the engine.** Architecturally
the cleaner model, but it means rewriting every agent-keyed map, the `ordered_agents` alignment,
the resume path, and every event payload — an invasive refactor of an 8,600-line file that is
the riskiest in the repo, to buy nothing a synthetic id doesn't already buy.

**Bonus the synthetic id gives us free:** events, per-agent model overrides, and resume become
naturally per-node rather than per-agent-type — which is exactly what the canvas needs to show
three researchers as three distinct things.

## Q17 — Scope of the `compatible_agents` restoration

**Decision: re-author all 182 skill files.**

**Constraints attached during design, because this is the least verifiable work in the spec:**
lists are derived by script from each skill's own name and description and reviewed by category
rather than hand-authored one file at a time (R-32), and a missed file degrades to
compatible-with-everything rather than to an invisible filter (R-33).
