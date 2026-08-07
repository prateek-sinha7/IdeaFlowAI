---
inclusion: fileMatch
fileMatchPattern: "backend/app/api/**"
---

# Backend — API Layer Domain

> Loaded when editing files under `backend/app/api/`. See `invariants.md` for hard constraints.

---

## Transport Architecture (v2.0+)

| Direction | Mechanism | File |
|-----------|-----------|------|
| Events → client | SSE (`GET /api/runs/{id}/events/stream`) | `run_stream.py` |
| Commands → server | REST POST endpoints | `run_commands.py` |
| Shared run infra | Registry, validators, owner gates | `run_engine.py` |
| Handoff only | `/ws/handoff/{token}` WebSocket | `websocket_handoff.py` |

**`websocket.py` is DELETED** (Phase 44). Do not recreate it. Do not add any `/ws/chat` endpoint.

---

## `run_engine.py` — Shared Infra (relocated from `websocket.py`)

Contains the shared symbols all API handlers use:
- `_PIPELINE_QUEUES` / `_CANCEL_EVENTS`
- `_get_or_create_queue` / `_cleanup_pipeline`
- `_register_resume_queue` / `_register_resume_task`
- Owner/terminal fences: `_review_gate_owned_by` / `_review_gate_run_is_terminal` / `_resolve_owned_parent_run_id`
- Ingress validators: `_validate_model_overrides` / `_validate_images` / `_revalidate_selections_trust_user`
- `_authenticate_token` / `_get_db`

**Do NOT duplicate** any of these in `run_commands.py` or `run_stream.py` — import from `run_engine`.

---

## `run_stream.py` — SSE Down-Channel

- Two-layer owner check before streaming: ORM `WorkflowRun.user_id` filter + `ScopedStore.get_run` default-deny → 404 (never 403).
- Generator uses a **session-less** `ScopedStore` (no `session=`): each `read_events` call is owned=True and releases the connection in `finally`. The request-session store backs only the pre-stream owner checks (BUG-004 fix).
- `_STREAM_TERMINAL_TYPES` excludes `review_gate_approved` — approving a gate resumes the run, does NOT close the stream (BUG-016 fix).
- Replay from `Last-Event-ID`; durable replay is followed by a `stream_attached{live, replayed_through_seq}` handshake.
- Pool sizing: `pool_size=20, max_overflow=40` on Postgres; `{}` on SQLite.

---

## `run_commands.py` — REST Up-Channel

### Owner check pattern (IDOR)
Every handler uses the two-layer gate:
```python
# Layer 1 — ORM filter (never nullable owner_id)
wr = db.query(WorkflowRun).filter(
    WorkflowRun.id == run_id,
    WorkflowRun.user_id == current_user.id
).first()
if not wr:
    raise HTTPException(404)
# Layer 2 — ScopedStore default-deny
store_run = scoped_store.get_run(run_id)
```
Cross-owner and missing-run → **404, never 403** (IDOR by design).

### Launch → attach seam
After `POST /api/runs` creates a run, `attachRun(runId)` on the FE connects the SSE stream. The `sendCommand` adapter in `page.tsx` must `await` the POST before the re-fetch fires (BUG-017 fix).

### Gate actions (`POST /api/runs/{id}/gate`)
- 4 actions: `approve` / `reject` / `redo` / `update_specs`
- `update_specs` triggers `_run_spec_revision_sub_pipeline` (KAN-101, Phase 27)
- IDOR: run ownership checked via `_review_gate_owned_by` BEFORE writing to the store
- `review_gate_approved` is NOT a stream terminal (BUG-016 fix)

### Concierge path (`POST /api/runs/{id}/messages`)
- `MessageCommand.concierge=True` → streaming `EventSourceResponse` (Phase 43/m0o)
- Proposal-only: `propose_steering_note`, `propose_revision`, `propose_gate_action` — never self-execute
- Consequential proposals (gate_action, revision) held behind a durable `concierge-proposal:{message_id}:{channel}` pending row (H1 server-enforce)
- Confirm turn: `body.confirm_proposal` selects the durable row; missing/cross-owner/resolved → 404

### Selections trust=user (Phase 22 / CAP-03)
- At SAVE (`user_workflows._compile_selections_trust_user`) AND LAUNCH (`_revalidate_selections_trust_user`), selections are compiled with `trust="user"`.
- User/db manifests referencing `user_allowed=False` capabilities → `CompilerError`.

### `run_revision` retirement (Phase 44)
- PPT/od_ppt revisions via `POST /api/runs/{id}/revisions` (REST byte-twin of `engine._handle_revision`)
- `_handle_revision` in `engine.py` STAYS — only the WS driver was deleted
- `od_ppt_revision` is wired via `effectiveReviseType` in `DashboardLayout`

---

## `runs.py` — Run CRUD & Read Endpoints

- `GET /api/runs/{id}/family` — BFS over owned children, `created_at ASC` order, 1-based `revision_index`
- `GET /api/runs/{id}/summary` — aggregates existing columns, zero new tables; `_SUMMARY_SAFE_AGENT_KEYS` allow-list projection (raw output/input_prompt never echoed)
- `GET /api/runs/{id}/gate-events` / `/validation-results` / `/exec-runs` — owner-scoped, `_owner_gate_or_404`
- `GET /api/runs/{id}/artifacts?kind=<kind>` — kind filter applied before `_build_lineage_tree`
- `parent_run_id` + server-computed `root_run_id` on `WorkflowRunResponse` (computed from an owned-ancestor walk)
- Owner-scoping: `WorkflowRun.user_id == current_user.id` — **never** the nullable backfilled `owner_id`

---

## `analytics.py` — Analytics Aggregations

- `GET /api/analytics/summary?range=<enum>` — owner-scoped collection filter (`user_id == me`)
- Range allow-list: `today/3d/7d/30d/90d/all`; unknown → 30d default (no 422)
- Numbers only in response — no raw run rows, no agent output echoed
- `token_usage` parsed per-run in try/except → `{}` fallback (DoS guard)

---

## `workflows.py` — Manifest Definitions

- `GET /api/workflows` — manifest list, DB-free, sourced from `PIPELINE_AGENTS` + `load_manifest`
- Surfaces: `user_launchable` / `display_name` / `description` / `icon` / `launch_surface`
- `user_launchable: true` in the manifest = appears in the catalog. **Never** a hardcoded name list.

---

## `user_workflows.py` — Saved Workflows CRUD

- `POST /api/user-workflows` — save-time validation reuses EXACT launch predicates
- `PATCH` / `DELETE` — IDOR→404 via `_owned()` filter (`id AND user_id AND source=="user"`)
- Persists compact `{agent_id:{validators?,gates?,model?,retry?}}` in the reused `manifest_json` column
- **No new table** — reuses `workflows` table with `source="user"` (migration 0021, 3 nullable cols)

---

## Auth Rules

- All endpoints: `Depends(get_current_user)` — no endpoint is unauthenticated
- `user_id` is the authz key (NOT the nullable backfilled `owner_id`)
- Handoff endpoint (`/api/handoff`) is a LIVE external IDE surface — do NOT delete it
