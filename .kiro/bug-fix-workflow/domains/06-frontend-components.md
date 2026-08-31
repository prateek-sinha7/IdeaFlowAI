# Domain 6 — frontend·components

10 cards, 3 batches.

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-409 | TESTED | B1 | 1 | `frontend/src/components/handoff/IntegrationsCard.tsx` | A′ (ISS-409 sibling of ISS-301/FIX-370; ISS-481 sibling of ISS-320/FIX-385) | replicate → verify | haiku |
| ISS-481 | TESTED | B1 | 1 | `frontend/src/components/handoff/IntegrationsCard.tsx` | A′ (ISS-409 sibling of ISS-301/FIX-370; ISS-481 sibling of ISS-320/FIX-385) | replicate → verify | haiku |
| ISS-073 | ANALYZED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-112 | ANALYZED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-114 | ANALYZED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-216 | ANALYZED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-434 | ANALYZED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-600 | ANALYZED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-117 | ANALYZED | B3 | 4 | `frontend/src/components/results/AgentDetailPanel.tsx` | C | full | haiku |
| ISS-387 | ANALYZED | B3 | 4 | `frontend/src/components/results/AgentDetailPanel.tsx` | C | full | haiku |

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
Status: the `status` column above is authoritative — it is what the line
reads and writes. A whole-file status could only drift from it.
