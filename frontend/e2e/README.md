# Flowin E2E (Playwright) — the committed UI test suite

This is the executable realization of `.planning/TEST-REGISTER.md` §3. **Playwright is the eyes** — every user-observable behavior (workflow selection, composing agents, model selection, live agent panels, waves, gates, deliverables, terminal states, cancel, reconnect, revisions, history) is exercised and asserted here. Humans don't hand-test.

**Status:** 123 mocked tests pass (0 fail), 15 intentional `fixme`s (backend-gated / un-mockable states), + 7 live tests that collect (4 real drivers, 3 documented fixmes). Runs in ~1.3 min.

## Run it

```bash
cd frontend

npm run e2e                  # all mocked specs (no backend needed) — the default
npm run e2e:headed           # watch it in a browser
npm run e2e:ui               # Playwright UI mode
npm run e2e -- e2e/tests/ts-q.terminal-states.spec.ts   # one file
npm run e2e:report           # open the last HTML report

npm run e2e:live             # *.live.spec.ts — needs a REAL backend (see below)
```

A Next dev server on `:3000` is auto-started (reused if already running).

## Two modes

### Mocked (default, fast, deterministic, CI-ready)
No backend, no Bedrock. The app streams runs over SSE (the sole transport, 44-06); the fixtures intercept REST **and** the per-run SSE stream **in the browser**:
- `fixtures/mockApi.ts` — routes `**/api/**` (auth/me, login, runs, capabilities, …). Mutable per-test (`mockApi.setRuns/setUser`). Auto-installed for every test.
- `fixtures/mockSse.ts` — routes `**/api/runs**`: it serves the SSE down-channel (`GET /api/runs/{id}/events/stream`, a `text/event-stream` body built from a durable frame tail) and mocks the REST up-channel commands (`POST /api/runs` + `/{id}/{answers,cancel,gate,revisions,messages}`). A spec drives the inbound stream (`mockSse.start/agentStart/agentComplete/complete/failed/cancelled/waveStarted/reviewGateReady/…`) and asserts the outbound REST commands the app sends (`mockSse.waitForCommand("run_pipeline")`). Frames follow the exact wire contract (`data`-wrapped, `event_id`/`seq` in `data`; `stream` top-level chunk/section).

### Live (`*.live.spec.ts`, nightly / on-demand)
Real backend + real Bedrock. Prerequisites:
```bash
# 1. seed users (registration is admin-only — see backend/scripts/seed_test_users.py)
cd backend && python3.11 scripts/seed_test_users.py
# 2. backend on :8000 with Bedrock.
#    --timeout-graceful-shutdown is required: a live-spec run holds an SSE stream
#    open, and without it uvicorn ignores SIGTERM forever (only kill -9 ends the
#    process). No --reload — it masks crashes and doubles the stuck-process count.
RUNS_ROOT=/tmp/flowin-runs AWS_PROFILE=default AWS_REGION=eu-central-1 \
  python3.11 -m uvicorn app.main:app --port 8000 --timeout-graceful-shutdown 5
# 3. run the live project
cd ../frontend && npm run e2e:live
```
`fixtures/live.ts` logs in via the real `POST /api/auth/login` (creds default to the seed script's `qa-<tier>@flowinqa.com` / `flowin-e2e-pass`, overridable via `E2E_*` env).

**Live timing notes (real-Bedrock, measured 2026-06-14):** `user_stories` ≈ 5 min (3 clarify rounds + 6 agents); `custom`/SC-001 ≈ 2 min; model-override ≈ 6 min. **`app_builder` is the long pole — ~40–45 min** for all 15 agents (a single run reached 14/15 DONE in 39 min, several agents emitting 300–480K tokens). So **TS-V-04 verifies only that app_builder *runs* live** (≥3 agents complete with real output, no errors) within a 16-min budget; the full 15-agent IDE deliverable is a **nightly-only** assertion, and the IDE *render* itself is proven deterministically in mocked TS-O-03. The clarify engine asks up to **3 rounds** before `clarification_limit_reached` → agents start; `dismissClarifyRounds` loops to handle this (see ISS-027 for the "Skip all & run directly" UX caveat).

## Layout

```
e2e/
  FIXTURE-CONTRACT.md      # the authoritative fixture API + gotchas (read before adding a spec)
  fixtures/
    constants.ts           # origins, token key, MODEL_CATALOG, CAPABILITIES
    mockApi.ts             # REST stub (+ makeRun helper)
    mockSse.ts              # SSE + REST stub: drive inbound SSE events / assert outbound REST commands
    scenarios.ts           # canned agent line-ups (AGENTS) + run players + SAMPLE_* fixtures
    dashboard.ts           # DashboardPage page object (navigation + locators)
    test.ts                # the mocked `test`/`expect` (mocks auto-installed)
    live.ts                # the `liveTest` harness (real login)
  tests/
    ts-a.auth … ts-y.resilience          # 19 mocked spec files (TS-A..TS-Y)
    ts-v.per-workflow.live.spec.ts       # live per-workflow E2E
    ts-w.model-override.live.spec.ts     # live model-override
```

## Adding a spec

Read `FIXTURE-CONTRACT.md` (the gotchas section matters — e.g. `custom` seeds no agents; agent cards come from `pipeline_start`; almost no `data-testid`). Mimic `tests/ts-i.agent-panels.spec.ts` (live panels), `tests/ts-q.terminal-states.spec.ts` (terminal/degraded), or `tests/ts-p.iframe-security.spec.ts` (iframe sandbox). Import `{ test, expect }` from `../fixtures/test`. Self-verify: `npm run e2e -- e2e/tests/<your-file>.spec.ts`.

## What's intentionally `fixme` (not failures)

These have no FE-observable surface in mocked mode and are covered by backend tests / live specs — each is a standalone `test.fixme(true, "<reason>")` with a documented reason:
- HTML5 **drag-reorder** of agents (TS-D-04) — native drag is unreliable to simulate.
- AgentModelPicker **alt-state copies** (loading / no-jwt / no-agents) — un-triggerable without fixture surgery; covered by the component unit tests.
- Revision **lineage / terminal-fidelity / surgical-diff / reconnect-section** (TS-U-03..06,08) — persistence/engine concerns; Phase 14 BE tests.
- **Cross-owner reconnect demotion** (TS-S-07) — backend-gated (BE-RES-01).
- Prototype **tweaks 400ms debounce** (TS-X-04) — deep prototype build interaction.
- **Wizard-path** per-workflow live drivers (TS-V-02/03) — need the live template/design-system gallery.

## Recommended next hardening (TEST-REGISTER §7)
- Add `data-testid` to the load-bearing nodes (Stop button, agent-card status badges, failure-affordance root, generic iframe, history rows, reconnect banners) to de-brittle the text/role selectors.
- Wire `e2e` (mocked) into CI as an MR gate; run `e2e:live` nightly.
