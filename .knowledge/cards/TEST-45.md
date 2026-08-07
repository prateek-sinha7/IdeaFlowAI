---
id: TEST-45
type: test
status: done
area: [frontend, sse, workflow, agents, auth, artifacts]
files:
  - frontend/e2e/README.md
  - frontend/e2e/FIXTURE-CONTRACT.md
summary: >-
  G1 — Build the committed Playwright E2E suite (the headline work) — ✅ DONE
  (2026-06-14)
source: .planning/TEST-REGISTER.md#g1-build-the-committed-playwright-e2e-suite-the
covers: [TS-Q-02]
---

### G1 — Build the committed Playwright E2E suite (the headline work) — ✅ DONE (2026-06-14)

**Built and green** at `frontend/e2e/` — 21 spec files (19 mocked TS-A…TS-Y + 2 live), 123 mocked tests passing / 0 failing / 15 documented `fixme`, ~1.3 min. Architecture exactly as specified below: a browser-level **mock-WS** (`page.routeWebSocket`) + **mock-API** (`page.route('**/api/**')`) harness for the deterministic mocked layer (no backend), and a `*.live.spec.ts` layer (`fixtures/live.ts`) for real Bedrock. `@playwright/test@^1.56` added; `seed_test_users.py` written (G2). See `frontend/e2e/README.md` + `frontend/e2e/FIXTURE-CONTRACT.md`. The original target layout that was built:

```
frontend/e2e/
  playwright.config.ts            # baseURL http://localhost:3000, projects: chromium (+firefox for voice-absent), webServer optional
  fixtures/
    auth.ts                       # programmatic login → seed localStorage["auth_token"]; per-tier storageState (basic/pro/enterprise)
    ws.ts                         # helpers to assert outbound run_pipeline frames + capture inbound events
  tests/
    ts-a.auth.spec.ts  ts-b.selection.spec.ts  ts-c.input-trigger.spec.ts
    ts-d.composer.spec.ts  ts-e.model-picker.spec.ts  ts-f.skills-hooks.spec.ts
    ts-i.agent-panels.spec.ts  ts-k.wave-tree.spec.ts  ts-m.questionnaire.spec.ts
    ts-n.review-gate.spec.ts  ts-o.deliverables.spec.ts  ts-p.iframe-security.spec.ts
    ts-q.terminal-states.spec.ts  ts-r.cancel.spec.ts  ts-s.reconnect.spec.ts
    ts-t.history.spec.ts  ts-u.revisions.spec.ts  ts-v.e2e-per-workflow.spec.ts
```

- **Two run modes:** *mocked-WS* (deterministic, fast, no Bedrock — drive each `pipeline_*`/`agent_*`/`wave_*`/gate frame from fixtures to assert UI mapping for TS-I/J/K/Q/R/S) **and** *live-Bedrock* (`AWS_PROFILE=default`, the §4 per-workflow runs — slower, real). The campaign's throwaway scenario-JSON driver is the template; commit its successor.
- **Reuse the srini fault-injector** for TS-Q-02 (run a backend instance with `AWS_PROFILE=hexaware-srini` to force the `ValidationException`).
- Mirror the existing security assertions (`PreviewPanel.degraded.test.tsx`, `genericDeliverable.test.tsx`, `MarkdownPreview.security.test.tsx`) **in-browser** for TS-P.
