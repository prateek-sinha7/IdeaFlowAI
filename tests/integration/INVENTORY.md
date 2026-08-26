# Screen inventory

Every navigable surface in the product, captured 2026-08-26 against the main
checkout on `feat/conditional-gates`.

The authority for what routes exist is `frontend/src/lib/routes.ts` — it holds
both the builders (`routes.*`) and the parser (`parseViewPath`), and ADR-0018
states every URL in the app is built and parsed there. All 34 screens render
behind one catch-all segment, `frontend/src/app/[...view]/page.tsx`.

`ParsedView` declares **37 discriminators** (36 screens + `unknown`). The table
below covers all of them, plus overlays and one route that renders but is absent
from `routes.ts` entirely.

## Route table

| # | Route | `ParsedView.screen` | `MainView` | Spec | Shot |
|---|---|---|---|---|---|
| 1 | `/login` | `login` | — | [01-auth](screens/01-auth.feature.md) | `01` |
| 2 | `/login?expired=true` | `login` | — | [01-auth](screens/01-auth.feature.md) | `02` |
| 3 | `/register` | `register` | — | [01-auth](screens/01-auth.feature.md) | — |
| 4 | `/dashboard` | `home` | `home` | [02-home-catalog](screens/02-home-catalog.feature.md) | `03` |
| 5 | `/create` | `create` | `home` | [02-home-catalog](screens/02-home-catalog.feature.md) | `04` |
| 6 | `/create/ppt` | `create-ppt` | *(legacy wizard)* | [03-launch-panels](screens/03-launch-panels.feature.md) | `05` |
| 7 | `/create/prototype` | `create-prototype` | *(legacy wizard)* | [03-launch-panels](screens/03-launch-panels.feature.md) | `06` |
| 8 | `/create/app` | `create-app` | `input` | [03-launch-panels](screens/03-launch-panels.feature.md) | `07` |
| 9 | `/create/user-stories` | `create-user-stories` | `input` | [03-launch-panels](screens/03-launch-panels.feature.md) | `08` |
| 10 | `/create/{type}` | `create-workflow` | `input` | [03-launch-panels](screens/03-launch-panels.feature.md) | `09` |
| 11 | `/workflows` | `workflows` | `saved-workflows` | [05-saved-workflows](screens/05-saved-workflows.feature.md) | `10` |
| 12 | `/workflows/new` | `workflow-new` | `composer` | [04-composer-canvas](screens/04-composer-canvas.feature.md) | `11` |
| 13 | `/workflows/{id}` | `workflow` | `saved-workflows` | [05-saved-workflows](screens/05-saved-workflows.feature.md) | `12` |
| 14 | `/workflows/{id}/edit` | `workflow-edit` | `composer` | [04-composer-canvas](screens/04-composer-canvas.feature.md) | `13` |
| 15 | `/workflows/{type}/canvas` | `workflow-canvas` | `composer` | [04-composer-canvas](screens/04-composer-canvas.feature.md) | `14` |
| 16 | `/workflows/{id}/run` | `workflow-run` | *(launch panel)* | [05-saved-workflows](screens/05-saved-workflows.feature.md) | `15` |
| 17 | `/runs` | `run-history` | `history` | [06-run-history](screens/06-run-history.feature.md) | `16` |
| 18 | `/runs/{id}` | `run-detail` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `17` |
| 19 | `/runs/{id}/steps` | `run-steps` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `18` |
| 20 | `/runs/{id}/steps/{agentId}` | `run-steps-agent` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `19` |
| 21 | `/runs/{id}/files` | `run-files` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `20` |
| 22 | `/runs/{id}/audit` | `run-audit` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `21` |
| 23 | `/runs/{id}/preview/full` | `run-preview-full` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `22` |
| 24 | `/runs/{id}/stream` | `run-stream` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `23` |
| 25 | `/runs/{id}/versions/{v}` | `run-version` | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | — |
| 26 | **`/runs/{id}/workspace`** | **`unknown`** ⚠ | `execution` | [07-run-detail](screens/07-run-detail.feature.md) | `40` |
| 27 | `/library` | `library` | `library` | [08-library](screens/08-library.feature.md) | `24` |
| 28 | `/library?tab=skills` | `library` | `library` | [08-library](screens/08-library.feature.md) | `25` |
| 29 | `/library?tab=hooks` | `library` | `library` | [08-library](screens/08-library.feature.md) | `26` |
| 30 | `/library/agents/{slug}` | `library-agent` | `library` | [08-library](screens/08-library.feature.md) | `27` |
| 31 | `/library/skills/{slug}` | `library-skill` | `library` | [08-library](screens/08-library.feature.md) | `28` |
| 32 | `/library/hooks/{slug}` | `library-hook` | `library` | [08-library](screens/08-library.feature.md) | `29` |
| 33 | `/settings/profile` | `settings-profile` | `settings` | [09-settings](screens/09-settings.feature.md) | `30` |
| 34 | `/settings/ai-model` | `settings-ai-model` | `settings` | [09-settings](screens/09-settings.feature.md) | `31` |
| 35 | `/settings/usage` | `settings-usage` | `settings` | [09-settings](screens/09-settings.feature.md) | `32` |
| 36 | `/settings/constitution` | `settings-constitution` | `settings` | [09-settings](screens/09-settings.feature.md) | `33` |
| 37 | `/settings/security` | `settings-security` | `settings` | [09-settings](screens/09-settings.feature.md) | `34` |
| 38 | `/analytics` | `analytics` | `analytics` | [10-analytics](screens/10-analytics.feature.md) | `35` |
| 39 | `/admin` | `admin` *(dead code)* | — | [11-admin](screens/11-admin.feature.md) | `36` |
| 40 | `/{anything-else}` | `unknown` | — | [13-errors](screens/13-errors.feature.md) | `39` |

### Overlays (no URL of their own)

| Overlay | Opened by | Spec | Shot |
|---|---|---|---|
| Account menu | `button[aria-label='Account menu']` | [12-shell-nav](screens/12-shell-nav.feature.md) | `37` |
| Notifications panel | `button[aria-label='Notifications']` | [12-shell-nav](screens/12-shell-nav.feature.md) | `38` |
| Advanced agents modal | `Advanced <N> agents` on a launch panel | [03-launch-panels](screens/03-launch-panels.feature.md) | — |
| Add-agent library modal | `button[aria-label='Add agent']` on canvas | [04-composer-canvas](screens/04-composer-canvas.feature.md) | — |
| Workflow actions menu | `button[aria-label='Workflow actions']` per card | [05-saved-workflows](screens/05-saved-workflows.feature.md) | — |

## Notes on the table

**Route 26 is the important row.** `/runs/{id}/workspace` renders correctly on a
cold load and selects the Workspace tab — but `parseViewPath` has no `workspace`
case, so it falls through to `{ screen: 'unknown' }`, and `routes.ts` has no
builder for it. It works because `DashboardLayout` drives the tab independently
of the parser. That is a live contradiction of ADR-0018 and is tracked in
`DEFECTS-OBSERVED.md` as **D-02**.

**Route 39 (`/admin`) is served by a static page, not the catch-all.**
`frontend/src/app/admin/page.tsx` takes precedence over `[...view]`, so the
`admin` cases in both `routes.ts` and `parseViewPath` are unreachable — the file
says so itself. The screen is real; the parser entry is documentation.

**Routes 6 and 7 do not use `MainView`.** `/create/ppt` and `/create/prototype`
render the legacy wizard (`app/workflow/create/page.tsx`), a different shell from
the `input` launch panel that routes 8–10 use. Their screens look and behave
differently, and the specs treat them as two distinct surfaces.

**Route 25 (`/runs/{id}/versions/{v}`) was not captured.** No run in the dev
database has more than one version, so there was nothing to navigate to. Its spec
is written from the route contract and marked `@unverified`.

**Route 26 was captured twice** — once by clicking the tab
(`capture/40-run-workspace-tab.json`) and once by cold-loading the URL
(`capture/41-run-workspace-cold.json`), to prove both paths work. The two render
identically, so there is one screenshot rather than two.
