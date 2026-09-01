# Domain 6 — frontend·components

10 cards, 3 batches.

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-409 | CLOSED | B1 | 1 | `frontend/src/components/handoff/IntegrationsCard.tsx` | A′ (ISS-409 sibling of ISS-301/FIX-370; ISS-481 sibling of ISS-320/FIX-385) | replicate → verify | haiku |
| ISS-481 | CLOSED | B1 | 1 | `frontend/src/components/handoff/IntegrationsCard.tsx` | A′ (ISS-409 sibling of ISS-301/FIX-370; ISS-481 sibling of ISS-320/FIX-385) | replicate → verify | haiku |
| ISS-073 | ALREADY_FIXED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-112 | ESCALATED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-114 | ALREADY_FIXED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-216 | ALREADY_FIXED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-434 | ESCALATED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-600 | CLOSED | B2 | 2 | frontend·components (mixed) | B/C | full | haiku |
| ISS-117 | CLOSED | B3 | 4 | `frontend/src/components/results/AgentDetailPanel.tsx` | C | full | haiku |
| ISS-387 | CLOSED | B3 | 4 | `frontend/src/components/results/AgentDetailPanel.tsx` | C | full | haiku |

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

## Run result (2026-09-01)

- **CLOSED:** ISS-409 (FIX-451), ISS-481 (FIX-452), ISS-600 (FIX-453), ISS-117 (FIX-454), ISS-387 (FIX-455)
- **ALREADY_FIXED:** ISS-073, ISS-114, ISS-216
- **ESCALATED:** ISS-112 (no FE attachment-ref data source), ISS-434 (needs PipelineRunState.deliverableMimetype)
- tsc: clean · tests: 11 passing · dedup: 178 open → 156 units
