# API Contract: Native `deepagents` Skills

No new endpoint, no new route, no schema migration. Three existing contracts change shape.

---

## 1. `GET /api/skills/library` — catalog listing

`backend/app/api/skills.py:28` · serialises `GlobalSkillEntry` via `asdict`.

**Change**: the `compatible_agents` key disappears from every entry (R-12). Nothing else moves.

```diff
 {
   "skills": [
     { "id": "poet", "name": "poet", "display_name": "Poet",
       "description": "Write a two-line rhyming couplet. Use when asked for verse.",
       "content": "<body>", "isBeta": false, "category": "writing",
-      "compatible_agents": [],
       "tags": ["writing"] }
   ],
   "total_count": 202,
   "categories": [ { "id": "all", "label": "All" }, ... ]
 }
```

`total_count` **stays 202** — the guard that the catalog edit did not break parsing.

Consumers to update: `frontend/src/store/api/skills.ts` (`GlobalSkillEntry`),
`hooks/useSkillsCatalog.ts`, `components/library/LibraryPage.tsx` (skill chips only — hook chips at
`:380`/`:394` read the *hooks* catalog and stay), `components/workflow/AgentsPopup.tsx:501`
(the skill-suggestion filter is deleted; the hook filter at `:502` stays).

**Hooks are unaffected.** `GET`-side hook entries keep `compatible_agents`
(`app/agents/hooks_catalog.py:41`).

---

## 2. Run launch — `attached_skills` request field

`backend/app/api/run_commands.py:1460` (`attached_skills: list[dict] | None`), also persisted on
the saved-workflow row (`app/api/user_workflows.py:79/96/112`).

**Change**: the client stops sending `compatible_agents` (`useWorkflow.ts:88`). The field was never
read from the payload — the backend cross-referenced the *catalog* — so this is a client-side
cleanup, not a contract break.

```diff
 "attached_skills": [
-  { "id": "poet", "name": "poet", "content": "<body>", "compatible_agents": [] }
+  { "id": "poet", "name": "poet", "content": "<body>" }
 ]
```

**Compatibility**: unknown keys are ignored, so old clients and persisted rows carrying
`compatible_agents` keep working unchanged. No migration.

---

## 3. `agent_skills` SSE event — delivery report

`backend/agents/execution_engine/engine.py:3459-3485`.

**Changes**: (a) emitted **after** `create_runner` rather than before, so it reports what was
actually delivered; (b) `attached_skills` is the run-attached set advertised to this agent —
unfiltered, because there is no per-agent filter any more (R-01); (c) two new keys.

```diff
 { "type": "agent_skills",
   "data": {
     "agent_id": "writer",
     "attached_skills": [ { "name": "poet", "source": "", "content": "<body>" } ],
     "attached_hooks":  [ ... ],
+    "skills_load_errors": [],          // R-15 — empty list, never omitted
+    "estimated_tokens": 530            // R-16 — 464 + 66 × n, advisory
   } }
```

`content` is retained for the UI's expandable skill rows (`AgentDetailPanel.tsx`), but it is
**no longer what the model receives** — the body now enters context only if the model calls
`read_file`. The panel copy must say "advertised", not "injected".

Consumers: `frontend/src/hooks/useWorkflow.ts:679`, `types/index.ts:565/601`,
`components/results/AgentDetailPanel.tsx:193`, `lib/wsReplayState.ts:112`,
`app/dashboard/page.tsx:693` (event allow-list — already includes `agent_skills`, no change).

---

## 4. Internal call contracts (not HTTP, but binding)

| Callable | Change |
|---|---|
| `agents.factory.create_runner(agent_id, ctx, *, checkpointer, interrupt_on, thread_id, run_sandbox)` | Signature unchanged. Now stages skills and writes `ctx.skills_delivery` as a side effect |
| `agents.factory._filter_skills_for_agent` | **Deleted.** Also delete its import in `engine.py` |
| `app.agents.deep_agent_runner.DeepAgentRunner.__init__` | New keyword-only `skills_sources: list[str] | None = None`. Default `None` ⇒ construction identical to today for `chat/concierge.py`, `handoff/coder.py`, `api/run_commands.py:2335` |
| `app.agents.skill_staging.stage_skills(sandbox, attached_skills) -> SkillsDelivery` | **New.** Pure, idempotent, never raises on a bad skill — failures land in `.errors` |
| `app.agents.skills_catalog.GlobalSkillEntry` | Field `compatible_agents` removed |
