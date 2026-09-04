# Escalated — Domain 14: backend·api

11 cards with status `ESCALATED`.

---

## ISS-134 — Cancel-liveness: process-local dict (ECS migration concern)

| field | value |
|---|---|
| card | ISS-134 |
| domain | 14-backend-api |
| batch | B1 |
| fix site | backend·api (mixed) |
| reason for escalation | The cancel mechanism uses a process-local in-memory dict. This is an **architecture concern for the ECS migration** — in a multi-process / multi-container deployment, cancels issued to one process won't reach runs living in another. Fixing it correctly requires a shared cancel-signal store (e.g. DB flag, Redis, or SSE/queue). |
| decision needed | **Architecture / infrastructure decision:** choose the shared cancel-signal mechanism before implementing the fix. Coordinate with the ECS migration plan. |
| card status | ESCALATED |

---

## ISS-419 — Gate seeding reverses FIX-377's locked constraint (ADR-0013)

| field | value |
|---|---|
| card | ISS-419 |
| domain | 14-backend-api |
| batch | B1 |
| fix site | `frontend/src/components/workflow/ReviewGatesSection.test.tsx` (test asserts manifest `approval`/`security` gate seeds checkbox CHECKED) |
| reason for escalation | The test asserts behaviour that reverses FIX-377's locked constraint: seeding a manifest `approval`/`security` gate as CHECKED, then toggling it, writes `gates: [approval, human]` — **rejected at `compiler.py:806-811` (ADR-0013)**, and there is no runtime dedupe for `approval` (`engine.py:6491`). Both gates are `user_allowed=False` (engineer-only). Full reasoning + 3 options recorded on the ISS-419 card. |
| decision needed | **Product / architecture decision:** choose one of the 3 options on the ISS-419 card (suppress seeding, gate-only final task, or leave locked + reword copy). Must align with ISS-377 (domain 12) and ADR-0013. |
| card status | ESCALATED |

---

## ~~ISS-119~~ — CLOSED ✓

**Closed:** routing test names were already reconciled upstream; no red defect remains.
A coverage test written against the card's remaining ask passed first try — not a defect proof.
No `xfail(strict=True)` test was possible; nothing to fix.

---

## ~~ISS-133~~ — CLOSED ✓

**Closed:** stale duplicate of ISS-125 / FIX-421 (already shipped).
Fix is live at `engine.py:7694-7755` — `_stamp_resume_marker` already uses the
collision-safe `_max_event_seq` + `append_event_at_or_after` pair.

---

## ~~ISS-161~~ — CLOSED ✓ (already-fixed by Phase 33/43 Concierge wiring)

**Closed:** The bug was a question on a terminal run routing to `CHANNEL_REVISION`.
Today `chat_router.py:215` catches any `concierge=True` turn **before** the
`PHASE_TERMINAL` branch: `if turn.concierge and turn.action not in GATE_ACTIONS ...
→ CHANNEL_CONCIERGE`. "How many tokens did this run use?" through the concierge lane
now correctly reaches the Concierge model. Plain-text non-concierge turns on a terminal
run correctly remain `CHANNEL_REVISION` (that is the intended behaviour for that path).
No code change needed.

---

## ISS-398 — Sibling of ISS-292 (up-channel gate race)

| field | value |
|---|---|
| card | ISS-398 |
| domain | 14-backend-api |
| batch | B2 |
| fix site | `backend/app/api/run_commands.py` |
| reason for escalation | Escalated by fixer. Tier-A′ sibling of ISS-292 but could not be resolved within domain boundary. Full detail on the ISS-398 card. |
| decision needed | **Human review of card ISS-398** to confirm the sibling fix shape and approve the change. |
| card status | ESCALATED |

---

## ~~ISS-422~~ — CLOSED ✓

**Fixed in two places:**

**`frontend/src/components/chat/ChatAttachments.tsx`** — inside the `chips` map, each attachment now looks up its `FileContentEntry` by name (`fileContents.find(fc => fc.name === att.name)`). When `contentEntry?.truncated` is true, an amber "truncated" badge is rendered next to the filename chip, with a tooltip explaining that only the first portion was sent.

**`backend/app/api/run_commands.py` — `_build_attached_files_block`** — the suffix condition now reads `entry.get("truncated")` in addition to the backend-side cap check. The FE caps text to 6,000 chars before sending, so `len(text) > _ATTACHED_FILE_TEXT_CAP` alone would never fire on already-capped text — the FE flag is the reliable signal.

**Files changed:**
- `frontend/src/components/chat/ChatAttachments.tsx`
- `backend/app/api/run_commands.py`

---

## ISS-180, ISS-181, ~~ISS-263~~, ISS-381 — user_workflows.py cluster

~~ISS-263 CLOSED ✓ — superseded by ISS-381. Premise was inferred and refuted: the save never silently returned 201; it 422s on roster validation. ISS-381 is the authoritative card for this defect.~~

The three remaining open cards:

| field | value |
|---|---|
| cards | ISS-180, ISS-181, ISS-381 |
| domain | 14-backend-api |
| batch | B3 |
| fix site | `backend/app/api/user_workflows.py` |
| reason for escalation | All three escalated by fixer (round 5). The full cluster could not be resolved within the single-file boundary. Full detail on individual cards. |
| decision needed | **Human review of cards ISS-180, ISS-181, ISS-381.** Determine which require cross-file coordination (engine, compiler) before the fixes can proceed. |
| card status | ESCALATED (3 remaining) |

---

## ISS-105 — SSE uvicorn cancel + shutdown snapshot race

| field | value |
|---|---|
| card | ISS-105 |
| domain | 14-backend-api |
| batch | B4 |
| fix site | `backend/app/api/run_stream.py` |
| reason for escalation | Escalated by fixer (round 5). Concerns uvicorn cancelling SSE tasks during shutdown and a snapshot race condition — correctness-critical SSE behaviour. Fix touches the SSE transport surface which is cross-domain (also referenced by domain 11 hooks). |
| decision needed | **Architecture review:** confirm the proposed fix approach for the uvicorn cancel / shutdown race before landing, as a wrong edit here is a runtime regression in the SSE down-channel. |
| card status | ESCALATED |
