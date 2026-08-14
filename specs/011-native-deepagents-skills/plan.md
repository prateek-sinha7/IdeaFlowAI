# Implementation Plan: Native `deepagents` Skills

**Spec**: [`spec.md`](spec.md)
**Clarifications**: [`clarifications.md`](clarifications.md) — C-01…C-08 resolved, D-01…D-04 accepted
**Created**: 2026-08-10
**Status**: Planned

---

## 1. Technical Context

| | |
|---|---|
| **Runtime** | Python 3.12, FastAPI + LangGraph; agents run through `agents/factory.py::create_runner` → `app/agents/deep_agent_runner.py::DeepAgentRunner` |
| **Library** | `deepagents==0.6.7` (pinned, `backend/requirements.txt:42`; the venv at `venv/lib/python3.12/site-packages/deepagents` confirms `__version__ = "0.6.7"`). **Not upgraded** — 0.7.x is out of scope per spec §5 |
| **Backend (fs)** | `FilesystemBackend(root_dir=str(run_sandbox.root), virtual_mode=True)` — `deep_agent_runner.py:338-339`. POSIX `/skills/` ⇒ `<sandbox.root>/skills/` |
| **Sandbox** | `app/agents/sandbox.py::RunSandbox`, rooted `<RUNS_ROOT>/<user>/<run>/`, **shared across every agent in a run**; fan-out workers pass an isolated `_ChildSandbox` override (`engine.py::_isolated_run_sandbox`) |
| **Catalog** | `backend/skills/global/<id>/SKILL.md` — **202 dirs**, loaded by `app/agents/skills_catalog.py::list_global_skills()` (cached; `clear_cache()` for tests) |
| **Attachment path** | UI → `POST /api/runs/...` (`app/api/run_commands.py:1460`) → `engine.execute(attached_skills=…)` → `AgentContext.attached_skills` → `factory._compose_system_prompt` |
| **Frontend** | Next.js/TS — `store/api/skills.ts`, `hooks/useSkillsCatalog.ts`, `components/library/LibraryPage.tsx`, `components/workflow/AgentsPopup.tsx`, `types/index.ts` |
| **Database** | **No schema change.** `attached_skills` is an existing JSON column on the workflow row (`app/api/user_workflows.py:463`); its payload shape is unchanged |
| **Tests** | pytest — `backend/tests/agents/` (incl. `characterization/`, `test_create_runner.py`), `backend/tests/unit/` |
| **Model calls** | Zero for the whole build. **One** live measurement at the end (acceptance #6), run by the user, not by the agent |

**Measured before planning** (re-run of the spec's inventory against `backend/skills/global/`):
202 skills · **42** descriptions > 200 chars · **1** > 1,024 (silently truncated today) ·
**154** carry `source` · **13** carry a non-empty `compatible_agents`. The spec's numbers hold.

---

## 2. Architecture Decisions

### D1 — Staging is one pure module, called from `create_runner`

New: `backend/app/agents/skill_staging.py`.

```python
stage_skills(sandbox, attached_skills) -> SkillsDelivery
#   writes <sandbox.root>/skills/<id>/SKILL.md, idempotently
#   returns .sources ["/skills"] · .staged [ids] · .errors [str] · .est_tokens int
```

`create_runner` is the **only** choke point that sees both the resolved sandbox and the
attached skills, and it already handles the fan-out worker's isolated sandbox override
(`run_sandbox=` param). Staging there covers the shared per-run sandbox *and* every isolated
worker sandbox with one call site — an engine-level "stage once per run" would silently skip
fan-out workers, whose `_ChildSandbox` has a different root.

**Idempotence (R-02)** is by content compare: read the target file, skip the write when bytes match.
Runner construction happens per agent against a shared directory, so N agents ⇒ 1 effective write.
No temp-file/rename dance — agents in a run are sequential and fan-out workers stage into their own
sandboxes, so there is no concurrent writer to guard against.

### D2 — Staged frontmatter is always synthesized, never copied

The attached-skill payload is `{id, name, content, compatible_agents}` (`useWorkflow.ts:83-89`),
and `content` is the **body only** — `skills_catalog._load_one` parses with `frontmatter.loads`
and stores `post.content`, so the frontmatter never reaches the payload. A staged file therefore
cannot be a copy; the loader would find no `name`/`description` and drop the skill silently.

Staging synthesizes:

```yaml
---
name: <skill dir id>        # must equal the directory name (deepagents parser)
description: <catalog description, clamped to 1024>
---
<body>
```

`description` is resolved from `list_global_skills()` by the payload `id`; a payload with no
catalog match falls back to its own `name` and a generated one-liner (C-07 — synthesize rather
than drop). This subsumes C-07 rather than treating it as an edge case: the normal path *is* the
synthesis path.

### D3 — `create_runner` re-orders: sandbox → stage → tools → prompt

Today the order is tools → prompt → sandbox (`factory.py:186-211`). Prompt composition needs to
know whether skills were staged (to suppress `_NO_TOOLS_PREAMBLE`), and staging needs the sandbox,
so the sandbox resolution moves above the tool/prompt block. `sandbox.ensure()` is a mkdir; it has
no ordering hazard.

```
sandbox = run_sandbox or RunSandbox(...); sandbox.ensure()
delivery = stage_skills(sandbox, ctx.attached_skills)      # empty ⇒ inert
custom_tools, exclude_builtin = _resolve_runner_tools(spec, ctx)
if delivery.staged:  exclude_builtin = False               # C-01 / R-05
no_tools = exclude_builtin and not custom_tools            # ⇒ False whenever skills staged
system_prompt = _compose_system_prompt(spec, ctx, no_tools=no_tools)
```

The `no_tools=False` fallout is the spec's flagged second-order consequence: an agent handed
`write_file` must not also be told it has no tools.

### D4 — The runner gains one parameter; `execute` joins the permanent exclusion set

`DeepAgentRunner(..., skills_sources: list[str] | None = None)` → `create_deep_agent(skills=…)`
(`graph.py:224`, `graph.py:715-716`). Stock preamble, no `system_prompt=` override (C-08), so none
of the `{skills_locations}`/`{skills_load_warnings}`/`{skills_list}` placeholder rules apply to us.

When `skills_sources` is set, the tool-filter exclusion becomes `{"task", "execute"}`:
`task` unconditionally (unchanged), `execute` because the stock preamble advertises script
execution we do not offer (D-04) and R-09 forbids directing it. `execute` is already a no-op under
`FilesystemBackend`, so naming it changes no bound tool — it is belt-and-braces against a future
sandbox backend.

### D5 — Delivery is reported from what was actually staged

`AgentContext` gains `skills_delivery: SkillsDelivery | None`, written by `create_runner`.
The engine's `agent_skills` yield **moves from before to after** the `create_runner` call
(`engine.py:3459-3485` → after `engine.py:3562`) and reports `advertised` (ids + names),
`load_errors`, and `estimated_tokens = 464 + 66 × n` — warning at 8,000/agent (C-05), never
blocking (R-16). Emitting before construction would report an intention, not a delivery, which is
exactly the silent-failure mode R-15 exists to close.

### D6 — Disk skills keep their eager path — via a separate context field

**This is the trap in R-03.** `engine.py:3451-3456` merges `ectx.disk_skills[spec.id]` into
`merged_skills`, which becomes `ctx.attached_skills`. Deleting the `=== SKILLS ===` block outright
would therefore also delete `ectx.disk_skills` injection — which spec §5 explicitly keeps
in scope-as-is.

Resolution: the engine stops merging. `AgentContext` gains `disk_skill: str | None`; the factory
renders **only** that value through the existing block-render code, byte-for-byte
(`--- SKILL UNKNOWN ---` … header included, since the disk entry carries no name today). Run-attached
skills no longer enter the prompt at all. A run with a disk skill and no attached skills keeps a
byte-identical prompt.

### D7 — Catalog migration is script-audited, human-edited

`backend/scripts/skills_audit.py` — one script, no modes. It reports every violation in one pass:
frontmatter (`name` == dir · `description` ≤ 200 · parses under the `deepagents` rules), identity
openings (R-08), and provenance hits (`claude` · `ecc` · `superpowers`/`obra` · vendor-LLM names —
**`cursor` excluded by design**). `--fix` does only the two mechanical removals
(`compatible_agents`, `source`/`sourceLabel`); descriptions and bodies are rewritten by hand.

The `cursor` trap from the spec is encoded as a *test* in the audit script, not a comment: a
regression that re-adds a blind `cursor` rule fails. Provenance and description rewrites are ~40 and
42 files respectively and are edited by hand — `sed` cannot tell a Cursor reference from a CSS
cursor, and cannot compress a description without losing the routing signal.

The script is then wrapped by `tests/unit/test_skills_catalog_hygiene.py` so acceptance criteria
7–10 are enforced continuously rather than at review time.

---

## 3. Delivery Strategy

Six phases. Phase 1 is the regression guard and lands first; the catalog work (Phase 5) is
independent of the runtime work and can proceed in parallel by a second pair of hands.

| # | Phase | Gate to exit |
|---|---|---|
| **0** | **Characterization pin.** Snapshot the composed system prompt for one text-only agent (`user_stories`) and one tool agent, with (a) nothing attached, (b) a disk skill only. These are the R-04/D6 oracles. | 2 new golden files committed; existing 5 characterization snapshots untouched |
| **1** | **Deletion + disk-skill rescue.** Delete `_filter_skills_for_agent` (factory + its engine import), delete `blocks["skills"]` for attached skills, add `AgentContext.disk_skill`, engine sets it instead of merging. | Phase-0 goldens byte-identical; `pytest tests/agents/` green |
| **2** | **Staging + runner wiring.** `skill_staging.py`, `create_runner` re-order (D3), `DeepAgentRunner(skills_sources=…)`, exclusion set, `no_tools` suppression. | Acceptance 2–5; a run with no skills constructs **no** `SkillsMiddleware` (asserted on the middleware list) |
| **3** | **Observability.** `SkillsDelivery` on the context, `agent_skills` event moved + enriched, token estimate + 8k warn, structured log line per agent. | Acceptance 11 |
| **4** | **Frontend.** Drop `compatible_agents` from `GlobalSkillEntry` (TS), `useSkillsCatalog`, `LibraryPage` skill chips (hook chips stay), `AgentsPopup` suggestion filter, `useWorkflow` payload field; render advertised-set + token cost in `AgentDetailPanel`. | `npx tsc --noEmit` no new errors; `LibraryPage.reskin.test.tsx` updated |
| **5** | **Catalog (202 files).** `skills_audit.py`; strip `compatible_agents`/`source`/`sourceLabel` (auto); rewrite 42 descriptions (hand); de-identity 3 bodies; de-provenance ~40 bodies. Drop the `compatible_agents` field from `GlobalSkillEntry` (Python) last, once nothing reads it. | Acceptance 7–10; `list_global_skills()` still returns 202 |
| **6** | **Live measurement.** `hello_html` + `poet`, frontier and `qwen3.5:4b`. **Run by the user** — record the activation rate for each in `build-summary.md`. | Acceptance 6; D-01 answered with a number |

Phase 5's `GlobalSkillEntry.compatible_agents` removal is deliberately last: `factory` (Phase 1),
the API serializer (`asdict`, automatic), and the frontend (Phase 4) must all be off it first.

---

## 4. File Changes

| File | Action | Purpose |
|---|---|---|
| `backend/app/agents/skill_staging.py` | **new** | `stage_skills()`, `SkillsDelivery`, frontmatter synthesis, token estimate (D1, D2) |
| `backend/agents/factory.py` | modify | new `AgentContext` fields `disk_skill` / `skills_delivery` (the dataclass lives here, `:30` — **not** in `execution_engine/context.py`, which is `ectx`); delete `_filter_skills_for_agent` + attached-skills block; re-order `create_runner`; render `ctx.disk_skill`; pass `skills_sources` (D3, D6) |
| `backend/app/agents/deep_agent_runner.py` | modify | `skills_sources` param → `create_deep_agent(skills=…)`; exclusion `{task, execute}` when skills present (D4) |
| `backend/agents/execution_engine/engine.py` | modify | stop merging disk skills; set `ctx.disk_skill`; move + enrich the `agent_skills` yield (D5, D6) |
| `backend/app/agents/skills_catalog.py` | modify | drop `compatible_agents` from `GlobalSkillEntry` (Phase 5) |
| `backend/agents/capabilities/skills/providers.py` | **leave** | `extract_ui_skill_blocks` still serves the disk-skill render + `test_guardrails.py:298`; not orphaned |
| `backend/scripts/skills_audit.py` | **new** | catalog audit/fix (D7) |
| `backend/skills/global/*/SKILL.md` | modify ×202 | R-11, R-12, R-13 |
| `backend/tests/agents/characterization/` | **new** ×2 | R-04 / D6 goldens |
| `backend/tests/agents/test_create_runner.py` | modify | staging, tool-set, `no_tools`, idempotence, traversal |
| `backend/tests/unit/test_skill_staging.py` | **new** | staging unit + frontmatter synthesis + token estimate |
| `backend/tests/unit/test_skills_catalog_hygiene.py` | **new** | acceptance 7–10 as tests |
| `frontend/src/store/api/skills.ts`, `hooks/useSkillsCatalog.ts`, `hooks/useWorkflow.ts`, `types/index.ts`, `components/library/LibraryPage.tsx`, `components/workflow/AgentsPopup.tsx`, `components/results/AgentDetailPanel.tsx` | modify | R-12 removal + R-15/16 surfacing |

`app/api/skills.py` needs no edit — it serialises with `asdict`, so dropping the dataclass field
propagates.

---

## 5. Test Strategy

Mapped to the spec's acceptance list; every item is offline except #6.

| Acceptance | Test |
|---|---|
| 1 — byte-identical no-skills prompt, no `SkillsMiddleware` | Phase-0 goldens + assert the constructed middleware list |
| 2 — 2 skills staged once, advertised to all agents | `test_skill_staging.py` + a 3-agent runner sweep |
| 3 — double construction is safe | call `create_runner` twice; assert mtime + content stable |
| 4 — `tools: []` agent gets read+write and no `_NO_TOOLS_PREAMBLE` | `test_create_runner.py` parametrised on skills present/absent |
| 5 — traversal rejected | write attempt at `../escape` and `/etc/passwd` through the backend |
| 6 — **live activation** | `hello_html` + `poet`, user-run, both models, rate recorded |
| 7–10 — catalog hygiene | `test_skills_catalog_hygiene.py` over all 202 |
| 11 — event payload | engine event assertion on advertised/errors/tokens |
| 12 — D-02 watch | `user_stories` with a skill attached; assert non-empty deliverable per agent |
| 13 — build health | `python -c "import app.main"` · `pytest tests/agents/ tests/unit/` · `npx tsc --noEmit` |

---

## 6. Risks & Mitigations

| ID | Risk (from spec) | Plan response |
|---|---|---|
| **D-01** | Activation unmeasured, no fallback | Phase 6 measures it explicitly on both models before the feature is called done. Nothing in the build depends on the answer; a `qwen3.5:4b` failure is recorded as a finding |
| **D-02** | 61 text-only agents gain `write_file`; deliverable comes from `ctx.last_streamed` | Acceptance 12 is a build gate, not a post-hoc check. If it trips, the narrow response is a staged-skill authoring rule (skills advertised to text-only pipelines must not prescribe file output), not a re-litigation of C-01 |
| **D-03** | Agents can edit their own staged skills | Accepted (C-02). Staging is idempotent per construction, so a mutated file is re-normalised on the next agent's construction within the same run |
| **D-04** | Stock preamble advertises `execute` and supporting files we don't stage | `execute` excluded at the tool filter (D4) so the advertisement cannot be acted on |
| **New — R-03/disk-skill collision** | Deleting the skills block silently kills `ectx.disk_skills` | D6: separate context field + byte-identical render, pinned by a Phase-0 golden |
| **New — payload has no frontmatter** | Naive staging writes an unparseable `SKILL.md`; deepagents drops it *silently* | D2 always synthesizes; a skill that still fails to load surfaces via `skills_load_errors` in the event (R-15) |
| **New — fan-out workers** | Isolated `_ChildSandbox` roots would miss a run-level staging step | Staging lives in `create_runner`, which already receives the isolated sandbox |

---

## 7. Notes on the apex tooling

`.apex/scripts/audit-log.js` and `.apex/stack.json` are absent in this checkout, so the
`/apex:plan` audit-log and stack-validation steps were skipped. The artifact pack itself follows
the repo's established shape (`specs/008-*`, `specs/009-*`): `plan.md` · `research.md` ·
`data-model.md` · `quickstart.md` · `contracts/`. `tasks.md` is generated next by `/apex:design`.
