# Domain 11 — frontend·hooks

16 cards, 2 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 3 | `frontend/src/hooks/useWorkflow.ts` | BUG-014-B-GROUNDED-CONTEXT, FIX-BUGFIX-SPEC-REVISION-CONTEXT, ISS-108, ISS-109, ISS-110, ISS-115, ISS-116, ISS-142, ISS-417, ISS-438, ISS-439, ISS-440 | A′ (ISS-417 sibling of ISS-304; ISS-438-440 stale-state sibling of ISS-232) + B (stale-state) + C | full; one read | **sonnet** (12 cards, core hook, stale-state reasoning) |
| B2 | 6 | `frontend/src/hooks/useRunChat.ts` | BUG-018-GROUNDED-CONTEXT, BUG-021-GROUNDED-CONTEXT, ISS-111, ISS-141 | C | full | haiku |

Notes:
- B1 `useWorkflow.ts` — the central state hook, heavily referenced. Dominant theme:
  stale-state (pipeline_start spreading ...prev without clearing hookRuns ISS-110,
  retainClarifyRound no reset ISS-108, unmemoized/dead-event reducers ISS-109/116,
  useWorkflow's own Task-N regex separate from FIX-237's parser ISS-115). Sonnet
  because these are interleaved state-management defects and fixing one carelessly
  breaks another.
- ISS-417 replicates ISS-304/FIX-373 (TokenUsageSummary destructures same corrupt
  cost fields). ISS-438-440 replicate ISS-232/FIX-340 (stale pipelineState.agents).
- B2 `useRunChat.ts` — terminal runs show actionable clarify card (ISS-141),
  messages never cleared on fresh non-revision launch (BUG-021), chat_narrator
  spec_revision branch unreachable (ISS-111), BUG-018 collision merge. Lower round,
  no overlap.
- Secondary globs: `useRunStream.ts`, `RunConnectionProvider.tsx`,
  `useWorkflow.reconnect.test.ts` — these span the SSE surface, which is not owned
  by this domain. Do not edit them; escalate.

Collision note: useWorkflow.ts and useRunChat.ts owned here. useRunStream.ts/
RunConnectionProvider.tsx are cross-domain SSE surface — escalate, never edit from here.
Status: NOT STARTED.
