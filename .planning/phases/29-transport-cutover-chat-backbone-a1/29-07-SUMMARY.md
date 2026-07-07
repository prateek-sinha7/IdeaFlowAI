---
phase: 29-transport-cutover-chat-backbone-a1
plan: 07
subsystem: ui
tags: [sse, eventsource, fetch-stream, react-hooks, transport, resilience, last-event-id, jwt, playwright]

# Dependency graph
requires:
  - phase: 29-06
    provides: mockSse transport driver (id:{seq}, Last-Event-ID replay, drop/reattach) + shared MockWs seq/event_id space + nextEventId()
  - phase: 29-01
    provides: wire-parity harness proving the SSE projection ≡ recorded WS frames (the binding gate this FE consumer relies on)
provides:
  - "useRunStream — the SSE transport twin of useWebSocket (fetch-stream, native Last-Event-ID resume, dedup-friendly max-seen seq cursor, backoff reconnect cap 30s, connection state machine, silent JWT refresh)"
  - "RunConnectionProvider — app-level connection ownership surviving route changes, server-derived reattach (GET /api/runs non-terminal), per-run cursor persistence, visibility/online reconnect, REST up-channel sendCommand + fan-out subscribe"
  - "NEXT_PUBLIC_SSE_TRANSPORT flag (env.ts) — reversible, additive transport switch (OFF by default → WS path intact)"
  - "Flag-selected transport in useWorkflow (commands over REST when on; websocketSend byte-for-byte unchanged when off)"
  - "ts-sse-resilience.spec.ts — 4 offline driver-level resilience specs (reload resume / route-change survival / auto-reconnect / multi-tab)"
affects: [29-wave2-chat-backbone, ws-deletion-followup, phase-30-image-carrier, run-connection-provider-mount]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SSE consumption via fetch + ReadableStream reader (NOT EventSource) so the Authorization + Last-Event-ID headers can be attached — credential-safe native resume"
    - "Flag-selected transport twin: a new hook mirrors an existing one's public contract behind an env flag; the OFF path stays byte-for-byte unchanged (LOCK-B additive cutover)"
    - "App-level connection ownership via a provider whose per-run connection children live above the router (survive route changes); one useRunStream per run via a mapped child component (Rules of Hooks)"
    - "Server-derived reattach: query GET /api/runs filtered to non-terminal statuses; never trust sessionStorage alone (the cursor is only a Last-Event-ID resume hint)"

key-files:
  created:
    - frontend/src/hooks/useRunStream.ts
    - frontend/src/providers/RunConnectionProvider.tsx
    - frontend/e2e/tests/ts-sse-resilience.spec.ts
  modified:
    - frontend/src/hooks/useWorkflow.ts
    - frontend/src/lib/env.ts

key-decisions:
  - "useRunStream uses fetch+ReadableStream, not EventSource — EventSource cannot send the Authorization or Last-Event-ID headers the JWT-auth SSE endpoint needs; the fetch reader gives the same native resume semantics credential-safely"
  - "The SSE hook dispatches the SAME { type, data } envelope as the WS onmessage handler, so the existing dashboard dedup (msg.data.event_id) + max-seen-seq cursor + handlePipelineMessage reducer bind UNCHANGED"
  - "RunConnectionProvider is built + correct but NOT mounted in app/layout.tsx this plan (layout is outside the LOCK-B allow-list); mounting is the deferred integration step. useRunConnection() has an inert default so useWorkflow compiles and runs byte-identically when the provider is absent"
  - "Silent JWT refresh (D-14f) is implemented as a best-effort seam (pre-expiry timer + one reactive refresh on a mid-stream 401) against POST /api/auth/refresh; if the endpoint is absent it degrades to the WS path's clear-token+redirect — no mid-run logout when refresh is available"

patterns-established:
  - "Additive transport cutover behind a reversible env flag with the legacy path provably intact (LOCK-B)"
  - "Driver-level resilience specs: prove the transport contract offline via the 29-06 mockSse + a fetch consumer that mirrors the real hook's Last-Event-ID/dedup/cursor mechanism, independent of app-UI text locators"

requirements-completed: [CHAT-07]

# Metrics
duration: 8min
completed: 2026-07-07
---

# Phase 29 Plan 07: FE SSE Transport Adapter (behind a flag) Summary

**A flag-selected SSE transport twin (`useRunStream`) of `useWebSocket` with native Last-Event-ID resume + dedup-by-event_id, an app-level `RunConnectionProvider` doing server-derived reattach that survives route changes, and a reversible `NEXT_PUBLIC_SSE_TRANSPORT` switch in `useWorkflow` — with `useWebSocket.ts` untouched and the WS path fully intact when the flag is off (LOCK-B).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-07T23:15:00Z
- **Completed:** 2026-07-07T23:21:00Z
- **Tasks:** 3
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- `useRunStream` SSE hook: consumes `GET /api/runs/{id}/events/stream` via a fetch-stream reader, dispatches WS-parity `{ type, data }` envelopes, tracks a max-seen `seq` cursor, sends `Last-Event-ID` on every (re)connect for native resume, drops `pipeline_heartbeat`/`pong`, reconnects with exponential backoff capped at 30s, surfaces a `connecting → replaying → live → reconnecting` state machine, and does silent JWT refresh before expiry (D-14a/c/d/f, T-29-07-2).
- `RunConnectionProvider`: app-level ownership that survives route changes (D-14a), server-derived reattach querying non-terminal `GET /api/runs` (D-14b, T-29-07-1), persisted per-run replay cursor (D-14c), reconnect on `visibilitychange`/`online` (D-14e), a REST up-channel `sendCommand`, and a fan-out `subscribe`. `useRunConnection()` has an inert default so it is safe outside the provider.
- `useWorkflow`: additive flag branch — SSE-on routes `run_pipeline` / `submit_questionnaire` over REST via the provider; SSE-off is the existing `websocketSend`, byte-for-byte unchanged. Shared `handlePipelineMessage` reducer untouched.
- `env.ts`: `NEXT_PUBLIC_SSE_TRANSPORT` flag (OFF by default; production images built empty keep the WS path).
- 4 offline resilience specs green via the 29-06 `mockSse` driver.

## Task Commits

Each task was committed atomically:

1. **Task 1: useRunStream.ts + env.ts flag** — `0429faef` (feat)
2. **Task 2: RunConnectionProvider** — `1cc8e92a` (feat)
3. **Task 3: flag-selected transport in useWorkflow + resilience specs** — `d68f1dc1` (feat)

**Plan metadata:** _(final docs commit — this SUMMARY + STATE + ROADMAP)_

## Files Created/Modified
- `frontend/src/hooks/useRunStream.ts` (created) — the SSE transport twin of `useWebSocket` (subscribe, replay cursor, dedup-friendly envelope, backoff reconnect, JWT refresh).
- `frontend/src/providers/RunConnectionProvider.tsx` (created) — app-level connection ownership + server-derived reattach + state machine + visibility/online reconnect + REST up-channel.
- `frontend/e2e/tests/ts-sse-resilience.spec.ts` (created) — reload-resume / route-change / auto-reconnect / multi-tab resilience specs.
- `frontend/src/hooks/useWorkflow.ts` (modified) — flag-selected transport branch (additive; flag-off path unchanged).
- `frontend/src/lib/env.ts` (modified) — `NEXT_PUBLIC_SSE_TRANSPORT` flag.

## Verification Evidence

**PRIMARY offline gate — TypeScript:**
```
cd frontend && npx tsc --noEmit -p tsconfig.json  →  EXIT 0 (clean, run after each task)
```

**Task 3 targeted resilience specs (the green bar for this plan):**
```
cd frontend && npm run e2e -- --project=mocked -g "sse-resilience"
  → 4 passed (2.6s)
    TS-SSE-RESILIENCE-01 page reload resumes via native Last-Event-ID
    TS-SSE-RESILIENCE-02 route-change keeps the resume cursor (app-level ownership)
    TS-SSE-RESILIENCE-03 auto-reconnect after a drop replays only past-cursor frames
    TS-SSE-RESILIENCE-04 multi-tab consumers ride ONE monotonic seq/event_id space
```

**Regression — 29-06 SSE smoke + resilience together (`-g "TS-SSE"`):** 6 passed (2 smoke + 4 resilience) — the 29-06 `ts-sse.spec.ts` smoke is intact.

**Regression — useWorkflow vitest** (new `useRunConnection()` context call): `npx vitest run src/hooks/useWorkflow` → 14 passed (4 files). Flag-off path unaffected.

**LOCK-B git diff confirmation** — the 29-07 change set is exactly the allow-list, and `useWebSocket.ts` is NOT in the diff:
```
$ git diff (my 3 commits + spec) --name-only | sort -u
frontend/e2e/tests/ts-sse-resilience.spec.ts
frontend/src/hooks/useRunStream.ts
frontend/src/hooks/useWorkflow.ts
frontend/src/lib/env.ts
frontend/src/providers/RunConnectionProvider.tsx

$ ... | grep useWebSocket  →  NONE — useWebSocket.ts untouched (LOCK-B OK)
```
No backend files, `websocket_handoff.py`, ratchets, ledger rows, or WS deletions touched. `handlePipelineMessage` reducer behavior unchanged.

## Decisions Made
- **fetch-stream over EventSource** — `EventSource` cannot attach the `Authorization: Bearer` or `Last-Event-ID` headers the JWT-auth SSE endpoint requires; a `fetch` + `ReadableStream` reader gives identical native-resume semantics credential-safely. This is exactly what the 29-06 `mockSse` (header-based `Last-Event-ID`) and the resilience specs' fetch consumer model.
- **Envelope parity** — the hook dispatches `{ type, data }` (the SSE `data:` JSON IS the `data` object carrying `event_id`+`seq`), so the dashboard's existing top-of-handler dedup (`msg.data.event_id`) + max-seen-seq cursor + `handlePipelineMessage` bind unchanged. No reducer edits.
- **Provider not mounted in layout this plan** — see Deviations.

## Deviations from Plan

None affecting correctness. One deliberate scope boundary is documented below (not an auto-fix — a LOCK-B allow-list constraint).

### Scope boundary (LOCK-B allow-list)

**RunConnectionProvider is built and correct but NOT mounted in `app/layout.tsx` in this plan.** Mounting the provider at the app root is the integration step that makes the live app consume the SSE transport when the flag is on. `app/layout.tsx` is **outside the 5-file LOCK-B allow-list**, so wiring it is deferred to the supervised follow-up (consistent with the CONTEXT "designed now, wired later" posture and LOCK-B additive-only mandate). To keep everything compiling and byte-identical when unmounted, `useRunConnection()` returns an inert default (`enabled:false`), so:
- `useWorkflow`'s flag branch only activates when the flag is on AND the provider is mounted; otherwise it uses `websocketSend` exactly as before.
- The resilience specs prove the transport contract at driver level (the honest offline-provable bar), not by mounting the app-wide provider.

## Issues Encountered
None. All three tasks passed their `tsc` gate first time; the resilience specs passed first run.

## DEFERRED-to-live checks

- **Full `--project=mocked` "123 specs green" bar — DEFERRED (DEF-29-06-1).** The full mocked suite is currently RED for pre-existing feat/ui-2 UI-convergence rework (redesigned dashboard home; legacy CreationHub button labels removed — commits 9c7b78bb / fe7a351b, KAN-78) that PREDATE phase 29 and touch none of this plan's files. Fixing those unrelated app specs is out of scope and would violate the allow-list. This plan's correctness is proven by `tsc` clean + the 6 SSE specs green (`-g "TS-SSE"`) + useWorkflow vitest 14/14. Not fabricated, not hung.
- **Live app-mounted provider verification (real backend + SSO + SSE endpoints).** The end-to-end cutover (flag on, provider mounted, real `GET /api/runs/{id}/events/stream` + REST commands) needs a running server and interactive SSO; deferred to the consolidated live pass per the 29-CONTEXT execution-viability note and the defer-live-verification convention.

## Threat Model Coverage
- **T-29-07-1 (Spoofing — stale sessionStorage run ids):** mitigated — `RunConnectionProvider` reattaches server-derived (`GET /api/runs` non-terminal); sessionStorage holds only the resume cursor, never the authoritative live-run set.
- **T-29-07-2 (DoS — mid-run 4001 logout):** mitigated — `useRunStream` schedules a pre-expiry silent refresh and attempts one reactive refresh on a mid-stream 401 before any clear-token+redirect.
- **T-29-07-SC (package installs):** accepted — zero installs; browser-native `fetch`/`ReadableStream` only.

## Next Phase Readiness
- Wave 2 (chat backbone: `POST /api/runs/{id}/messages`, router, steering seam, narrator cards) can consume `RunConnectionProvider.sendCommand` + `subscribe` and `useRunStream`'s `{ type, data }` frames.
- **Follow-up to wire the cutover live:** mount `<RunConnectionProvider>` in `app/layout.tsx` and subscribe `useWorkflow`/dashboard to `runConnection.subscribe` for the down-channel (out of this plan's allow-list). The WS deletion + INV-12 exit gate remain the separate supervised follow-up (LOCK-B).

## Self-Check: PASSED

All 5 allow-listed files exist on disk; all 3 task commits (`0429faef`, `1cc8e92a`, `d68f1dc1`) exist in git. `useWebSocket.ts` confirmed NOT in the 29-07 diff (LOCK-B).

---
*Phase: 29-transport-cutover-chat-backbone-a1*
*Completed: 2026-07-07*
