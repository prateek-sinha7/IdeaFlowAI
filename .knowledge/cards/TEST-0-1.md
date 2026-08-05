---
id: TEST-0-1
type: test
status: done
area: [frontend, agents, auth]
files:
  - frontend/e2e/README.md
summary: >-
  0.1 Status legend
source: .planning/TEST-REGISTER.md#0-1-status-legend
---

### 0.1 Status legend

| Badge | Meaning |
|---|---|
| ✅ **LIVE** | Confirmed on real Bedrock **and** visually (Playwright/screenshot) in a live campaign (2026-06-12 / 2026-06-13). Behavior proven to work once; still needs a **committed, repeatable** Playwright test (none exists yet — §1.5/§7). |
| 🟡 **LIVE-MECH** | Live mechanism fired on the wire; the specific value/edge is offline-backed. |
| 🟢 **OFFLINE** | Green in pytest / contract / characterization snapshot. Backend-trustworthy; UI binding still to automate. |
| 🟠 **OFFLINE-ONLY** | Proven offline (fault-injection / prompt-pin); live re-confirm explicitly deferred. |
| 🔴 **TO-BUILD** | No test exists yet. The case below is the spec to automate — **author it in Playwright**. |
| ⚪ **KNOWN-FAIL** | Pre-existing baseline failure (logged ISS-022/025/026). Not a regression; do **not** block on it. |

> **Status update (2026-06-14):** the committed Playwright suite now **EXISTS** at `frontend/e2e/` (§7-G1 DONE) — **123 mocked tests pass, 0 fail**, 15 intentional `fixme`s, + 7 live tests (4 real drivers) that collect. It covers all 25 suites below (TS-A…TS-Y) via a browser-level mock-WS + mock-API harness (no backend needed for the mocked layer), plus a real-Bedrock `*.live.spec.ts` layer. Run with `cd frontend && npm run e2e`. See `frontend/e2e/README.md`. The 🔴 **TO-BUILD** badges in §3 are now **automated** (the few un-mockable rows are `fixme` with documented reasons — drag-reorder, revision lineage/terminal-fidelity, wizard-path live drivers; see the README). The remaining work to "continuously gated" is wiring `npm run e2e` into CI (§7-G4) and adding `data-testid`s (§7-G3).

---

## 1. Test environment, prerequisites & setup
