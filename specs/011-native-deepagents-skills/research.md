# Research Notes: Native `deepagents` Skills

Companion to [`plan.md`](plan.md). Everything here was read from the installed package or the
live codebase on 2026-08-10 — no claim below is from documentation alone.

---

## 1. Package verification (`deepagents==0.6.7`)

The venv at `venv/lib/python3.12/site-packages/deepagents/_version.py` reports `0.6.7`, matching
`backend/requirements.txt:42`. **A second, unrelated install exists** at
`/opt/homebrew/lib/python3.12/site-packages/deepagents` reporting `0.7.5` — a bare `python3` picks
that one up. Every verification below used the venv interpreter; anyone re-checking these facts must
do the same or they will be reading 0.7.x, whose `write_file` overwrite semantics the prototype
build loop does not tolerate (spec §5).

Confirmed against 0.6.7:

- `create_deep_agent(..., skills: list[str] | None = None, permissions=…, backend=…)` — `graph.py:217-236`.
- `skills is not None` ⇒ `SkillsMiddleware(backend=backend, sources=skills)` appended — `graph.py:715-716`.
  Note it is also appended to the general-purpose sub-agent stack (`graph.py:670-671`) and to
  declared sub-agents (`graph.py:598-600`); irrelevant to us — `task` is excluded, so no sub-agent runs.
- `_list_skills_with_errors(backend, source_path)` — `middleware/skills.py:573`: `backend.ls(source)`,
  keeps entries with `is_dir`, requires `<source>/<name>/SKILL.md`. A bare `SKILL.md` at the source
  root is never found. Source-level failures return a formatted error string rather than raising.

The remaining rows of the spec's §3 table (frontmatter key whitelist, 1,024-char description
truncation, `before_agent` per-thread caching, `allowed-tools` parsed-but-unenforced) were taken as
verified by the spec's own package read and were not re-derived.

---

## 2. Decision log

### T1 — Where does staging live?

| Option | Verdict |
|---|---|
| Engine, once per run before the agent loop | **Rejected.** Fan-out workers construct against an isolated `_ChildSandbox` (`engine.py::_isolated_run_sandbox`), whose root a run-level step never touches — those agents would advertise a directory that does not exist |
| `create_runner` (factory), idempotent | **Chosen.** The only point that sees the *effective* sandbox for this invocation, shared or isolated |
| `DeepAgentRunner.__init__` | Rejected. The runner receives a sandbox but not the attached-skill payload, and it is also constructed directly by `chat/concierge.py`, `handoff/coder.py`, `api/run_commands.py` — none of which should grow a skills path |

### T2 — Copy the catalog `SKILL.md`, or synthesize?

Copying looks obvious and is wrong. `skills_catalog._load_one` stores `post.content` — the body
with frontmatter **stripped** — and the run payload (`useWorkflow.ts:83-89`) forwards only
`{id, name, content, compatible_agents}`. There is no frontmatter anywhere in the path. A copy
would stage a file the `deepagents` parser rejects, and rejection is *silent*. Synthesis is the
only correct option, which also makes C-07 the normal path rather than a fallback.

Considered and rejected: mounting `backend/skills/global/` via `CompositeBackend` so the real files
are read directly. Out of scope per spec §5, and it would expose all 202 skills plus the whole
global catalog to the model's `read_file`.

### T3 — Stock preamble or custom (C-08 re-check)

Confirmed the constraint that drove C-08: a `system_prompt=` override to `SkillsMiddleware` must
contain `{skills_locations}`, `{skills_load_warnings}` and `{skills_list}` or the constructor raises
`ValueError` (`skills.py:786-825`). A custom preamble is therefore possible — but the decision
stands on evidence, not mechanics: prompt-stated precedence measures ~13–17% compliance and
collapses on small models. R-07 is discharged at authoring time by R-08/R-09 instead.

### T4 — What happens to `ectx.disk_skills`?

Traced: `engine.py:1543` loads `{agent_id: content}`; `engine.py:3453-3456` appends
`{"content": …}` (no `id`, no `name`) to `merged_skills`; that list becomes
`AgentContext.attached_skills` (`engine.py:3490`) and is rendered by
`factory._compose_system_prompt`. So the eager block is the disk skill's **only** delivery route,
and R-03's "delete the block" would take it with it. Spec §5 keeps disk skills eagerly injected, so
plan D6 splits them onto their own context field and preserves the render byte-for-byte —
including the `--- SKILL UNKNOWN ---` header the nameless disk entry produces today.

### T5 — Does `no_tools` need to change?

Yes, and it falls out of C-01 rather than being a separate decision. `factory.py:192` derives
`no_tools = exclude_builtin_tools and not custom_tools`; C-01 forces `exclude_builtin_tools=False`
whenever skills are staged, so `no_tools` becomes `False` automatically. The spec's flagged
second-order consequence is thereby structural, not a special case to remember.

### T6 — `execute`

`_BUILTIN_TOOLS` (`deep_agent_runner.py:95-108`) lists `execute`, documented there as exposed only
by sandbox backends and "a harmless no-op" under `FilesystemBackend`. Adding it to the exclusion
set when skills are staged changes no bound tool today and closes D-04 against a future backend
swap.

---

## 3. Unknowns

| # | Question | Resolution path |
|---|---|---|
| U1 | Will `qwen3.5:4b` actually call `read_file` on an advertised skill? | Acceptance 6, Phase 6 — measured, not guessed. This is D-01 and the plan does not depend on the answer |
| U2 | Do any of the 61 text-only agents write a file instead of streaming once given `write_file`? | Acceptance 12 is a build gate (D-02) |
| U3 | Exact provenance-contaminated file count | Spec measures union ≈ 40 (`claude` 26 · `ecc` 17 · `superpowers`/`obra` 5 · vendor names 3). `skills_audit.py --provenance` produces the authoritative list; `cursor` is excluded by design and that exclusion is itself tested |
| U4 | Whether the 464-token preamble constant still holds for 0.6.7's exact `SKILLS_SYSTEM_PROMPT` | Not re-measured. The estimate is advisory (R-16, warn-only), so drift costs a slightly wrong warning threshold, nothing else |

---

## 4. Measurements taken during planning

Re-run against `backend/skills/global/` with the venv interpreter — all four match the spec:

```
202 skill dirs
 42 descriptions > 200 chars
  1 description > 1024 chars   (silently truncated by deepagents today)
154 carry `source`
 13 carry a non-empty `compatible_agents`
```

---

## 5. References

- `specs/011-native-deepagents-skills/spec.md` · `clarifications.md`
- `venv/lib/python3.12/site-packages/deepagents/{graph.py,middleware/skills.py,_version.py}`
- `backend/agents/factory.py` — `create_runner:111`, `_filter_skills_for_agent:286`, `_compose_system_prompt:317`, `_resolve_runner_tools:844`
- `backend/app/agents/deep_agent_runner.py` — `_BUILTIN_TOOLS:95`, `__init__:299`, backend/graph assembly `:337-355`
- `backend/agents/execution_engine/engine.py` — `_load_disk_skills:6217`, disk merge + `agent_skills` `:3451-3485`, `create_runner` call `:3562`, `_isolated_run_sandbox:3055`
- `backend/app/agents/skills_catalog.py` · `backend/app/api/skills.py`
- Prior art in-repo: `specs/009-grading-dashboard/plan.md` (artifact-pack shape)
