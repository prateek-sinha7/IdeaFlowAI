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
| C11 | `preview/PrototypePreview` | View source / Tweaks | ⛔ **never mounts — D-18** |
| C12 | `composer/AgentSkillsPicker` | Agent rail → Skills | ➖ **not an overlay** — inline in the rail (`83`) |
| C13 | `composer/WorkflowPickerModal` | ROUTE node → rail Config → Target | ✅ `87` |
| C14 | `ppt/PPTTemplateGallery` upload | `Upload custom` (ppt) | ✅ `80` |
| C15 | `prototype/TemplateDetailModal` (3) | template tile (prototype) | ✅ `76` |
| C16 | `prototype/CustomTemplateModal` | `Upload custom` (prototype) | ✅ `77` — same component as C14 |
| C17 | `prototype/DesignSystemDetailModal` (3) | design-system tile | ✅ `78` |
| C18 | `prototype/CustomDesignSystemModal` (2) | custom design system | ✅ `79` |
| C19 | `workflow/SkillManager` | `Manage skill` on an AgentNode | ⛔ **unreachable — D-17** |
| C20 | `workflow/WorkflowDialog` (2) | *(same component as C6)* | ✅ `49` — **double-counted since sweep 2** |
| C21 | `app/admin` create + toast | `Add user` | ✅ `81` |
| C22 | legacy builder add-agent | `Add Agent` on `/workflow` | ✅ `86` — empty for all 6 categories (**D-17**) |
| C23 | `app/admin` delete confirm | `Delete <email>` per row | 📝 specified from source (`19-toasts-and-dialogs`) — destructive, not captured |
| C24 | `ui/CompletionToast` | a run finishes | 📝 specified from source — needs a live run |
| C25 | admin toast | any admin mutation | 📝 specified from source |
| C26 | native `window.alert` ×6 | a failed download or export | 📝 specified from source (`19-toasts-and-dialogs`) |

Legend: ✅ captured · 📝 specified from source, not yet captured · ⛔ unreachable (a defect)

**19 of 19 reachable overlays captured**, plus four transient/destructive layers
(C23–C26) specified from source in sweep 6 — a delete-user confirm nobody had
noticed, two toast families, and six native `window.alert` calls.
 The original 21 was wrong twice: C20 is the
same component as C6 (double-counted), and C12 is an inline rail panel, not an overlay.
Of the 19 real ones, C11 and C19 **cannot be opened by any user** — both are defects
(D-18, D-17), not coverage gaps.

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
| Preview renderer | per deliverable type — a `.md` offers Auto/HTML/Markdown/Bundle, a prototype offers Auto/**Prototype** | ✅ 5 of 6 (`84`) — Slides needs a deck |
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

## H. The concierge chat lane

Not a page, not a tab, not an overlay — the **left column of every run-detail
surface**, present on all five tabs and all nine run URLs. It was absent from this
manifest entirely until sweep 5b.

| Aspect | Status |
|---|---|
| Lane on every tab | ✅ verified on `/runs/{id}`, `/files`, `/audit` |
| Header (type, status, title, meta, back) | ✅ `c01`–`c05` |
| Transcript + `data-role` / `data-message-id` | ✅ — only `narrator` exists in seeded data |
| Narrator vocabulary (7 message kinds) | ✅ |
| Adornments collapse / expand | ✅ |
| Composer enable-on-input | ✅ |
| Composer per run state | ✅ all 6 runs (**D-19**) |
| Chain suggestions + beta chip | ✅ `c01` |
| `user` / `assistant` message roles | ⬜ needs a live LLM turn — real cost, and it can create a gate |
| `waiting_for_user` blocking gate | ⬜ the seeded run has since completed |

**8 of 10.** Specified in `screens/18-chat-lane.feature.md`.

## Score

| Group | S1 | S2 | S3 | S4 | S5 | S6 | Total |
|---|---|---|---|---|---|---|---|
| A. Pages outside catch-all | 4 | 9 | 9 | 9 | 9 | 9 | 9 |
| B. Catch-all screens | 35 | 35 | 36 | 36 | 36 | 36 | 36 |
| C. Overlays | 6 | 11 | 11 | 17 | 19 | **23** | 23 |
| D. Run states | 1 | 5 | 5 | 5 | 5 | **6** | 6 |
| E. Tab families | 5 | 10 | 10 | 13 | 13 | 13 | 13 |
| F. Tier variants | 1 | 4 | 4 | 4 | 4 | **5** | 5 |
| G. Cross-cutting | 1 | 8 | 9 | 9 | 9 | **14** | 14 |
| H. Chat lane | 0 | 0 | 0 | 0 | 8 | **10** | 10 |
| I. Keyboard | 0 | 0 | 0 | 0 | 1 | **4** | 4 |
| J. Navigation edges | 0 | 0 | 0 | 0 | 0 | **6** | 6 |
| K. Run families & versions | 0 | 0 | 0 | 0 | 0 | **8** | 8 |
| L. Handoff & gates | 0 | 0 | 0 | 0 | 1 | **9** | 9 |
| **Total** | **53** | **82** | **84** | **93** | **105** | **143** | **143** |

**Every surface in the product is now specified.** Not every one is *captured* — the
distinction is the point of sweep 6 and is marked per scenario:

| Tag | Meaning | Count |
|---|---|---|
| *(untagged)* | verified in a real browser and screenshotted | most |
| `@sourced` | selector and copy read from the component; behaviour not yet seen | sweep 6 |
| `@unverified` | an open question, deliberately not asserted | a handful |
| `@defect` | written to today's WRONG behaviour, with the expected fix in a comment | 21 |
| `@destructive` | writes or deletes; needs its own fixture | handoff, admin, gates |

Sweep history:

- **S3** re-captured all 55 page URLs with a settle; corrected five claims written
  from reading source instead of loading the URL (**C-1 … C-5**).
- **S4** closed the overlay and tab-family gaps; found **D-13 … D-16**, including a
  fourth tier, `hexaware`, no spec knew about.
- **S5** traced the last overlays to their mount points instead of hunting them, and
  specified the concierge chat lane. Found **D-17 … D-21**.
- **S6** widened the enumerator past `fixed inset-0` (`_gaps.py`) and wrote a spec
  for **everything it found**, source-derived and tagged `@sourced`: toasts, native
  dialogs, the delete-user confirm nobody had noticed, keyboard, 100 navigation
  edges, the error boundaries, run families and versions, and the handoff and gate
  controls. Four new feature files, 19–22.

## What is specified but NOT yet captured, and why

| Area | Spec | Blocker |
|---|---|---|
| Toasts, native alerts, delete-user confirm | `19` | dev server 500; delete needs a disposable fixture user |
| Keyboard, nav edges, error boundaries | `20` | dev server 500; boundaries need fault injection |
| Run families, versions, divert links | `21` | no multi-version run family exists |
| Handoff with a valid token | `22` | needs a token minter |
| Gate and clarify controls | `22` | needs a `waiting_for_user` run — a live LLM call, answered by a human |
| `hexaware` tier | `17` | no seeded account |
| Empty-account states, cross-account 403 | `06`, `13`, `17` | needs a second account's session |
| Slides renderer mode | `07` | needs a deck deliverable |
| Loading / skeleton frames | `20` | needs request throttling |
| Responsive breakpoints | — | not attempted; the only surface with no spec at all |

**One honest exception:** responsive breakpoints have no scenarios anywhere. Every
other surface in the product has at least a `@sourced` spec.
