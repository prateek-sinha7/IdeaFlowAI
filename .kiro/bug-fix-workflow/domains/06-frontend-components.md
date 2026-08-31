# Domain 6 — frontend·components

10 cards, 3 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | `frontend/src/components/handoff/IntegrationsCard.tsx` | ISS-409, ISS-481 | A′ (ISS-409 sibling of ISS-301/FIX-370; ISS-481 sibling of ISS-320/FIX-385) | replicate → verify | haiku |
| B2 | 2 | frontend·components (mixed) | ISS-073, ISS-112, ISS-114, ISS-216, ISS-434, ISS-600 | B/C | full | haiku |
| B3 | 4 | `frontend/src/components/results/AgentDetailPanel.tsx` | ISS-117, ISS-387 | C | full | haiku |

Notes:
- B1 both A′: ISS-409 replicates FIX-370 (empty-catch leaves state at defaults);
  ISS-481 replicates FIX-385 (delete with zero confirm). Skip validate/analyze.
- B2 is a mixed bag across component files (InlineGateActions, AgentThinkingTab/
  StartingPointCard, ResultCard, tsc-error files, RunChatLane, copy-feedback test).
  Several are stale-test/tsc-arity fixes. Split into sub-tasks per file if a single
  worker's context gets heavy — they are disjoint files so still one round.
- B3 AgentDetailPanel: ISS-387 (history push on agent/task select) + ISS-117
  (replay allowlist omits validator_result/gate_passed). Secondary globs into
  `useRunStateStore.ts` (domain 11 hooks) — escalate if the fix must edit it.

Collision note: AgentDetailPanel.tsx / IntegrationsCard.tsx owned here. AuditTab.tsx
(shared with domain 5) — do not edit. useRunStateStore.ts is domain 11's.
Status: NOT STARTED.
