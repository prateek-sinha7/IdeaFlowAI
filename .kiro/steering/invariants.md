---
inclusion: always
---

# IdeaFlowAI — Invariants

> The canonical source is `.knowledge/INVARIANTS.md` — loaded here directly.

#[[file:.knowledge/INVARIANTS.md]]

---

## Transport Contract (v2.0+)

- **Down-channel:** per-run SSE (`GET /api/runs/{id}/events/stream`)
- **Up-channel:** REST commands (`POST /api/runs/{id}/gate|answers|cancel|messages|revisions`)
- **Shared run infra:** `backend/app/api/run_engine.py`
- `/ws/handoff` is the **only** remaining WebSocket — do not touch it.
- Banned-pattern CI ratchet (`test_sse_cutover_banned_patterns.py`) enforces 5 retired WS tokens.

## What NOT to Resurrect

| Symbol / File | Deleted in | Reason |
|---------------|-----------|--------|
| `accumulated_outputs` dict | Phase 5 (L15) | Replaced by `ArtifactGraph` |
| `agents/prototype/` package | Phase 7 | All behavior moved to capabilities |
| L1–L13 branches in `engine.py` | Phase 7 | Dissolved into capabilities |
| F1–F5 factory leaks | Phase 8 | Dissolved into capabilities |
| `/ws/chat` endpoint + `websocket.py` | Phase 44 | SSE cutover complete |
| `useWebSocket.ts` | Phase 44 | SSE cutover complete |
| `ReviewGatePanel.tsx` (full-screen) | Phase 42 | Inline gate actions supersede it |
| `QuestionnairePanel.tsx` (full-screen) | Phase 42 | Inline clarify actions supersede it |
| `AgentProgressPanel.tsx` | Phase 42 | Absorbed into RunChatLane |

## INV-3 — Golden Safety Checklist

Before merging any backend change:
1. `pytest tests/agents/test_characterization_*.py` — `SNAPSHOT_UPDATE` must be unset
2. New `pipeline_complete` fields go in `_VOLATILE_STRIP_KEYS`
3. New chat event types go in `_DOCUMENTED_EVENT_TYPES`
4. `git status --porcelain tests/agents/characterization/golden/` → empty

## SC-001 — Kernel Name-Free Checklist

- `grep -rn "if pipeline_type ==" agents/execution_engine/` → 0
- `grep -rn 'spec\.id ==' agents/execution_engine/` → 0
- `test_banned_patterns.py` (11 tests) all pass
