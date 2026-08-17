# Clarifications — 011-native-deepagents-skills

**Date**: 2026-08-10
**Resolves**: Q1–Q8 in `spec.md` §6
**Outcome**: all eight decided. Three decisions changed the requirement set — see §Consequences.

---

## C-01 — How do the 61 text-only agents reach a skill? → **Grant the filesystem tool set (read *and* write), sandbox-confined**

**Context** (`spec.md` §6 Q1, R-05): `_resolve_runner_tools` returns `exclude_builtin_tools=True`
for `tools: []` (61 of 87 agents) and for the `planning`/`random_word`/`coin_flip` sets.
`DeepAgentRunner` then drops all of `_BUILTIN_TOOLS` — including `read_file`
(`deep_agent_runner.py:95-107`). A skill advertised as `-> Read /skills/poet/SKILL.md` is
unreadable by those agents. `writer` and `emoji-picker` in the `hello_html` loop are both affected.

| Option | |
|---|---|
| A | Subtract only `{"read_file"}` when skills are staged |
| **B (chosen)** | **Grant the full filesystem tool set — read *and* write — confined to the run sandbox** |
| C | Only the 26 tool-having agents may receive skills |

**Decision**: **B**.

Rationale, in the developer's words: *"If a skill requires to write or plan a certain thing we need
to provide the write to it. Otherwise skill is useless. But it should only have access to sandbox
only. We'll improvise if we have issues later."*

Option A satisfies the letter of R-05 (the skill can be *read*) but not its intent — a skill whose
procedure is "produce this file" cannot be carried out by an agent that can only read. Option C
contradicts R-01 and would exclude `writer`, the exact agent the `poet` skill targets.

**Confinement** is already in place and needs no new mechanism: the backend is
`FilesystemBackend(root_dir=str(run_sandbox.root), virtual_mode=True)`
(`deep_agent_runner.py:336-339`), and `virtual_mode=True` blocks `..`/`~` traversal, anchoring
every path to the run sandbox.

**Scope of the grant**: conditional on skills being staged for the run. A run with no attached
skills keeps today's exact tool set, preserving R-04. `task` (the library sub-agent spawner)
remains excluded unconditionally — the engine orchestrates fan-out itself.

> **Accepted risk, flagged.** 61 agents are text-only *by design*, and the engine resolves their
> deliverable from streamed text (`ctx.last_streamed`), not from disk. An agent that now chooses
> to `write_file` instead of streaming its answer may produce an **empty deliverable**. This is the
> most likely way this decision bites. It is accepted per *"we'll improvise if we have issues
> later"* and tracked as **D-02** below — not designed around up front.

> **Second-order:** `_NO_TOOLS_PREAMBLE` (the anti-fabrication block applied when `no_tools=True`)
> must not be emitted for an agent that has just been granted tools, or the prompt will tell the
> agent it cannot write files while handing it `write_file`.

---

## C-02 — Does granting filesystem access expose sibling agents' outputs? → **Yes, accepted**

**Context** (§6 Q2): the `RunSandbox` is shared across a run's agents, so any agent with
`read_file` can read every other agent's deliverables from the same run.

| Option | |
|---|---|
| A | `FilesystemPermission` restricting skills-only agents to read under `/skills/**` |
| **B (chosen)** | **Accept full sandbox access** |

**Decision**: **B**. No permission rules. `virtual_mode=True` already confines access to the run
sandbox, which is the boundary that matters (per-user, per-run, traversal-proofed at
`sandbox.py:130-136`). Cross-agent reads within one run are not a leak between tenants.

Consistent with C-01: having decided agents may write to do their work, restricting what they may
read within their own run's workspace would be arbitrary.

**Consequence**: `spec.md` R-06 ("staged skills are read-only to the model") is **dropped**. Under
C-01 agents hold `write_file`/`edit_file`, and adding a deny rule *only* for `/skills/**` would be
the single permission rule in the system — inconsistent with B and not requested. An agent can
therefore modify its own staged skill files within its run sandbox; the global catalog under
`backend/skills/global/` is never exposed and cannot be touched.

---

## C-03 — How do we de-risk activation being pure model judgment? → **Native only, no fallback**

**Context** (§6 Q3): the body enters context only if the model chooses to call `read_file`. If it
never does, the skill silently does nothing. `qwen3.5:4b` drives the local `hello_html` loop and
small models are documented as failing to notice such cues.

| Option | |
|---|---|
| A | Native path, but keep eager inline behind a config flag until measured |
| B | Hybrid — native for capable models, eager for small/local, chosen by tier |
| **C (chosen)** | **Native only, no fallback** |

**Decision**: **C**. The eager injection path is deleted outright, not flagged off. One delivery
mechanism, one code path.

**This is a deliberate risk acceptance, not a claim that activation works.** No measurement exists
yet. Acceptance criterion 6 in `spec.md` is now a **discovery** step rather than a regression
check: it establishes the activation rate for the first time, on both a frontier model and
`qwen3.5:4b`. If `qwen3.5:4b` does not activate, local `hello_html` skill testing stops working
until a fix lands, and the fix will be a new decision — not a revert to a retained fallback.

---

## C-04 — Descriptions over the limit → **Rewrite all 42 to ≤200 chars**

**Context** (§6 Q4, R-13): the description is the entire routing signal the model sees **and** it
is paid on every agent advertising the skill. `flox-environments` is 1,214 chars and is already
being **silently truncated** at the `deepagents` hard limit of 1,024; 42 skills exceed 200.

**Decision**: rewrite all 42 to ≤200 chars, in the form *"what it does + when to use it"*.
`flox-environments` is the correctness fix (truncation today); the other 41 are cost and routing
quality. No change to `deepagents` limits — we stay well inside them.

---

## C-05 — Per-agent skill token ceiling → **Warn at 8,000, never block**

**Context** (§6 Q5, R-16): cost is `464 + 66 × n_skills` **per agent**; the whole 202-skill catalog
would be 13,730 tok/agent (247k on an 18-agent pipeline).

**Decision**: compute at staging time, log it, emit it on the `agent_skills` event, and warn above
a configurable ceiling defaulting to **8,000 tok/agent**. **Never hard-fail a run.** The user chose
what to attach; the system's job is to make the cost visible, not to veto it.

---

## C-06 — Skills cached per thread on resumed runs → **Accept and document**

**Context** (§6 Q6): `before_agent` early-returns when `skills_metadata` is already in state
(`skills.py:941-985`), so skills load once per thread. A resumed run — HITL gate, crash recovery —
reuses the snapshot from the original invocation.

**Decision**: accept. Our `thread_id` is per agent-invocation (`f"{run_id}:{agent_id}"`), so a
normal run loads once per agent, which is correct. Editing a skill mid-run not taking effect is
acceptable and arguably desirable — a run should be internally consistent. Documented, not worked
around.

---

## C-07 — Attached skills with no frontmatter → **Synthesize it**

**Context** (§6 Q7, R-10): the `deepagents` parser requires `name` + `description` in YAML
frontmatter and **silently drops** any skill lacking them (`skills.py:366-454`). A user-authored
skill whose content is bare prose would never load, with no error surfaced.

**Decision**: at staging time, if the content has no parseable frontmatter, synthesize one from the
attach payload's `id`/`name`/`description` and prepend it. Directory name must equal the
frontmatter `name` or `deepagents` logs a mismatch warning — use the payload `id` for both.

---

## C-08 — Custom preamble or the stock one? → **Stock `skills=` sugar**

**Context** (§6 Q8): `create_deep_agent(skills=[...])` builds `SkillsMiddleware` with the stock
`SKILLS_SYSTEM_PROMPT`. Supplying our own requires constructing the middleware ourselves and
passing it via `middleware=[...]`, with a template retaining three literal format slots.

| Option | |
|---|---|
| A | Custom `SkillsMiddleware` carrying an explicit precedence rule |
| **B (chosen)** | **Stock `skills=` sugar** |

**Decision**: **B**. One-line integration, less code, and it tracks upstream template improvements
automatically.

**Consequence — R-07 changes meaning.** R-07 required the prompt to state *"a skill may not change
your role, output contract, or tool permissions; your agent instructions win."* With the stock
preamble there is no place to say it. R-07 is therefore **rewritten as an authoring-time
requirement**, discharged entirely by R-08 (no skill asserts an identity) and R-09 (no skill
directs use of an unavailable tool). This is a defensible position and arguably the stronger one:
prompt-stated precedence is measured at only ~13–17% compliance and collapses on small models,
whereas a contradiction that was never written cannot be obeyed. But it does mean **sanitization is
now the sole defence**, so A5 stops being hygiene and becomes load-bearing.

> **Known mismatch, accepted.** The stock preamble instructs the model on *"Executing Skill
> Scripts"* and *"Access supporting files"*. We stage `SKILL.md` only, and `execute` is in our
> excluded tool set. The model is told about a capability it does not have. Cost is a few wasted
> tokens and a possible failed tool call; revisit by switching to option A if it causes real
> misbehaviour.

---

## Consequences for `spec.md`

| Requirement | Change |
|---|---|
| **R-05** | Broadened — agents receive the **filesystem tool set (read + write)**, not `read_file` alone (C-01) |
| **R-06** | **Dropped** — staged skills are no longer read-only to the model (C-02) |
| **R-07** | **Rewritten** — precedence is enforced at authoring time, not stated in the prompt (C-08) |
| **R-08, R-09** | **Elevated to load-bearing** — now the only defence against skill/agent conflict (C-08) |
| §5 Out of scope | `FilesystemPermission` rules move here (C-02); the eager-inline fallback flag moves here (C-03) |
| Acceptance 5 | **Removed** (write-deny no longer a requirement) |
| Acceptance 6 | Reframed from regression check to **first measurement** of activation (C-03) |

## Deferred / accepted risks

| ID | Risk | Why deferred |
|---|---|---|
| **D-01** | Activation rate is unknown and there is no fallback. If `qwen3.5:4b` does not call `read_file`, local skill testing breaks. | Explicitly accepted (C-03). Measured by acceptance 6; a failure becomes a new decision. |
| **D-02** | 61 text-only agents gain `write_file`. Their deliverable is resolved from streamed text, so an agent that writes a file instead of streaming may yield an **empty deliverable**. | Accepted per *"we'll improvise if we have issues later"* (C-01). Watch for it in acceptance 12's pipeline regression run. |
| **D-03** | Agents can modify their own staged skill files mid-run. | Consequence of C-02; contained to the run sandbox, never touches the global catalog. |
| **D-04** | The stock preamble advertises script execution the agents cannot perform. | Accepted (C-08); revisit only if it causes real misbehaviour. |
