---
id: TEST-1-5
type: test
status: done
area: [sse, agents, auth]
summary: >-
  1.5 Selector strategy — the app ships almost no data-testid
source: .planning/TEST-REGISTER.md#1-5-selector-strategy-the-app-ships-almost-no-da
---

### 1.5 Selector strategy — **the app ships almost no `data-testid`**

Every `data-testid` in the repo is inside Vitest mocks / `src/data/skills.ts`, **not** in production components. Playwright must anchor on **exact visible text**, **`getByRole`**, **`iframe[title=…]`**, **`button[title=…]`**, and the few `aria-label`s (`Close preview`, `Manage skill`). The §3 cases give the exact handle per element. **Recommended (see §7-G3):** before/while authoring, add `data-testid` to the load-bearing nodes flagged in §7 (Stop button, agent-card status badges, the failure-affordance root, the generic iframe, history rows + status badges, reconnect banners). Text selectors work today but are brittle to copy changes.
