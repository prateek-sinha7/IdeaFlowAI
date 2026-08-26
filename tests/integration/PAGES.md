# Page index — every distinct URL in the product, captured

The definitive capture target, and the per-page record of what was found. Built
from source *before* any capture:

- `find frontend/src/app -name page.tsx` — the Next.js file routes
- `ParsedView` in `frontend/src/lib/routes.ts` — the 36 catch-all screens
- `GET /api/runs` — the run statuses that change a page's shape

Every page was loaded in real Google Chrome with a **2.5s settle after
navigation** before the fingerprint and the screenshot were taken, so nothing
below is a mid-load state or a redirect caught in flight.

| Column | Meaning |
|---|---|
| **Shot** | `screenshots/<area>/pNN-<slug>.png` — full-page PNG |
| **Fingerprint** | `capture/pNN-<slug>.json` — headings, controls, inputs, settled URL, notes |
| **Spec** | the feature file whose scenarios cover this page |

Overlays, tab families and cross-cutting states are **not pages**; they are in
`MANIFEST.md` sections C and E–G, with their screenshots under
`screenshots/12-overlays/` and `screenshots/13-states/`.

**55 page URLs. 55 captured.** One extra shot (`p56`) records the version
fallback described in D-12.

---

## 01 · auth — `screenshots/01-auth/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p01 | `/login` | sign-in form; email/password inputs carry **no `name` attribute** | `01-auth` |
| p02 | `/login?expired=true` | the same form plus the session-expired banner | `01-auth` |
| p03 | `/login?expired=1` | **no banner** — only the literal `true` triggers it (D-03) | `01-auth`, `13-errors` |
| p04 | `/register` | redirect stub → `/login`; not a real screen | `01-auth` |
| p05 | `/` | branches on token presence → `/dashboard` (authed) or `/login`. **Not unconditional — C-3** | `01-auth` |

## 02 · home — `screenshots/02-home/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p06 | `/dashboard` | the catalog — "What would you like to build today?" | `02-home-catalog` |
| p07 | `/create` | the same screen; two URLs, one view | `02-home-catalog` |

## 03 · create — `screenshots/03-create/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p08 | `/create/ppt` | wizard shell — tab strip + template gallery | `03-launch-panels` |
| p09 | `/create/prototype` | wizard shell — Template / Design System / Discovery | `03-launch-panels` |
| p10 | `/create/app` | **renders the user-stories panel — D-01** | `03-launch-panels` |
| p11 | `/create/user-stories` | simple panel — brief, Advanced, review gates, Run | `03-launch-panels` |
| p12 | `/create/ex_A2_branch` | catalog-driven launch panel for a fixture workflow | `03-launch-panels` |
| p13 | `/workflow/create?mode=ppt` | **redirects to `/create/ppt` — C-1** | `16-pages-outside-routes` |
| p14 | `/workflow/create?mode=prototype` | **redirects to `/create/prototype` — C-1** | `16-pages-outside-routes` |

## 04 · workflows — `screenshots/04-workflows/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p15 | `/workflows` | saved list | `05-saved-workflows` |
| p16 | `/workflows/new` | empty composer | `04-composer-canvas` |
| p17 | `/workflows/{id}` | read-only detail | `05-saved-workflows` |
| p18 | `/workflows/{id}/edit` | composer; Save overwrites in place | `04-composer-canvas` |
| p19 | `/workflows/ppt/canvas` | built-in on canvas; Save creates a copy | `04-composer-canvas` |
| p20 | `/workflows/{id}/run` | the saved workflow's launch panel | `03-launch-panels` |
| p21 | `/workflow` | **a second, older builder — not in `routes.ts`, linked from nowhere** | `16-pages-outside-routes` |

## 05 · runs — `screenshots/05-runs/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p22 | `/runs` | history — filters, sort, auto-refresh | `06-run-history` |
| p23 | `/runs/{completed}` | Preview tab | `07-run-detail` |
| p24 | `/runs/{completed}/steps` | Steps | `07-run-detail` |
| p25 | `/runs/{completed}/steps/{agentId}` | one agent's step detail | `07-run-detail` |
| p26 | `/runs/{completed}/files` | Files | `07-run-detail` |
| p27 | `/runs/{completed}/workspace` | **renders, but no builder and no parser case — D-02** | `07-run-detail` |
| p28 | `/runs/{completed}/audit` | Audit | `07-run-detail` |
| p29 | `/runs/{completed}/preview/full` | full-bleed deliverable | `07-run-detail` |
| p30 | `/runs/{completed}/stream` | stream view on a finished run | `07-run-detail` |
| p31 | `/runs/{failed}` | **4 tabs, no Preview** — the strip is not positionally stable | `14-run-states` |
| p32 | `/runs/{cancelled}` | Run Again; tells you to open the nonexistent "Thinking" tab (D-08) | `14-run-states` |
| p33 | `/runs/{diverted}` | Start a new run | `14-run-states` |
| p34 | `/runs/{id}/versions/{v}` | run detail with the artifact pinned to a version | `07-run-detail`, `13-errors` |

## 06 · library — `screenshots/06-library/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p35 | `/library` | Agents tab (default) | `08-library` |
| p36 | `/library?tab=skills` | Skills | `08-library` |
| p37 | `/library?tab=hooks` | Hooks | `08-library` |
| p38 | `/library/agents/{slug}` | agent drawer — Overview / Skills / Hooks / Config | `08-library` |
| p39 | `/library/skills/{slug}` | skill drawer | `08-library` |
| p40 | `/library/hooks/{slug}` | hook drawer | `08-library` |

## 07 · settings — `screenshots/07-settings/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p41 | `/settings/profile` | identity + plan; email read-only | `09-settings` |
| p42 | `/settings/ai-model` | testid `tab-model` ≠ route segment | `09-settings` |
| p43 | `/settings/usage` | testid `tab-limits` ≠ route segment; Deliverable Access | `09-settings` |
| p44 | `/settings/constitution` | | `09-settings` |
| p45 | `/settings/security` | | `09-settings` |
| p46 | `/settings` | **redirects to `/settings/profile` — C-2**, despite parsing to `unknown` | `09-settings`, `13-errors` |

## 08 · analytics — `screenshots/08-analytics/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p47 | `/analytics` | 4 KPI tiles, 6 range buttons, 6-way pipeline filter, By Pipeline Type (**D-11**) | `10-analytics` |

## 09 · admin — `screenshots/09-admin/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p48 | `/admin` | own shell — no app nav, only "← Back to app" and "Logout"; 4-user table | `11-admin` |

## 10 · handoff — `screenshots/10-handoff/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p49 | `/handoff/settings` | **GitHub PAT + API keys — the most security-sensitive surface, not in `routes.ts`** | `16-pages-outside-routes` |
| p50 | `/handoff/{invalid}` | "Handoff not found" + Back to dashboard; its own error surface, HTTP 200 | `16-pages-outside-routes` |

## 11 · errors — `screenshots/11-errors/`

| # | URL | What it is | Spec |
|---|---|---|---|
| p51 | `/this-route-does-not-exist` | the 404 screen; offers Sign in even when signed in | `13-errors` |
| p52 | `/runs/{nonexistent-uuid}` | **byte-identical to p51** — the missing run is never named | `13-errors` |
| p53 | `/workflows/{nonexistent-uuid}` | **byte-identical to p51** | `13-errors` |
| p54 | `/preview-fullscreen?error=quota` | quota message; **no heading element, no way back** | `16-pages-outside-routes` |
| p55 | `/preview-fullscreen` | no payload → redirects to `/runs` | `16-pages-outside-routes` |
| p56 | `/runs/{id}/versions/99` | **silently serves v1 — D-12** (not a 56th page; a state of p34) | `13-errors` |

---

## What the re-capture changed

Five claims from the earlier sweeps were wrong, all for the same reason — they
were written from reading source rather than from loading the URL. They are
listed as C-1 … C-5 at the end of `DEFECTS-OBSERVED.md`, and the specs that
carried them have been corrected.

One new defect was found by re-capturing what an earlier sweep had skipped:
**D-12**, the silent version fallback.

## Sweep 4 — the post-commit audit

Everything above was committed, then audited against what `MANIFEST.md` still
listed as open. That pass captured six more overlays and every remaining tab
family, and found four more defects:

| # | What |
|---|---|
| **D-13** | Choosing the HTML renderer on a markdown deliverable renders a blank pane with no explanation |
| **D-14** | Run cards are `div[role="button"]`, not links — no new-tab, no copyable URL — and `/runs` has zero `data-testid` attributes |
| **D-15** | `/runs?type=presentation` shows "No runs match this filter" while the chip beside it reads 7; the chip's own value is `ppt` |
| **D-16** | A **fourth tier**, `hexaware`, exists in code and in the admin dialog. It is not a rung on the ladder — it gains prototype over basic but **loses ppt** |

D-16 is the one that matters: every tier scenario in `17-theme-and-tiers` was
written assuming basic → pro → enterprise is totally ordered. It is not.

## Sweep 5 — the last popups, and the chat lane

Traced each remaining overlay to its mount point in source instead of hunting for
it in the UI. Two were never missing, one was mislocated, one is unopenable:

| Overlay | Outcome |
|---|---|
| `WorkflowDialog` | **is** the catalog inspect dialog — double-counted since sweep 2 |
| `AgentSkillsPicker` | not an overlay — renders inline in the composer config rail |
| `WorkflowPickerModal` | captured (`87`) — it lives in the config rail, not on the canvas node |
| `SkillManager` | **unopenable by any user — D-17** |
| `PrototypePreview` controls | **never mount — D-18** |

Also captured the **concierge chat lane** (`screenshots/14-chat-lane/`), the left
column of every run page, which no earlier sweep had listed at all. Specified in
`screens/18-chat-lane.feature.md`.

Five more defects:

| # | What |
|---|---|
| **D-17** | `/workflow`'s Add Agent picker is empty for all 6 categories, so the legacy builder can never run anything — and `SkillManager`, whose only mount root is its node, is unreachable |
| **D-18** | A prototype run previews the spec agent's markdown while its Files tab reports `prototype.html · validated` |
| **D-19** | Failed runs keep an enabled chat composer; cancelled and diverted runs have none |
| **D-21** | The prototype run's clarification exchange appears twice, with different message ids |

*(D-20 is deliberately unused — `UXFIX-03`/`D-20` are upstream design-doc ids.)*

## Still not captured, and why

| Gap | Blocker |
|---|---|
| `waiting_for_user` run state | needs a live LLM run — real cost, and it creates a gate only a human should answer |
| a hexaware account (D-16) | the tier exists in code and in the admin dialog, but no fixture is seeded |
| empty-account states, cross-account 403 | qa-pro/basic/enterprise all have 0 runs so both are reachable — they need the seeded password, which this session could not read |
| a *switch* between artifact versions | no run in the dev DB has more than one version |
| 2 of 19 overlays | **not coverage gaps** — `SkillManager` cannot be opened (D-17) and the prototype preview never mounts (D-18) |
| chat `user` / `assistant` roles | sending a message is a live LLM turn, and can create a gate a human must answer |
| Slides renderer mode | needs a deck deliverable |
| loading / skeleton frames | needs request throttling to observe |
| responsive breakpoints | not attempted |
