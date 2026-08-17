# Feature Specification: Native `deepagents` Skills

**Spec ID**: 011-native-deepagents-skills
**Created**: 2026-08-10
**Status**: Clarified — Q1–Q8 resolved in [`clarifications.md`](clarifications.md); ready to plan
**Root**: `backend/agents/factory.py`, `backend/app/agents/deep_agent_runner.py`, `backend/skills/global/`
**Verified against**: `deepagents==0.6.7` (installed) — package source read and executed, not inferred from docs
**Supersedes**: eager `blocks["skills"]` injection + `_filter_skills_for_agent` (`agents/factory.py`); `compatible_agents` in all 202 `SKILL.md`

---

## 1. Problem

VELOCITY injects skills **eagerly**. Every run-attached skill's full body is concatenated into
every agent's system prompt by `_compose_system_prompt`, then filtered per-agent against a
`compatible_agents` frontmatter field.

Both halves are wrong.

**The cost is unconditional.** A skill body averages ~1,900 tokens and is paid on every accepting
agent whether or not that agent's task has anything to do with it. Relevance is never assessed —
not by us, not by the model.

**The routing field never got filled in.** `compatible_agents` is populated in **13 of 202**
skills. The other 189 are unscoped, which means "applies to every agent" — so the filter mostly
filters nothing, while still asking 202 skill authors to enumerate 87 agents. The same team filled
in the *agent-side* equivalent (`guardrails:`) 37 times out of 87. Asking the skill to know its
consumers does not work.

Meanwhile `deepagents` 0.6.7 — already installed, already the runtime — ships a **complete,
entirely unused** skills subsystem built on the opposite principle: advertise cheaply, load on
demand. We are hand-rolling a worse version of a thing we already depend on.

## 2. What it does

Skills attach at the **run level** and are advertised to **every** agent in that run. Each skill
costs two lines of prompt (~66 tokens); the model calls `read_file` to pull the body **only when
it judges the skill relevant to the task in front of it**.

```
run launch  ──▶  stage attached skills once into  <sandbox>/skills/<id>/SKILL.md
                          │
                          ├─▶ agent 1 ─ sees: "- **poet**: Write rhyming verse…
                          │              -> Read `/skills/poet/SKILL.md`"     (~66 tok)
                          ├─▶ agent 2 ─ same list
                          └─▶ agent N ─ same list
                                        │
                                        └─▶ model decides ─▶ read_file() ─▶ body enters context
```

Nothing decides *for* the model which skills it may see. The user decides what is attached to the
run; the model decides what to actually open.

## 3. Verified mechanics — the constraints this spec must live inside

Read from the installed package. These are facts, not preferences.

| Fact | Source |
|---|---|
| `create_deep_agent(skills=…, permissions=…)` are public params | `graph.py:217-236` |
| `skills` → `SkillsMiddleware(backend=backend, sources=skills)` | `graph.py:715-716` |
| `sources` are **directory paths**, POSIX, relative to the backend root | `skills.py::_list_skills_with_errors` |
| Scan requires `<source>/<skill-name>/SKILL.md`; a bare `SKILL.md` at the source root is **never** found | `skills.py:573-630` |
| Only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` survive frontmatter parsing — **everything else is silently dropped** | `skills.py:366-454` |
| **The body is not injected.** Activation is the model calling `read_file` | `SKILLS_SYSTEM_PROMPT` |
| A `system_prompt=` override must contain `{skills_locations}`, `{skills_load_warnings}`, `{skills_list}` or the constructor raises `ValueError` | `skills.py:786-825` |
| `before_agent` early-returns when `skills_metadata` is already in state — skills load **once per thread** | `skills.py:941-985` |
| `description` > 1,024 chars is **silently truncated** | `skills.py:139-148` |
| `allowed-tools` is parsed and printed but **never enforced** anywhere in the package | grep: every hit is inside `skills.py` |

Our backend is `FilesystemBackend(root_dir=str(run_sandbox.root), virtual_mode=True)`
(`deep_agent_runner.py:336-339`), so POSIX `/skills/` resolves to `<sandbox.root>/skills/`.

**Cost model — `464 tok fixed preamble + ~66 tok per skill`, *per agent*.**

| Skills attached | tok/agent | × 18-agent pipeline |
|---|---|---|
| 1 | 530 | 9,540 |
| 3 | 662 | 11,916 |
| 5 | 794 | 14,292 |
| 202 (whole catalog) | 13,730 | 247,140 |

The preamble dominates at low counts, so the real cost driver is **how many agents carry a skills
block at all**, not how many skills each carries.

**Catalog inventory (measured):** 202 skill dirs — all parse, all have `name` + `description`, all
`name` values match their directory. Frontmatter: `name`/`display_name`/`description`/`category`/
`compatible_agents`/`tags` = 202 each · `source`/`sourceLabel` = 154 · `isBeta` = 48.

**Agent inventory (measured):** 87 agents — **61** are text-only (`tools: []`), 26 have tools.

## 4. Requirements

### Delivery

- **R-01 — Run-level attachment, no per-agent scoping.** Every skill attached to a run is
  advertised to every agent in that run. No code path may filter which agents see which skill.
- **R-02 — One shared skills directory.** Skills stage once into `<sandbox>/skills/<id>/SKILL.md`
  and all agents point at the same source. The staging step is **idempotent** — the sandbox is
  shared across a run's agents and runner construction happens per agent.
- **R-03 — Bodies are never injected.** After this change no skill body may enter a system prompt
  unconditionally. The `=== SKILLS ===` block is deleted, not conditionally skipped.
- **R-04 — Zero cost when nothing is attached.** A run with no attached skills constructs no
  `SkillsMiddleware` and produces a **byte-identical** system prompt to today. This is the
  regression guard for 87 agents across 15 pipelines.
- **R-05 — An agent must be able to *carry out* a skill, not merely read it.** When a run has
  attached skills, every agent receives the filesystem tool set — **read *and* write** — confined
  to the run sandbox by `virtual_mode=True`. A skill whose procedure is "produce this file" is
  useless to an agent that can only read. `task` (the library sub-agent spawner) stays excluded
  unconditionally. *(C-01)*
- **R-06 — *(dropped, C-02)*** — staged skills are not write-protected. Under R-05 agents hold
  `write_file`/`edit_file`, and a deny rule covering only `/skills/**` would be the sole permission
  rule in the system. Access is bounded by the run sandbox, which is the boundary that matters; the
  global catalog under `backend/skills/global/` is never exposed.

### Correctness

- **R-07 — Agent instructions outrank skill instructions — enforced at authoring time.** `AGENT.md`
  owns the `produces`/`consumes` contract that downstream stages and validators depend on; a skill
  changing output shape breaks the run, not just the wording. We use the **stock** `deepagents`
  preamble (C-08), which has no slot for a precedence rule — so this requirement is discharged
  entirely by R-08 and R-09. **Sanitization is the sole defence**, which makes it load-bearing
  rather than hygiene. Prompt-stated precedence measures at only ~13–17% compliance and collapses
  on small models; a contradiction that was never written cannot be obeyed.
- **R-08 — No skill may assert an identity.** Because every attached skill reaches every agent
  (R-01), a body opening *"You are a…"* can hijack an unrelated agent. Three skills do today.
- **R-09 — No skill may direct use of a tool the agent lacks.** 48 skills name filesystem tools.
  Under R-05 agents receive the full read+write set, so most such references are now valid —
  but `execute` is **not** available to any agent and must not be directed.
- **R-10 — A skill must load.** Every attached skill must satisfy the `deepagents` parser: YAML
  frontmatter present, `name` matching its directory, `description` ≤ 1,024 chars. Skills arriving
  without frontmatter get one synthesized rather than being silently dropped.

### Catalog

- **R-11 — VELOCITY is the only platform named.** Strip provenance (`source`/`sourceLabel`
  frontmatter) and foreign AI-tooling references from bodies. **Technical subject matter stays** —
  a `postgresql-optimization` skill still says PostgreSQL; React, Spring Boot and Django are the
  skills' *subjects*, not third-party references.
- **R-12 — `compatible_agents` is retired** from the 202 `SKILL.md` files, from
  `GlobalSkillEntry`, from `factory.py`, from the `agent_skills` event, and from the four frontend
  call sites. *Hooks* have their own separate `compatible_agents` — it stays.
- **R-13 — Descriptions ≤ 200 chars.** The description is the entire routing signal **and** it is
  paid on every agent that advertises the skill. One skill currently exceeds the hard 1,024 limit
  and is being silently truncated; 42 exceed 200.
- **R-14 — All 202 skills are kept**, including the ~80 covering technology VELOCITY has no
  pipeline for. They cost nothing unless attached.

### Observability

- **R-15 — Delivery is never silent.** Per agent, report skills advertised and any
  `skills_load_errors`. The dominant failure mode in this class of system is a skill quietly not
  attaching, and progressive disclosure makes silence *more* likely, not less.
- **R-16 — Token cost is surfaced.** Compute `464 + 66 × n_skills` per agent, log and emit it, warn
  above a configurable ceiling. Never hard-fail a run on it.

## 5. Out of scope

Skill script execution (`execute` is excluded from our tool set and the only backends providing it
run unsandboxed shell) · per-agent skill allowlists (`skills:` in `AGENT.md`) · a
`CompositeBackend` mount of the global catalog · `StateBackend` skill injection via
`invoke(files=…)` · upgrading `deepagents` to 0.7.x (independently breaking: `write_file` starts
overwriting, which the prototype build loop depends on) · peer-vs-peer skill conflict (two skills
both prescribing output format — no answer exists upstream either) · `ectx.disk_skills`, the
per-user per-agent `SKILL.md` override, which is genuinely per-agent and stays eagerly injected.

Added by clarification: **`FilesystemPermission` rules of any kind** (C-02 — access is bounded by
the run sandbox alone) · **an eager-inline fallback path or config flag** (C-03 — the old injection
is deleted outright, not retained behind a switch) · **a custom skills preamble** (C-08 — the stock
`skills=` sugar is used, so no precedence text reaches the model).

## 6. Resolved decisions

All eight questions resolved 2026-08-10 — full reasoning in [`clarifications.md`](clarifications.md).

| # | Question | Decision |
|---|---|---|
| **C-01** | 61 of 87 agents have no `read_file` — how do they reach a skill? | **Grant the filesystem tool set — read *and* write — when skills are staged**, confined to the run sandbox by `virtual_mode=True`. Read-only was rejected: a skill whose procedure is "produce this file" is useless to an agent that cannot write. `task` stays excluded. |
| **C-02** | Does that expose sibling agents' outputs? | **Accepted.** No `FilesystemPermission` rules. The run sandbox is the boundary that matters. |
| **C-03** | Activation is unmeasured model judgment. | **Native only, no fallback.** Eager injection is deleted outright, not flagged off. Deliberate risk acceptance — see D-01. |
| **C-04** | 42 descriptions over 200 chars; one over the hard 1,024 limit. | Rewrite all 42 to *"what it does + when to use it"*. |
| **C-05** | Per-agent token ceiling? | Warn at **8,000 tok/agent**; never block. |
| **C-06** | Skills cached per thread on resumed runs. | Accept and document — a run should be internally consistent. |
| **C-07** | Skills without frontmatter are silently dropped. | Synthesize frontmatter from the payload's `id`/`name`/`description`. |
| **C-08** | Custom preamble or stock? | **Stock `skills=` sugar.** No precedence text reaches the model, so R-07 becomes an authoring-time requirement discharged by R-08/R-09. |

### Accepted risks

| ID | Risk |
|---|---|
| **D-01** | Activation rate is unknown with no fallback. If `qwen3.5:4b` does not call `read_file`, local skill testing breaks until a new decision is made. |
| **D-02** | 61 text-only agents gain `write_file`. Their deliverable is resolved from streamed text (`ctx.last_streamed`), so an agent that writes a file *instead of* streaming may yield an **empty deliverable**. The most likely way C-01 bites. |
| **D-03** | Agents can modify their own staged skill files mid-run. Contained to the run sandbox; the global catalog is never exposed. |
| **D-04** | The stock preamble advertises script execution and supporting-file access that no agent has (`execute` is excluded, and only `SKILL.md` is staged). |

> **Sanitization trap, already found:** do **not** blind-regex `cursor`. Zero real Cursor-IDE
> references exist in the catalog — every hit is a CSS or screen-reader cursor (e.g.
> `accessibility`: *"visibility of the keyboard/screen reader cursor"*). Measured body
> contamination is `claude` 26 · `ecc` 17 · `superpowers`/`obra` 5 · vendor-LLM names 3, union
> ≈ 40 files. R-11 needs judgment per file, not `sed`.

> **Second-order consequence of C-01:** `_NO_TOOLS_PREAMBLE` (the anti-fabrication block emitted
> when `no_tools=True`) must not be applied to an agent that has just been granted tools, or the
> prompt will tell it that it cannot write files while handing it `write_file`.

## 7. Acceptance

1. A run with **no** attached skills produces a byte-identical system prompt to pre-change for a
   `user_stories` pipeline, and constructs no `SkillsMiddleware`. *(R-04)*
2. A run with 2 skills attached stages `<sandbox>/skills/<id>/SKILL.md` for each, exactly once,
   and every agent in the run advertises both. *(R-01, R-02)*
3. Calling runner construction twice for the same run does not error and does not duplicate staged
   files. *(R-02)*
4. A `tools: []` agent in a run **with** skills has the filesystem tool set bound — `read_file`
   **and** `write_file`/`edit_file` — and does **not** receive `_NO_TOOLS_PREAMBLE`; the same agent
   in a run **without** skills has the identical tool set and prompt it has today. *(R-05, R-04, C-01)*
5. A path outside the run sandbox (`../` traversal, absolute path) is rejected by the backend,
   confirming `virtual_mode=True` confinement. *(R-05, C-02)*
6. **`hello_html` end-to-end with `poet` attached — the first measurement of activation, not a
   regression check.** The skill is advertised to all three agents; `writer` emits a `read_file`
   call against `/skills/poet/SKILL.md`; the output is the two-line rhyme rather than the plain
   default line. Run on a frontier model **and** Ollama `qwen3.5:4b`; **record the activation rate
   for each**. A `qwen3.5:4b` failure is a finding to act on, not a blocker to work around —
   there is no fallback by design. *(R-03, D-01)*
7. No `SKILL.md` contains `compatible_agents`, `source`, or `sourceLabel`; `list_global_skills()`
   still returns 202 entries. *(R-12)*
8. No description exceeds 200 chars. *(R-13)*
9. No skill body opens by assigning the model an identity, and none directs use of `execute` or
   any tool outside the filesystem set plus the agent's own declared set. *(R-08, R-09)*
10. Re-running the sanitization audit reports zero provenance or foreign-AI-tooling matches, and
    every edited skill still teaches its original technique. *(R-11)*
11. The `agent_skills` event carries the advertised set, any `skills_load_errors`, and the
    estimated token cost. *(R-15, R-16)*
12. **D-02 watch:** a text-only pipeline (`user_stories`) run **with** a skill attached still
    produces a non-empty deliverable for every agent — i.e. granting `write_file` did not cause an
    agent to write a file instead of streaming its answer. *(D-02)*
13. `python -c "import app.main"` clean · `pytest tests/agents/ tests/unit/` green ·
    `npx tsc --noEmit` shows no new source errors.
