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

### Precise seq-collision analysis (orchestrator, 2026-07-15 — do NOT guess-implement this)
Reading the live path pinned the exact mechanism, and it is a real durable-log hazard:
- The engine stamps every outward event from `counter = itertools.count(1)` (`engine.py:966`) and persists it at that seq via `sink.persist(seq, …)` (`engine.py:972`) — a **contiguous, engine-owned** seq space — THEN calls `emit_milestone_card(event)` (`engine.py:973+`).
- `persist_milestone_card` writes the card via `ScopedStore.append_event_next_seq` = **max-persisted + 1**. During the processing of engine event N (max-persisted = N), the card takes **N+1**.
- The engine's NEXT loop iteration takes `next(counter)` = **N+1** and persists at N+1 → **collision on the `0024` per-run-seq uniqueness constraint**. Because `sink.persist` is best-effort (degrades a `SQLAlchemyError` to a warning, INV-3), the **engine event N+1 silently fails to persist → a GAP in the durable replay log** → a mid-run reconnect misses that engine event.
- The Concierge `chat_reply` (seq 17909, verified in B.3) does NOT hit this because it fires on a **settled/idle** run (no live `itertools.count` active) — so the settled-run persist is safe, but the **mid-run** narrator persist is not.

**Fix options (a design decision, then offline collision test + live reconnect validation — NOT a rushed edit):**
1. **Route the card through the engine's own counter** — instead of an out-of-band `append_event_next_seq` write, have the narrator YIELD the card as an engine event so it gets `next(counter)` and is persisted contiguously like any other event (cleanest; the card becomes a first-class stamped event).
2. **Make the card+engine share one allocator** — reconcile so the card and the engine never draw the same seq (e.g., the card reserves via the same `counter`).
3. **Collision-retry** — on the unique-constraint failure, the LOSER (card) retries with the next seq AND the engine's persist must be made non-best-effort for the real-run case so an engine event never silently drops (today it degrades, which is the gap source).

**Why deferred, not done this session:** this is subtle concurrency on the durable event log (high blast radius — a wrong reconciliation silently gaps run-reconnect replay). It needs a deliberate design choice + an offline test proving a milestone event and the subsequent engine event get distinct seqs + a live reconnect proving no gap — dedicated focus, not an end-of-session edit. Everything ELSE in 43-06 (the SSE cutover + B.3) is done; this is the isolated remaining backend piece.
