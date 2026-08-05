---
id: TEST-2-8
type: test
status: done
area: [resume, workflow, agents, artifacts, runtime]
summary: >-
  2.8 Engine fan-out / merge + wave scheduler & durable resume (register parts 11/12)
source: .planning/TEST-REGISTER.md#2-8-engine-fan-out-merge-wave-scheduler-durable
covers: [BE-FAN-01, BE-FAN-02, BE-FAN-03, BE-WAVE-01, BE-WAVE-02, BE-RES-01, BE-RES-02]
---

### 2.8 Engine fan-out / merge + wave scheduler & durable resume  (register parts 11/12)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-FAN-01 | Single `run_fanout` spawn path (declarative `fanout_batch` + runtime `spawn_subagents` funnel through it); **engine decides isolation/caps/merge, never the manifest (INV-7)**; reserve-before-spawn budget | `pytest tests/agents/test_fanout.py test_isolation.py test_budget.py` | 🟢 |
| BE-FAN-02 | `copy_disjoint` deterministic (sorted) + overlap→conflict (evicted, never silent overwrite); conflicts first-class (artifact+event+4 policies); parallel ≤ cap 4 | `pytest tests/agents/test_merge.py test_merge_conflict.py` | 🟢 |
| BE-FAN-03 | `subagent_runs` rows (never `workflow_runs`); cancellation tears down every allocation (zero residue); emits `subagent_spawned/result`, `merge_*`, `budget_*` | `pytest tests/agents/test_subagent_runs.py test_fanout_cancel.py` | 🟢 → drives UI TS-K |
| BE-WAVE-01 | `wave_scheduler` topo-sorts `json_tasks` into deterministic parallel waves (Kahn levels, conflict-key split), **one `run_fanout` per wave**, per-wave merge; cycle/dup → `WaveBuildError` pre-spawn | `pytest tests/agents/test_wave_scheduler.py test_json_tasks.py` | 🟢 → drives UI TS-K |
| BE-WAVE-02 | `wave_runs` rows (owner/workspace NOT NULL); emits `wave_started/completed/failed` + `subagent_*` carrying `wave_index`+`step` | `pytest tests/agents/test_wave_runs.py` | 🟢 → drives UI TS-K |
| BE-RES-01 | Per-step retry + content-hash reuse (restart-stable `input_hash`); WS `after_seq` replay (owner-scoped, idempotent by `event_id`); cross-owner reconnect → ∅ + `live:false` | `pytest tests/agents/test_step_retry.py test_ws_reconnect_replay.py` | 🟢 → drives UI TS-S |
| BE-RES-02 | Step-granular auto-resume incl. **mid-wave** (completed wave skipped wholesale, first incomplete wave re-runs in entirety); `workspace_id` recovered from durable owner-scoped row (not re-minted) | `pytest tests/agents/test_restart_resume.py` | 🟢 (live SIGKILL mid-wave-2 + restart ✅ in P12 UAT) |

---
## 3. UI end-to-end test suites (Playwright) — every user-observable behavior

> **Routing reality:** `/` redirects to `/login`. The entire app is `/dashboard` — a **single-page view state machine** (`MainView = home | input | execution | history | library | settings | analytics`), **not** a router. Flow: `home`(CreationHub) → select → `input`(IdeaInputPage) → Run → `execution`(2-panel). `prototype`/`ppt` are the exception — they hard-navigate to `/workflow/{prototype,ppt}/templates` wizards. **Dead/legacy (do NOT test):** `WorkflowView.tsx`, `WorkflowControls.tsx`, `PipelineGraph.tsx`+`AgentNode.tsx` (alt dark surface, unmounted), `WorkflowComposer.tsx`+`CapabilityPalette.tsx` (DELETED — ISS-014), `ValidatorIssuePanel.tsx` (built but unmounted).
