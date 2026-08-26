# Surface manifest — the complete capture checklist

Derived from source, not from clicking around. Regenerate the raw enumeration with:

```
python3 tests/integration/capture/_enumerate.py
```

Sources of truth:
- **Pages** — `find frontend/src/app -name page.tsx` (Next.js file routing)
- **Screens** — `ParsedView` in `frontend/src/lib/routes.ts` (36 + `unknown`)
- **Overlays** — files matching `fixed inset-0` or `role="dialog"` (20 components)
- **States** — run `status` values from `GET /api/runs`

Legend: ✅ captured · ⬜ not captured · 🔎 code-verified only (no screenshot)

---

## A. Pages outside the catch-all

`routes.ts` does **not** cover these. Four of the five were missing from the first
inventory entirely.

| # | Path | File | HTTP | Status |
|---|---|---|---|---|
| A1 | `/` | `app/page.tsx` | 200 | ✅ `p05` — branches on token presence: `/dashboard` or `/login` (**C-3**) |
| A2 | `/login` | `app/login/page.tsx` | 200 | ✅ `01`, `02` |
| A3 | `/register` | `app/register/page.tsx` | 200 | ✅ `p04` — redirect stub to `/login` |
| A4 | `/admin` | `app/admin/page.tsx` | 200 | ✅ `36` |
| A5 | `/workflow` | `app/workflow/page.tsx` | 200 | ✅ `55` — **not in routes.ts** |
| A6 | `/workflow/create` | `app/workflow/create/page.tsx` | 200 | ✅ `p13`,`p14` — **redirects to `/create/{mode}` (C-1)** |
| A7 | `/preview-fullscreen` | `app/preview-fullscreen/page.tsx` | 200 | ✅ `56` — **not in routes.ts** |
| A8 | `/handoff/settings` | `app/handoff/settings/page.tsx` | 200 | ✅ `57` — **not in routes.ts** |
| A9 | `/handoff/{token}` | `app/handoff/[token]/page.tsx` | 200 | ✅ `58` (invalid token) |

## B. Catch-all screens (`ParsedView`, 36 + unknown)

| Screen | Route | Status |
|---|---|---|
| home | `/dashboard` | ✅ `03` |
| create | `/create` | ✅ `04` |
| create-ppt | `/create/ppt` | ✅ `05` |
| create-prototype | `/create/prototype` | ✅ `06` |
| create-app | `/create/app` | ✅ `07` (**D-01**) |
| create-user-stories | `/create/user-stories` | ✅ `08` |
| create-workflow | `/create/{type}` | ✅ `09` |
| workflows | `/workflows` | ✅ `10` |
| workflow-new | `/workflows/new` | ✅ `11`, `54` |
| workflow | `/workflows/{id}` | ✅ `12` |
| workflow-edit | `/workflows/{id}/edit` | ✅ `13` |
| workflow-canvas | `/workflows/{type}/canvas` | ✅ `14` |
| workflow-run | `/workflows/{id}/run` | ✅ `15` |
| run-history | `/runs` | ✅ `16` |
| run-detail | `/runs/{id}` | ✅ `17` |
| run-steps | `/runs/{id}/steps` | ✅ `18` |
| run-steps-agent | `/runs/{id}/steps/{agentId}` | ✅ `19` |
| run-files | `/runs/{id}/files` | ✅ `20` |
| run-audit | `/runs/{id}/audit` | ✅ `21` |
| run-preview-full | `/runs/{id}/preview/full` | ✅ `22` |
| run-stream | `/runs/{id}/stream` | ✅ `23`, `45` |
| *(unrouted)* run-workspace | `/runs/{id}/workspace` | ✅ `40` (**D-02**) |
| run-version | `/runs/{id}/versions/{v}` | ✅ `p34` — renders; only a version *switch* is unobservable (**C-4**) |
| library | `/library` | ✅ `24`–`26` |
| library-agent | `/library/agents/{slug}` | ✅ `27` |
| library-skill | `/library/skills/{slug}` | ✅ `28` |
| library-hook | `/library/hooks/{slug}` | ✅ `29` |
| settings-profile | `/settings/profile` | ✅ `30` |
| settings-ai-model | `/settings/ai-model` | ✅ `31` |
| settings-usage | `/settings/usage` | ✅ `32` |
| settings-constitution | `/settings/constitution` | ✅ `33` |
| settings-security | `/settings/security` | ✅ `34` |
| analytics | `/analytics` | ✅ `35` |
| admin | *(dead code — A4 serves it)* | ✅ `36` |
| login / register | *(A2 / A3 serve them)* | ✅ |
| unknown | `/{anything}` | ✅ `p51`; `/settings` does NOT reach it (**C-2**) |

## C. Overlays — 20 components render a `fixed inset-0` / `role="dialog"` layer

| # | Component | Opened by | Status |
|---|---|---|---|
| C1 | `workflow/AgentsPopup` (4 layers) | `Advanced N agents` | ✅ `50`, `51` |
| C2 | `catalog/NameWorkflowModal` | Save / Save as my version | ✅ `52` |
| C3 | `workflow/AgentLibrary` | `Add agent` on canvas | ✅ `53` |
| C4 | `ui/NotificationPanel` | Notifications | ✅ `38` |
| C5 | `library/LibraryPage` detail | card / `Configure →` | ✅ `27`–`29` |
| C6 | catalog inspect dialog | `Inspect X details` | ✅ `49` |
| C7 | `history/WorkflowHistory` (3 layers) | Run actions menu | ✅ `70` |
| C8 | `savedworkflows/SavedWorkflowsPage` (3) | Workflow actions menu | ✅ `69` |
| C9 | `results/ArtifactVersionPicker` | `Version v1` | ✅ `71` |
| C10 | `preview/RunHeader` | Share / Download | ✅ `71` (Share = copy-link, no dialog) |
| C11 | `preview/PrototypePreview` | View source / Tweaks | ⬜ needs a completed prototype run |
| C12 | `composer/AgentSkillsPicker` | Agent rail → Skills | ➖ **not an overlay** — inline in the rail (`83`) |
| C13 | `composer/WorkflowPickerModal` | divert target picker | ⬜ needs a workflow with a divert step |
| C14 | `ppt/PPTTemplateGallery` upload | `Upload custom` (ppt) | ✅ `80` |
| C15 | `prototype/TemplateDetailModal` (3) | template tile (prototype) | ✅ `76` |
| C16 | `prototype/CustomTemplateModal` | `Upload custom` (prototype) | ✅ `77` — same component as C14 |
| C17 | `prototype/DesignSystemDetailModal` (3) | design-system tile | ✅ `78` |
| C18 | `prototype/CustomDesignSystemModal` (2) | custom design system | ✅ `79` |
| C19 | `workflow/SkillManager` | skill management | ⬜ unreachable in 4 sweeps — possibly dead |
| C20 | `workflow/WorkflowDialog` (2) | workflow dialog | ⬜ unreachable in 4 sweeps — possibly dead |
| C21 | `app/admin` create + toast | `Add user` | ✅ `81` |

**17 of 20 captured** (C12 reclassified out of this group).

## D. Run lifecycle states

| Status | Count in dev DB | Status |
|---|---|---|
| completed | 36 | ✅ `17`–`22` |
| failed | 8 | ✅ `42`–`44` |
| cancelled | 11 | ✅ `47` |
| diverted | 4 | ✅ `48` |
| generating (live) | 1 | ✅ `45`, `46` |
| **waiting_for_user** | 0 exist | ⬜ **needs a live LLM run — flagged, not spent** |

## E. Tab families

| Family | Members | Status |
|---|---|---|
| Run detail | Preview, Steps, Files, Workspace, Audit | ✅ all 5 |
| Settings | Profile, AI Model, Usage, Constitution, Security | ✅ all 5 |
| Library list | Agents, Skills, Hooks | ✅ all 3 |
| Library agent drawer | Overview, Skills, Hooks, Config | ✅ all 4 (`73`) |
| Prototype wizard | Template, Design System, Discovery | ✅ all 3 (`06`,`74`,`75`) |
| Composer view | Simple, Canvas | ✅ both (`11`,`54`) |
| Composer config rail | Workflow, Agent | ✅ both (`82`) — Agent has 5 sub-tabs of its own |
| Advanced modal | Agents, Workflow | ✅ both (`50`,`51`) |
| Audit filters | All, Governance, Security, Activity, blocked-only | ✅ 4 of 5 (`72`) |
| Preview renderer | Auto, HTML, Markdown, Bundle, Slides | ✅ 4 of 5 (`84`) — Slides needs a deck |
| Run history filters | All, User Stories, Presentation, Prototype, App Builder, Custom | ✅ all 6 (`85`) — `?type=` |
| Run history sort | Newest, Longest, Tokens | ✅ all 3 — `?sort=` |
| Library categories | 14 agent / 10 skill / 5 hook | ⬜ 1 each |

## F. Tier variants

| Account | Tier | Admin | Status |
|---|---|---|---|
| qa-admin | enterprise | yes | ✅ everything |
| qa-enterprise | enterprise | no | ✅ `68` — menu + lock matrix |
| qa-pro | pro | no | ✅ `67` — lock matrix |
| qa-basic | basic | no | ✅ `64`,`65`,`66` — catalog, usage, admin denial |

## G. Cross-cutting states

| State | Status |
|---|---|
| Light theme | ✅ all shots |
| Dark theme | ✅ `59`–`62` (dashboard, run steps, canvas, library) |
| Empty: no runs | ⬜ needs a fresh account |
| Empty: no workflows | ⬜ needs a fresh account |
| Empty: no notifications | ✅ `38` |
| Empty: no audit records for a filter | ✅ `72` |
| Empty: no suggested hooks for an agent | ✅ `73` |
| Error: nonexistent run id | ✅ `63` (generic 404) |
| Error: nonexistent workflow id | ✅ `p53` — identical to the generic 404 |
| Error: invalid handoff token | ✅ `58` |
| Error: preview quota exceeded | ✅ `56` |
| Error: another user's run (403) | ⬜ needs two sessions |
| Loading / skeleton | ⬜ (38 files render one) |
| Mobile / responsive | ⬜ |

---

## Score

| Group | Sweep 1 | Sweep 2 | Sweep 3 | Sweep 4 | Total |
|---|---|---|---|---|---|
| A. Pages outside catch-all | 4 | 9 | 9 | 9 | 9 |
| B. Catch-all screens | 35 | 35 | 36 | 36 | 36 |
| C. Overlays | 6 | 11 | 11 | **17** | 20 |
| D. Run states | 1 | 5 | 5 | 5 | 6 |
| E. Tab families | 5 | 10 | 10 | **13** | 13 |
| F. Tier variants | 1 | 4 | 4 | 4 | **5** |
| G. Cross-cutting | 1 | 8 | 9 | 9 | 14 |
| **Total** | **53** | **82** | **84** | **93** | **103** |

**90% captured.** Sweep 1 reported completeness at what was really 51%.

- **Sweep 3** re-captured all 55 page URLs with a 2.5s settle into
  `screenshots/<area>/`, and corrected five claims the earlier sweeps had written
  from reading source instead of loading the URL (**C-1 … C-5**).
- **Sweep 4** was a post-commit audit of what this manifest still listed as open.
  It captured six of the ten remaining overlays and every remaining tab family,
  reclassified one "overlay" that is really an inline panel, and found four
  defects (**D-13 … D-16**) — including a **fourth tier**, `hexaware`, that no
  spec knew about. The tier total rose from 4 to 5 because of it.

**Every page URL is backed by a fingerprint in `capture/` and a full-page
screenshot.** `PAGES.md` is the per-page index: URL → shot → fingerprint → spec.

## What is still open, and why

| Gap | Blocker |
|---|---|
| `waiting_for_user` run state | needs a live LLM run — real cost, and it creates a gate a human must answer |
| a hexaware account (D-16) | no seeded fixture; the tier exists in code and in the admin dialog only |
| empty-account states (no runs, no workflows) | qa-pro / qa-basic / qa-enterprise all have 0 runs, so this is reachable — it needs the seeded password, which this session could not read |
| cross-account 403 | same blocker: needs a second account's session |
| C11 prototype preview source / tweaks | needs a completed prototype run |
| C13 workflow picker | needs a workflow containing a divert step |
| C19 SkillManager, C20 WorkflowDialog | never reached from any surface in four sweeps — confirm they are not dead code before specifying them |
| Slides renderer mode | needs a deck deliverable |
| a *switch* between artifact versions | no run in the dev DB has more than one version |
| loading / skeleton states | needs request throttling to observe |
| responsive breakpoints | not attempted |
