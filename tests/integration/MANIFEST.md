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
| A1 | `/` | `app/page.tsx` | 200 | 🔎 redirects to `/login` unconditionally |
| A2 | `/login` | `app/login/page.tsx` | 200 | ✅ `01`, `02` |
| A3 | `/register` | `app/register/page.tsx` | 200 | 🔎 redirect stub to `/login` |
| A4 | `/admin` | `app/admin/page.tsx` | 200 | ✅ `36` |
| A5 | `/workflow` | `app/workflow/page.tsx` | 200 | ✅ `55` — **not in routes.ts** |
| A6 | `/workflow/create` | `app/workflow/create/page.tsx` | 200 | ✅ via `05`,`06` — legacy wizard |
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
| run-version | `/runs/{id}/versions/{v}` | ⬜ no multi-version run exists |
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
| unknown | `/{anything}` | ✅ `39` |

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
| C11 | `preview/PrototypePreview` | View source / Tweaks | ⬜ |
| C12 | `composer/AgentSkillsPicker` | node → Skills | ⬜ |
| C13 | `composer/WorkflowPickerModal` | divert target picker | ⬜ |
| C14 | `ppt/PPTTemplateGallery` upload | `Upload custom` (ppt) | ⬜ |
| C15 | `prototype/TemplateDetailModal` (3) | template tile (prototype) | ⬜ |
| C16 | `prototype/CustomTemplateModal` | `Upload custom` (prototype) | ⬜ |
| C17 | `prototype/DesignSystemDetailModal` (3) | design-system tile | ⬜ |
| C18 | `prototype/CustomDesignSystemModal` (2) | custom design system | ⬜ |
| C19 | `workflow/SkillManager` | skill management | ⬜ |
| C20 | `workflow/WorkflowDialog` (2) | workflow dialog | ⬜ |
| C21 | `app/admin` create + toast | `Add user` | ⬜ |

**6 of 21 captured.**

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
| Composer config rail | Workflow, Agent | ⬜ 1 of 2 |
| Advanced modal | Agents, Workflow | ✅ both (`50`,`51`) |
| Audit filters | All, Governance, Security, Activity, blocked-only | ✅ 4 of 5 (`72`) |
| Preview renderer | Auto, HTML, Markdown, Bundle, Slides | ⬜ 1 of 5 |
| Run history filters | All, User Stories, Presentation, Prototype, App Builder, Custom | ⬜ 1 of 6 |
| Run history sort | Newest, Longest, Tokens | ⬜ 1 of 3 |
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
| Error: nonexistent workflow id | ⬜ |
| Error: invalid handoff token | ✅ `58` |
| Error: preview quota exceeded | ✅ `56` |
| Error: another user's run (403) | ⬜ needs two sessions |
| Loading / skeleton | ⬜ (38 files render one) |
| Mobile / responsive | ⬜ |

---

## Score

| Group | Sweep 1 | Sweep 2 | Total |
|---|---|---|---|
| A. Pages outside catch-all | 4 | **9** | 9 |
| B. Catch-all screens | 35 | 35 | 36 |
| C. Overlays | 6 | **11** | 21 |
| D. Run states | 1 | **5** | 6 |
| E. Tab families | 5 | **10** | 13 |
| F. Tier variants | 1 | **4** | 4 |
| G. Cross-cutting | 1 | **8** | 14 |
| **Total** | **53** | **82** | **103** |

**80% captured.** Sweep 1 reported completeness at what was really 51%.

## What is still open, and why

| Gap | Blocker |
|---|---|
| `waiting_for_user` run state | needs a live LLM run — real cost, and it creates a gate a human must answer |
| 10 remaining overlays | inside the prototype galleries and the composer node inspector |
| Preview renderer modes | needs deliverables of several types (deck, app, markdown) |
| Run-history filters / sort | mechanical; next increment |
| Empty account states | needs a user with zero runs and zero workflows |
| Cross-account 403 | needs two concurrent sessions |
| Loading / skeleton states | needs request throttling to observe |
| Responsive breakpoints | not attempted |
| `/runs/{id}/versions/{v}` | no multi-version run exists |
