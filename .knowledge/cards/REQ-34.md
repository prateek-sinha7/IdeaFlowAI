---
id: REQ-34
type: req
status: done
area: [resume, workflow, auth]
summary: >-
  Reopen & Fix (Phase 50 [R5])
source: .planning/REQUIREMENTS.md#reopen-fix-phase-50-r5
---

### Reopen & Fix (Phase 50 [R5])

- [x] **RESUME-18**: A user can resume a terminal-FAILED run via `POST /api/runs/{id}/resume`: two-layer owner check (`user_id`, 404 never 403), overlap-guarded (`pipeline_already_running` precedent) and replay-idempotent (the P33 M4 lesson); recovers workspace_id from durable rows (never fresh-minted — Pitfall 2), `selections_json` (0023), completed steps/tasks via the cursor, and disk via re-materialization; re-registers in `_PIPELINE_QUEUES` BEFORE FE attach (BUG-015 live-attach semantics) reusing the `run_engine.py` bridge — NO third hand-copied driver; status transition (failed→running or a `run_resuming` EVENT per INV-12 preference) makes FE `AUTO_STREAM_STATUSES` auto-attach; live-layer callbacks threaded (RESUME-10 mechanism). Authorized by the LOCK-E/ND-4 supersede record (POR §8.1).

## Fan-Out User-Facing Requirements — User-Composable Fan-Out (Phase 51 [PB])

**Added:** 2026-07-20 · **Source of truth:** `.planning/PATH-B-FANOUT-COMPOSER-SCOPE.md` (implementation-ready, file:line-verified) + `.planning/FANOUT-USER-FACING-SCOPE.md`. Exposes the Phase-11 fan-out kernel to the composer with **no new engine power** (no security/trust flag flip, no new capability kind, no migration).
