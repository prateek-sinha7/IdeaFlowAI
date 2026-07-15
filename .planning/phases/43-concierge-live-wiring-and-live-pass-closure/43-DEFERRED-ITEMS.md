# Phase 43 — Deferred Items

Items surfaced during execution that are intentionally deferred within the phase (not dropped). Each names its owning plan so the goal cannot evaporate.

---

## DEF-43-03-1 — Narrator A.4 live injection + seq-allocator reconciliation

**Surfaced by:** 43-03 (narrator live call-site + nonce hardening), 2026-07-15.
**Status:** Deferred → **owned by 43-06** (the supervised SSE cutover). Tracked in 43-06 `files_modified` (`backend/app/api/run_commands.py`) + `must_haves` + `requirements: A.4`.

**What 43-03 delivered (offline, done):** the dormant narrator injection SEAM — `engine.execute(milestone_sink=None)` + `_RunEventSink.emit_milestone_card` at the run_events sink boundary; `persist_milestone_card` reaches the kernel only as an injected callback (no `chat_narrator` import in the engine — INV-12/ports-&-adapters). Proven end-to-end by `TestEngineSinkWiring`. Dormant by default (`milestone_sink=None`), so it fires on ZERO golden paths (goldens byte-identical, 10/10).

**What remains (live, 43-06):** flip the injection ON by passing `milestone_sink=persist_milestone_card` at the **surviving** engine call-site.
- **Correct call-site:** `backend/app/api/run_commands.py:1243` (the SSE/POST `engine.execute(...)`). **NOT** `backend/app/api/websocket.py:2021` — that legacy-WS call-site is deleted by 43-09. (43-03's SUMMARY named websocket.py; the A.0-(a) decision makes run_commands.py the correct post-cutover target.)
- **The load-bearing reconciliation (why it was deferred, not done inline):** the engine sink stamps outward-event `seq` from an in-memory `itertools.count`; the narrator card persists via `ScopedStore.append_event_next_seq` (max-persisted + 1) — two independent allocators. Wiring the narrator inline in the per-event loop makes a card take the next engine seq, so the following engine event's persist collides and degrades → a durable-log gap on live reconnect. Resolve safely (share the engine counter, or reconcile the allocator — the same independent-allocator coexistence Phase 29 arbitrated for the `chat_message` up-channel with the `0024` uniqueness constraints) as part of the supervised cutover, then verify milestone cards emit live over the SSE down-channel.
- **Nonce prerequisite (done):** the deep-link nonce is already DB-backed / owner-scoped / single-use (WR-02, migration `0025`), so the live milestone card's deep-link is safe to expose at cutover.

**Acceptance at 43-06:** with SSE live, a run that reaches a milestone persists + emits a milestone card over the SSE down-channel (recorded evidence); no seq collision / durable-log gap (a mid-run reconnect replays the full event log including the card); goldens re-run 10/10 byte-identical.
