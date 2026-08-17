---
id: 260812-wir
status: complete
date: 2026-08-12
---

# quick-260812-wir — terminal durability + terminal-reopen render + lost-event audit

Ordered deliberately: ISS-124 first, because it was still MINTING the corrupted runs
ISS-126 has to render — fixing the display while the source keeps producing the condition
is half a fix.

1. **ISS-124 → FIX-244** (backend). Give both app-layer driver terminals a durable
   `run_events` write via FIX-243's collision-safe `_record_cancellation_in_the_durable_tail`,
   extended with a `reason` parameter (INV-12: extend, never copy).
2. **ISS-126 → FIX-245** (frontend). Reconcile a reopened run against its PERSISTED status,
   after the durable replay loop, one-way. Reduce terminal-marker deciders 3 → 1.
3. **ISS-123 → FIX-246**. Read-only forensic audit only. **Never back-fill `run_events`.**

Gates: goldens 10 / 0 files moved · lint-imports 4 kept / 0 broken · failing test IDs
unchanged (never counts) · a real-browser A/B on `808612bf` vs `1ea6d262`.
Money rules: never launch, resume, approve or cancel any run.
