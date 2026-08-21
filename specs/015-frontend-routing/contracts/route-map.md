# 015 — Contract: Route map

This is the interface contract this feature exposes: the fixed set of URLs the app promises to
serve, and what each one redirects from. Any change to this table is a breaking change to a
bookmarked/shared link and must be a new redirect entry, not a silent removal.

## Screens (34 — see spec.md §5 for the grouped count, data-model.md for the parser table)

**Auth & root**
| Route | Serves |
|---|---|
| `/` | authed → `/dashboard`, else → `/login` (redirect only, not a screen) |
| `/login` | Login |
| `/register` | Redirect to `/login` (no self-registration screen exists; pre-dates this spec) |

**Home & creation**
| Route | Serves |
|---|---|
| `/dashboard` | Home launch grid |
| `/create` | Full launch catalog |
| `/create/ppt` | Pitch-an-idea config |
| `/create/prototype` | Prototype config |
| `/create/app` | App-builder wizard |
| `/create/user-stories` | PRD / user-stories brief |
| `/workflows/new` | Blank Composer |

**Runs**
| Route | Serves |
|---|---|
| `/runs` (`?type=&sort=`) | Run History |
| `/runs/{id}` | Run detail → Preview tab |
| `/runs/{id}/steps` | Steps tab |
| `/runs/{id}/steps/{agentId}` | One agent's expanded detail |
| `/runs/{id}/files` | Files tab |
| `/runs/{id}/audit` | Audit tab |
| `/runs/{id}/stream` | Live execution — refresh re-attaches |
| `/runs/{id}/versions/{v}` | Specific artifact version |
| `/runs/{id}/preview/full` | Run detail → Preview tab (legacy alias of `/runs/{id}`, see note below) |

**Note on `/runs/{id}/preview/full` (audit judgment call, 2026-08-21):** this row previously read
"Fullscreen artifact" and `data-model.md` documented a "fullscreen flag" distinguishing it from
plain `/runs/{id}` — neither was ever built. The route resolves and never 404s, but renders
byte-identical to `/runs/{id}` (same `"execution"` mainView, same default Preview tab). No live UI
action navigates here: the app's two real "Full Screen" affordances are (1) the App Builder
IDE preview's own trigger (`AppBuilderPreview.tsx`'s `handleFullscreen`), which opens
`/preview-fullscreen` reading `sessionStorage["__app_preview__"]`, and (2) the PPT/prototype/
generic deliverable "Full Screen" buttons (`PreviewPanel.tsx`'s `PPTTabActions`/`PreviewChrome`,
`WorkflowHistory.tsx`), which open the on-screen content as a `blob:` URL in a new tab — a
deliberate, repeated pattern (see the `handlePreviewOpen` comment in `PreviewPanel.tsx`) chosen to
avoid a second network round-trip and to work for live/in-progress content that isn't yet
persisted server-side (a route-based fetch-by-id can't serve that). `/runs/{id}/preview/full`
survives only as the redirect target for old `/preview-fullscreen?runId=` bookmarked links (see
Retired paths below); treat it as a legacy/simplified alias, not an active distinct screen.

**Saved workflows**
| Route | Serves |
|---|---|
| `/workflows` | My Workflows list |
| `/workflows/{id}` | Read view |
| `/workflows/{id}/edit` | Composer editing it |
| `/workflows/{id}/run` | Launch panel pre-filled → creates run → `/runs/{newId}/stream` |

**Library**

**Post-close amendment (2026-08-21):** the 3 list screens below (previously separate `/library/agents`,
`/library/skills`, `/library/hooks` path segments) merged into ONE path with the tab encoded as a
query param — simplification, plus a real bug fix: switching tabs never updated the URL, so the
active tab and the address bar could go out of sync. Item-DETAIL routes are unchanged. See
`spec.md`'s Clarifications, Session 2026-08-21.

| Route | Serves |
|---|---|
| `/library` (`?tab=&category=`) | Agents/Skills/Hooks tabs — `tab` omitted for `agents` (the default), `category` omitted for `all`/absent |
| `/library/agents/{slug}` | Agent detail |
| `/library/skills/{slug}` | Skill detail |
| `/library/hooks/{slug}` | Hook detail |

**Settings, analytics, admin**
| Route | Serves |
|---|---|
| `/settings` | → `/settings/profile` (redirect only) |
| `/settings/profile` | Profile tab |
| `/settings/ai-model` | AI Model tab |
| `/settings/usage` | Usage & Limits tab |
| `/settings/constitution` | Constitution tab |
| `/analytics` (`?range=&pipeline=`) | Analytics |
| `/admin` | Admin dashboard |

**Not in this table by design**: `/handoff`, `/handoff/{token}`, `/handoff/settings`. They
already have real, addressable routes today — they never lived inside the shared-URL page this
spec fixes — so they need no work here (spec.md §5). They still fall under FR-015's session-
expiry redirect, verified separately in SC-009.

## Retired paths (redirect, never 404 — FR-007, SC-004)

| Old path | New target | Status |
|---|---|---|
| `/test-preview` | *(none — deleted, FR-014)* | 404/not-found, deliberately not redirected |
| `/workflow/create?mode={t}` | `/create/{t}` | 307 (temporary) |
| `/preview-fullscreen` | `/runs/{id}/preview/full` | 301 |
| `/library/agents` (`?category=`) | `/library` (`?category=`) | 307 (temporary) |
| `/library/skills` (`?category=`) | `/library?tab=skills` (`&category=`) | 307 (temporary) |
| `/library/hooks` | `/library?tab=hooks` | 307 (temporary) |

## Cross-feature consumers of this contract

- **Spec 014** (`specs/014-conditional-gates/spec.md` R-20, R-28) reads `/runs/{id}` (diverted-run
  card links) and `/runs/{id}/stream` (the `pipeline_diverted` terminal SSE event is caught
  here). Changing either route's path pattern is a breaking change for 014's frontend work.
- **Error tracking / analytics** (go-live report §5.2/BLK-7/BLK-8, not this spec's scope) will
  want the `mainView` names from `data-model.md`'s parser table as the canonical screen-label
  vocabulary (FR-012) — those names are part of this contract too, not just the paths.
