# Redux store for `store/api` — Library slice (wired) + full slice scaffold (dead code)

**Scope note (read first):** this plan covers two different levels of completeness, on purpose:

- **`librarySlice`** (agents/workflows/skills/hooks) is the one slice that gets fully wired into the app — `StoreProvider`, dashboard preload, `useAgentLibrary`/`useWorkflowLibrary` rewrites, logout reset. This is the only part of the app whose *behavior* changes.
- **Every other `store/api/*.ts` module** (`auth`, `chats`, `capabilities`, `settings`, `handoff`, `mcp`, `install`, `files`, `ppt`, `prototype`, `runs`, `userWorkflows`, `admin`, `health`) gets a **slice scaffolded** — state shape, thunks, reducer, registered in the root store — but **nothing that currently calls those APIs is touched**. No component, hook, or page swaps its fetch calls for these. They compile, they're unit-testable, and `RootState`/`AppDispatch` cover them, but until someone deliberately imports from a given slice at a call site, it's inert. This is what "just the slices, nothing else, so we can switch them in later" means concretely.

## Problem

Today, agent + workflow data is fetched per-mount via two hooks:

- `useWorkflowLibrary()` (`src/hooks/useWorkflowLibrary.ts`) — calls `workflowsApi.list()` on every mount.
- `useAgentLibrary()` (`src/hooks/useAgentLibrary.ts`) — calls `useWorkflowLibrary()` *and* `agentsApi.library()` on every mount.

Both hooks are consumed independently by `LibraryPage.tsx` and `AgentLibrary.tsx` (the workflow-builder's "add agent" drawer). Neither hook shares state with the other, so:

- Opening the Library page and then opening the Agent drawer (or vice versa) re-fetches both endpoints from scratch.
- Navigating away and back re-fetches again — there's no cache, so the loading spinner flashes every time.
- `SKILLS` / `HOOKS` (`src/data/skills.ts`, `src/data/hooks.ts`) are static arrays, imported directly wherever needed. They're cheap, but they aren't exposed through the same access pattern as agents/workflows, so consumers reach into two different systems for what is conceptually one "library" domain.

## Goal

- Introduce a Redux store (Redux Toolkit) as the single source of truth for the Library domain: **workflows, agents, skills, hooks**.
- Preload all four on the home/dashboard shell, once, right after auth resolves — not per-page.
- Cache the API-backed pieces (agents, workflows) so revisiting Library / the Agent drawer within a **10 minute** window reuses the in-memory data instead of re-hitting the API.
- Keep `SKILLS`/`HOOKS` in the *same* `library` slice as agents/workflows (seeded synchronously, no network call) so all four datasets are read through one consistent `state.library.*` selector API — not a separate reducer key.
- Preserve existing consumer behavior (`LibraryPage`, `AgentLibrary`) with minimal churn — same shapes, same normalization rules, same loading/error semantics.
- Scaffold one Redux slice per remaining `store/api/*.ts` module, mirroring its exported methods 1:1, using the same shared conventions established for `librarySlice` — so that swapping a page's current `useState`/`useEffect`/direct-`api.*.call` pattern for the Redux equivalent later is a local, mechanical change instead of a design exercise.
- **Do all of this without duplicating logic 14 times over.** The de-duplication pass below (TTL condition, error extraction, logout reset, selector paths, folder layout) is as much a part of this plan as the slices themselves — see "Shared utilities" and the Audit.

## Folder layout — mirrors `store/api/` 1:1, no extra nesting

```
frontend/src/store/
  api/                    # UNCHANGED — agentsApi, workflowsApi, chatsApi, http, etc.
    agents.ts
    workflows.ts
    ...
  slices/                 # NEW — one reducer file per domain, same naming as api/
    librarySlice.ts        # agents.ts + workflows.ts + skills.ts + hooks.ts (WIRED)
    authSlice.ts            # auth.ts            (scaffold only)
    chatsSlice.ts            # chats.ts            (scaffold only)
    capabilitiesSlice.ts      # capabilities.ts      (scaffold only)
    settingsSlice.ts           # settings.ts            (scaffold only)
    handoffSlice.ts             # handoff.ts              (scaffold only)
    mcpSlice.ts                  # mcp.ts                   (scaffold only)
    installSlice.ts               # install.ts                 (scaffold only)
    filesSlice.ts                   # files.ts                     (scaffold only)
    pptSlice.ts                       # ppt.ts                         (scaffold only)
    prototypeSlice.ts                   # prototype.ts                     (scaffold only)
    runsSlice.ts                          # runs.ts                            (scaffold only)
    userWorkflowsSlice.ts                   # userWorkflows.ts                     (scaffold only)
    adminSlice.ts                             # admin.ts                               (scaffold only)
    healthSlice.ts                              # health.ts                                (scaffold only)
  store.ts                # makeStore() factory, RootState, AppDispatch, AppStore
  hooks.ts                 # useAppDispatch / useAppSelector
  types.ts                  # AsyncStatus, DEFAULT_TTL_MS, isStale(), createTtlCondition(), getErrorMessage()
```

**Why this shape and not `store/redux/slices/*`:** `store/` is already the app's name for "the data-access layer" (that's what `store/api/` is today — despite the name, there's no Redux in this repo yet). Nesting an extra `redux/` folder under `store/` would mean two sibling concepts (`store/api/agents.ts` and `store/redux/slices/librarySlice.ts`) that both "belong to" `store/` but sit three and four levels deep respectively, for no benefit — nothing else lives in `store/` that a `redux/` folder needs to be disambiguated from. Flattening to `store/slices/`, `store/store.ts`, `store/hooks.ts`, `store/types.ts` — siblings of `store/api/` — means every slice file's import of its matching API module is a one-level-up sibling reference (`../api/workflows`), the file tree visually pairs each `slices/xSlice.ts` with `api/x.ts`, and there's no ambiguity about what `store/` means in this codebase going forward: it's the whole client-side data layer, API clients plus the Redux state built on top of them.

`store/redux/index.ts` becomes `store/store.ts` (avoids the `index.ts`-inside-`index.ts`-adjacent-folder ambiguity `store/redux/index.ts` had, and matches naming precedent — most RTK example repos name the root store file `store.ts`, not `index.ts`).

## Shared utilities — the actual de-duplication pass (`store/types.ts`)

This is the section that exists specifically to answer "make sure nothing is duplicated." Fourteen-plus slices, several with multiple independently-cacheable sub-resources (settings has 4, runs and prototype have several each), is exactly the situation where copy-pasting the same TTL-guard ternary and the same `err instanceof Error ? err.message : fallback` line into every thunk turns into 20+ near-identical blocks that drift out of sync the first time someone tweaks one of them. Three small shared exports prevent that:

```ts
// store/types.ts
export type AsyncStatus = 'idle' | 'loading' | 'succeeded' | 'failed';
export const DEFAULT_TTL_MS = 10 * 60 * 1000;

export function isStale(lastFetchedAt: number | null, ttlMs = DEFAULT_TTL_MS): boolean {
  return lastFetchedAt === null || Date.now() - lastFetchedAt >= ttlMs;
}

/**
 * Shared TTL/in-flight guard for createAsyncThunk's `condition` option.
 * Every ✅ (TTL-cached read) thunk across every slice uses this instead of
 * hand-rolling the same three-branch check — see slice inventory below.
 */
export function createTtlCondition<S extends { status: AsyncStatus; lastFetchedAt: number | null }>(
  selectSlice: (state: unknown) => S,
  ttlMs = DEFAULT_TTL_MS
) {
  return (arg: { force?: boolean } | undefined, { getState }: { getState: () => unknown }): boolean => {
    const slice = selectSlice(getState());
    if (arg?.force) return true;
    if (slice.status === 'loading') return false;
    if (slice.status === 'succeeded' && !isStale(slice.lastFetchedAt, ttlMs)) return false;
    return true;
  };
}

/** Every thunk's `catch`/`rejectWithValue` path uses this instead of a copy-pasted ternary. */
export function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}
```

`librarySlice.ts` and all 13 scaffold slices import these rather than each defining their own `TTL_MS` constant, their own inline `condition` ternary, or their own `err instanceof Error ? ...` line. A slice's own file only ever contains what's actually specific to that slice: its state shape, its API calls, and its reducers.

### Cross-slice logout reset — one dispatch, not N

Audit finding #2 (below) identified that `librarySlice` needs to clear itself on logout because `StoreProvider` outlives the client-side navigation to `/login`. That same fact is true for **every other user/tenant-scoped slice** once it's actually wired up later: `chatsSlice`, `runsSlice`, `userWorkflowsSlice`, `settingsSlice`, `adminSlice` would each independently need the identical fix. Rather than requiring every future call-site swap to remember "also add a reset-on-logout dispatch" — the exact kind of thing that gets missed — the reset is designed as a **shared action every user-scoped slice listens for**, decided now while all the slices are being scaffolded in one pass:

```ts
// store/slices/authSlice.ts
export const sessionEnded = createAction('auth/sessionEnded');
```

(A plain action, not the `authApi.logout()` async thunk — `authSlice`'s own `logout` thunk stays unused/scaffold-only along with the rest of `authSlice`, matching the stated scope. `sessionEnded` is the one thing dispatched from a real call site: `dashboard/page.tsx`'s existing `handleLogout`, exactly where `resetLibrary()` would otherwise have been dispatched.)

Every user-scoped slice adds one line to its `extraReducers`:

```ts
// e.g. store/slices/librarySlice.ts
builder.addCase(sessionEnded, () => initialState);
```

This is a standard, documented RTK pattern (a slice reacting to an action type it didn't define, via `builder.addCase` on an imported action creator) — not a custom mechanism. `handleLogout` dispatches `sessionEnded()` once; today that resets `library` (the only slice actually wired), and the moment `chatsSlice`/`runsSlice`/etc. get wired up later, they opt in with the same one-line `addCase` instead of dashboard needing a growing list of manual reset dispatches.

### Selector exports — no inlined state-path strings at call sites

Every slice exports its own selectors alongside its reducer (e.g. `librarySlice.ts` exports `selectWorkflows`, `selectAgents`, `selectLibraryStatus`, not just the reducer), and consumers (`useWorkflowLibrary`, future call sites) import those instead of writing `useAppSelector(s => s.library.workflows)` inline. This means the string `"library"` (the reducer key) exists in exactly one place — the slice's own selector functions and its registration in `store.ts` — instead of being re-typed at every `useAppSelector` call site, which is both a duplication risk and the thing that silently breaks if a reducer key is ever renamed.

## Audit — dry run of the original plan (senior-FE pass)

Walking the original plan through as if implementing it end-to-end surfaced four things that would either break in production, silently regress existing behavior, or bite the next engineer. All four are folded into the sections below; this is the "what could ruin it" record.

### 1. Module-level `store` singleton leaks across requests/users (critical — SSR)

The original plan had `export const store = configureStore(...)` at module scope, consumed by a `"use client"` `StoreProvider`. That's the textbook Next.js + Redux footgun: App Router still renders client components on the **server** for the initial HTML pass, and a module-level singleton is evaluated once per Node.js server process, not once per request. Under concurrent traffic, two different users' requests can share (and mutate) the same store instance server-side — one user's preloaded agents/workflows could leak into another user's initial render. It also breaks hydration determinism if the server-rendered store and the client's first-render store ever diverge (e.g. a request landing mid-mutation).

**Fix:** replace the singleton with a `makeStore()` factory, instantiated once per `StoreProvider` mount via `useRef` (the pattern Redux Toolkit's own Next.js docs prescribe):

```ts
// store/store.ts
export const makeStore = () => configureStore({ reducer: { /* ... */ } });

export type AppStore = ReturnType<typeof makeStore>;
export type RootState = ReturnType<AppStore['getState']>;
export type AppDispatch = AppStore['dispatch'];
```

```tsx
// providers/StoreProvider.tsx
"use client";
export function StoreProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<AppStore | null>(null);
  if (!storeRef.current) storeRef.current = makeStore();
  return <Provider store={storeRef.current}>{children}</Provider>;
}
```

This also fixes test isolation for free — unit tests import `makeStore()` and get a clean store per test instead of fighting shared module state across the Vitest run.

### 2. Stale library data survives logout → login on the same tab (critical — correctness)

`handleLogout` in `dashboard/page.tsx` calls `logout()` then `router.replace("/login")` — a **client-side** navigation, not a full page reload. `StoreProvider` sits at the root layout, above the router, so it never unmounts across that navigation. Result: if a different user logs into the same browser tab within the 10-minute TTL window, the dashboard's preload effect re-runs (`isAuthenticated` flips false → true), but `fetchLibrary`'s staleness check sees `status: 'succeeded'` and a recent `lastFetchedAt` and **skips the refetch** — the new user would see the previous user's cached agents/workflows for up to 10 minutes. This matters here because the library already has a `custom` agent category and per-tenant pipeline types, i.e. this is plausibly user/tenant-scoped data, not a static catalog.

**Fix:** dispatch the shared `sessionEnded` action (see "Cross-slice logout reset" above — not a library-specific `resetLibrary`, so the fix generalizes to every future user-scoped slice for free) from `handleLogout` before navigating away:

```ts
const handleLogout = useCallback(async () => {
  await logout(getToken() ?? "");
  dispatch(sessionEnded());
  router.replace("/login");
}, [router, dispatch]);
```

### 3. `Promise.all` couples two independently-failing calls (regression in resilience)

Today, `useWorkflowLibrary` and the agents fetch inside `useAgentLibrary` are two **independent** effects/promises — a failure in one doesn't block the other, and `LibraryPage.tsx` only ever surfaces `agentsError` (it doesn't check a workflow-specific error at all). The original plan's single `Promise.all([workflowsApi.list(), agentsApi.library()])` couples them: if either call rejects, the whole thunk rejects and **both** arrays stay empty — including the one that would have succeeded. That's a real regression: a flaky workflows endpoint would now take down the agents list too.

**Fix:** use `Promise.allSettled` inside the thunk, apply whichever result(s) fulfilled, and don't wipe previously-cached data for the side that failed:

```ts
const [workflowsResult, agentsResult] = await Promise.allSettled([
  workflowsApi.list(), agentsApi.library(),
]);
// in the fulfilled case reducer: only overwrite `workflows` if workflowsResult.status === 'fulfilled',
// same for `agents`; set `error` from whichever settled as 'rejected' (or null if both succeeded),
// via getErrorMessage() from store/types.ts, not a bespoke ternary.
```

### 4. Two named thunks (`fetchLibraryIfStale` / `refetchLibrary`) invite a "called the wrong one" bug

The original draft had `fetchLibrary`, `fetchLibraryIfStale`, and a `refetchLibrary` variant as three separate exports. That's more surface than needed and it's exactly the kind of thing where a future edit calls `fetchLibrary()` directly (bypassing the TTL guard) by mistake, silently reintroducing the "refetch on every mount" bug this whole change exists to fix.

**Fix:** collapse to a single `fetchLibrary` thunk that always carries the TTL guard via RTK's `condition` option, built from the shared `createTtlCondition()` helper (not a hand-rolled inline check — see "Shared utilities" above, which is itself a fix for the duplication this same finding would otherwise cause across 14 more slices). An optional `force` arg satisfies the "explicit refresh" case without a second exported thunk:

```ts
// store/slices/librarySlice.ts
export const fetchLibrary = createAsyncThunk<
  { workflows: PromiseSettledResult<WorkflowSummary[]>; agents: PromiseSettledResult<AgentLibraryResponse> },
  { force?: boolean } | undefined,
  { state: RootState }
>(
  'library/fetch',
  async () => Promise.allSettled([workflowsApi.list(), agentsApi.library()]),
  { condition: createTtlCondition((s: RootState) => s.library) }
);
```

(Note the explicit `{ state: RootState }` third type param on `createAsyncThunk` — without it, `getState()` inside `condition` types as `unknown` and the staleness check won't compile under this repo's strict TS config. `createTtlCondition`'s own signature handles this once, generically, so individual slices don't each need to re-derive it.)

All call sites — the dashboard preload effect and both hooks — call `dispatch(fetchLibrary())` (no `force`), and the TTL guard is the *only* place staleness is decided. This also means dispatching it redundantly from multiple mounted components (dashboard + `LibraryPage` + `AgentLibrary` drawer, which mounts its `useAgentLibrary()` call unconditionally regardless of the drawer's open/closed state) is safe by construction: `condition` + the synchronous `pending` dispatch mean the second and third calls in the same tick see `status: 'loading'` and no-op. Worth an explicit manual check in Testing (Network tab, only one request pair fires) rather than assuming it.

### Also worth flagging, not blocking

- **Selector granularity**: prefer the exported per-field selectors (see "Selector exports" above) over destructuring one wide `useAppSelector(s => s.library)`. Fine functionally either way (RTK/Immer gives structural sharing so a wide selector only re-renders when something in `library` actually changed), but exported selectors avoid re-typing the state path and are the idiomatic react-redux pattern.
- **`lib/api.ts`'s `getWorkflows`** (used in `dashboard/page.tsx` for recent-runs history) is a same-named-but-different endpoint (`/api/runs`, returns a `WorkflowRun[]`) from `store/api/workflows.ts`'s `workflowsApi.list()` (`/api/workflows`, returns `WorkflowSummary[]`) — confirmed these are unrelated domains (run history vs. workflow catalog), so there's no overlap to unify and no double-fetch to worry about here.
- **No cache-invalidation-on-mutation gap** for the library domain specifically: confirmed there's no endpoint that creates/edits/deletes entries in the agents/workflows list itself — so nothing needs to dispatch `fetchLibrary({ force: true })` after a mutation today. If a "create custom agent" flow is added later, it will need to.
- **Pre-existing type duplication landmines the scaffold must not deepen** (found while designing `chatsSlice`/`runsSlice` — see the inventory below for how each slice is scoped to avoid adding a *third* shape):
  - `WorkflowRun` already exists in **three** incompatible shapes: `store/api/runs.ts`'s `WorkflowRun` (raw snake_case, e.g. `agent_outputs: string | null`), `types/index.ts`'s `WorkflowRun` (normalized camelCase, e.g. `agentOutputs?: AgentThinkingEntry[]`), and `lib/api.ts`'s private `RawWorkflowRun` + `normalizeWorkflowRun()` (the wire shape `getWorkflows`/`getWorkflow` convert into `types/index.ts`'s shape before dashboard ever sees it).
  - `ChatSession`/`ChatMessage` exist in **two** shapes: `store/api/chats.ts`'s (raw snake_case, matches `chatsApi`'s actual return types) and `types/index.ts`'s (richer camelCase UI shape with `artifact`/`steps`, used by `dashboard/page.tsx`'s local chat state today).

## Non-goals

- **Not migrating any existing call site other than `useAgentLibrary`/`useWorkflowLibrary`.** Every page/component currently calling `chatsApi`, `runsApi`, `settingsApi`, etc. directly (or via `lib/api.ts`) keeps doing exactly that. The new slices for those domains sit unused until a follow-up task explicitly swaps a call site over — this plan does not decide *when* that happens, and does not attempt to reconcile the pre-existing `WorkflowRun`/`ChatSession` type duplication called out above (that's a pre-existing condition, not something this plan is scoped to fix — it's flagged so the scaffold doesn't blindly add a third/fourth shape on top).
- Not adopting RTK Query. A plain slice + `createAsyncThunk` gives explicit control over the 10-minute TTL rule without pulling in RTK Query's cache-lifecycle model (`keepUnusedDataFor`, tag invalidation) which is a bigger conceptual shift than this task needs, and keeps every slice in the same idiom.
- Not touching `SkillsHooksContext` (`src/context/SkillsHooksContext.tsx`) — that's *user-attached* skills/hooks selection state (a different concern from the read-only catalog), stays as-is.
- Not adding TTL caching to genuinely live/mutable/streaming endpoints where a cache would be actively wrong (chat messages, run status polling, health checks, the prototype NDJSON stream, MCP JSON-RPC calls) — see the per-slice notes below for which ones intentionally skip the `condition` guard and why.

## Package additions

```
@reduxjs/toolkit
react-redux
```

Nothing else in the repo currently pulls in Redux — confirmed via `package.json` (no `redux`/`zustand`/`swr`/`react-query`).

## `librarySlice.ts` (wired)

One combined slice, not two/four. All four Library-page datasets live under a single `state.library` key, since that's how the app actually thinks about them (`LibraryPage.tsx` has one tab bar: Agents / Skills / Hooks, plus workflow categories as agent filters). `skills`/`hooks` need no fetch/TTL — they're just seeded fields sitting next to the async ones.

State:

```ts
interface LibraryState {
  workflows: WorkflowSummary[];
  agents: AgentDef[];
  skills: SkillDef[];   // seeded from SKILLS at initialState, never fetched
  hooks: HookDef[];     // seeded from HOOKS at initialState, never fetched
  status: AsyncStatus;  // covers agents+workflows only
  error: string | null;
  lastFetchedAt: number | null; // epoch ms — agents+workflows only
}

const initialState: LibraryState = {
  workflows: [],
  agents: [],
  skills: SKILLS,
  hooks: HOOKS,
  status: 'idle',
  error: null,
  lastFetchedAt: null,
};
```

- `fetchLibrary`, a single `createAsyncThunk` (see Audit finding #4 for the full signature, built on `createTtlCondition` from `store/types.ts`) that:
  - Fetches `workflowsApi.list()` and `agentsApi.library()` via `Promise.allSettled` (see Audit finding #3) — a failure in one does not blank out the other.
  - Applies the existing `normalizeWorkflows` (from `useWorkflowLibrary.ts`) and `normalizeAgents` (pipeline-type alias remap, from `useAgentLibrary.ts`) to whichever side(s) fulfilled — both move into this slice file as plain functions (no behavior change beyond dropping the `console.trace`, just relocation).
  - Only touches `workflows`/`agents`/`status`/`error`/`lastFetchedAt` — `skills`/`hooks` are untouched, since they're not network-backed.
- `builder.addCase(sessionEnded, () => initialState)` — the shared logout-reset (see "Cross-slice logout reset" above). No slice-specific `resetLibrary` action.
- Exported selectors: `selectWorkflows`, `selectAgents`, `selectSkills`, `selectHooks`, `selectLibraryStatus`, `selectLibraryError` — consumers never write `s.library.x` inline (see "Selector exports" above).

## Slice inventory — the rest of `store/api` (scaffold only)

Per-slice design rule: **only GET endpoints that return a reusable list/detail get the TTL `condition` guard**, built from the shared `createTtlCondition()` (mirroring `librarySlice`'s `fetchLibrary` — never a hand-rolled copy). Mutation thunks (`create*`/`update*`/`delete*`/`rename*`) never carry a `condition` — they always run — and their `fulfilled` reducer patches the corresponding cached list in place (e.g. `deleteRun` removes the matching id from `runs.items` instead of forcing a full refetch). Every thunk's error path uses `getErrorMessage()`, not a local ternary. `librarySlice`, `chatsSlice`, `runsSlice`, `userWorkflowsSlice`, `settingsSlice`, and `adminSlice` (the user/tenant-scoped ones) each add the one-line `builder.addCase(sessionEnded, () => initialState)`; `capabilitiesSlice`, `pptSlice`, `prototypeSlice`, `installSlice`, `healthSlice` (non-user-scoped catalogs/probes) and `handoffSlice`/`mcpSlice`/`filesSlice` (ephemeral single-action results) do not.

### Table

| API module | Slice | State shape | Thunks (✅ = TTL-cached read via `createTtlCondition`, ⚙️ = mutation/action, — = live/no-cache) | Resets on `sessionEnded`? |
|---|---|---|---|---|
| `auth.ts` | `authSlice` | `{ user: User \| null, status, error }` | `login` ⚙️, `register` ⚙️, `fetchMe` —, `logout` ⚙️ (unused — see "Cross-slice logout reset"), `changePassword` ⚙️. Also defines and exports the shared `sessionEnded` plain action. | n/a (it's the source of the reset) |
| `chats.ts` | `chatsSlice` | `{ sessions: ChatSession[], status, error, lastFetchedAt, active: ChatDetail \| null, activeStatus, activeError }` (types from `store/api/chats.ts`, **not** `types/index.ts` — see the type-duplication note above) | `fetchChats` ✅, `fetchChat(id)` — (always fresh, it's an open conversation), `createChat` ⚙️ (prepends to `sessions`), `addMessage` ⚙️ (appends to `active.messages`), `deleteChat` ⚙️ (removes from `sessions`) | ✅ |
| `capabilities.ts` | `capabilitiesSlice` | `{ data: CapabilitiesPalette \| null, status, error, lastFetchedAt }` | `fetchCapabilities` ✅ | — |
| `settings.ts` | `settingsSlice` | `{ githubPat, apiKeys[], preferences, constitution }`, each with its own `status`/`error`/`lastFetchedAt` | `fetchGithubPat` ✅, `setGithubPat` ⚙️, `deleteGithubPat` ⚙️, `fetchApiKeys` ✅, `createApiKey` ⚙️, `deleteApiKey` ⚙️, `fetchPreferences` ✅, `updatePreferences` ⚙️, `fetchConstitution` ✅, `updateConstitution` ⚙️, `deleteConstitution` ⚙️ — all four ✅ reads share the *same* `createTtlCondition` helper, parameterized per sub-resource selector, not four copy-pasted conditions | ✅ |
| `handoff.ts` | `handoffSlice` | `{ current: HandoffDetail \| null, status, error }` | `receiveHandoff` ⚙️, `getHandoff(token)` —, `startHandoff(token)` ⚙️ | — |
| `mcp.ts` | `mcpSlice` | `{ lastResult: JsonRpcResponse \| null, status, error }` | `callMcp(request, apiKey)` — (JSON-RPC call, not cacheable by nature) | — |
| `install.ts` | `installSlice` | `{ combined, command, script }` (strings), shared `status`/`error` | `fetchCombined` ✅, `fetchCommand` ✅, `fetchScript` ✅ (static installer text, safe to cache) | — |
| `files.ts` | `filesSlice` | `{ lastExtraction: ExtractTextResponse \| null, status, error }` | `extractText(file)` ⚙️ (a File upload isn't a cache key we can compare on later mounts) | — |
| `ppt.ts` | `pptSlice` | `{ templates: PptTemplateSummary[], status, error, lastFetchedAt, selected: PptTemplateDetail \| null, selectedStatus, selectedError }` | `fetchTemplates` ✅, `fetchTemplate(id)` ✅. `previewUrl`/`thumbnailUrl` stay as plain exported functions (URL builders, not async) — not thunks. | — |
| `prototype.ts` | `prototypeSlice` | `{ templates[], templatesStatus/.../lastFetchedAt, designSystems[], designSystemsStatus/.../lastFetchedAt, selectedTemplate, selectedDesignSystem }` | `fetchTemplates` ✅, `fetchTemplate(id)` ✅, `fetchDesignSystems` ✅, `fetchDesignSystem(id)` ✅, `fetchUrl(url)` — (`prototype.run`'s NDJSON streaming generator is **not** modeled as a thunk at all — see exceptions below) | — |
| `runs.ts` | `runsSlice` | `{ items: WorkflowRun[], status, error, lastFetchedAt, detail, chainContext, artifacts, events, hookRuns, family }` — `WorkflowRun` here is `store/api/runs.ts`'s raw shape, deliberately **not** unified with `types/index.ts`'s normalized `WorkflowRun` (see type-duplication note); each detail field has its own small `status`/`error`, keyed to "whatever run is currently open," not a per-id cache map | `fetchRuns(options?)` ✅ *(TTL applies only to the no-args/default-filter call — see caveat below)*, `fetchRun(id)` —, `deleteRun(id)` ⚙️ (removes from `items`), `exportPptx` ⚙️, `fetchChainContext(id)` —, `fetchArtifacts(id, opts?)` —, `fetchEvents(id, after?)` — (polling endpoint, never cached), `fetchHookRuns(id)` —, `fetchFamily(id)` — | ✅ |
| `userWorkflows.ts` | `userWorkflowsSlice` | `{ items: UserWorkflowSummary[], status, error, lastFetchedAt }` | `fetchUserWorkflows` ✅, `createUserWorkflow` ⚙️, `renameUserWorkflow` ⚙️, `deleteUserWorkflow` ⚙️ | ✅ |
| `admin.ts` | `adminSlice` | `{ users: AdminUser[], status, error, lastFetchedAt }` | `fetchUsers` ✅, `updateUserTier` ⚙️, `createUser` ⚙️, `deleteUser` ⚙️ | ✅ |
| `health.ts` | `healthSlice` | `{ response: HealthResponse \| null, status, error }` | `fetchHealth` — (a health probe is the one read endpoint that must **never** be TTL-cached — caching it would defeat the entire point of calling it) | — |

### Explicit exceptions to "every GET gets a TTL condition"

- **`runsApi.list(options)`**: the TTL guard only has one cache slot (`lastFetchedAt` on the slice), but the real endpoint takes `{ type, limit, offset, status_filter }`. Caching "the last call" and serving it back for a *different* filter combination would silently show the wrong run history. Scaffolded behavior: `condition` (still built from `createTtlCondition`, called only when `fetchRuns` is invoked with **no args** / the same default args as the cached call) — any call with filter args skips the `condition` check and always executes. Called out explicitly so a future call site doesn't assume filtered queries are cached when they aren't.
- **`prototypeApi.run`**: an `AsyncGenerator` yielding NDJSON chunks over a raw `fetch` stream (bypassing axios entirely, per the source comment). It doesn't fit `createAsyncThunk`'s single-resolved-value model and isn't state to cache — it stays outside Redux entirely, called directly from whatever component drives the run, the same way `RunConnectionProvider`'s SSE stream stays outside Redux today. `prototypeSlice` covers everything else in that file (templates, design systems, url fetch).
- **`mcpApi.call` / `handoffApi.receive`**: both take a Flowin API key as an explicit argument rather than using the shared JWT interceptor. The thunks pass that argument straight through — no change to the auth model, just wrapped in `createAsyncThunk` for consistency of shape.

## `store.ts`

```ts
import { librarySlice } from './slices/librarySlice';
import { authSlice } from './slices/authSlice';
import { chatsSlice } from './slices/chatsSlice';
import { capabilitiesSlice } from './slices/capabilitiesSlice';
import { settingsSlice } from './slices/settingsSlice';
import { handoffSlice } from './slices/handoffSlice';
import { mcpSlice } from './slices/mcpSlice';
import { installSlice } from './slices/installSlice';
import { filesSlice } from './slices/filesSlice';
import { pptSlice } from './slices/pptSlice';
import { prototypeSlice } from './slices/prototypeSlice';
import { runsSlice } from './slices/runsSlice';
import { userWorkflowsSlice } from './slices/userWorkflowsSlice';
import { adminSlice } from './slices/adminSlice';
import { healthSlice } from './slices/healthSlice';

export const makeStore = () =>
  configureStore({
    reducer: {
      [librarySlice.name]: librarySlice.reducer,
      [authSlice.name]: authSlice.reducer,
      [chatsSlice.name]: chatsSlice.reducer,
      [capabilitiesSlice.name]: capabilitiesSlice.reducer,
      [settingsSlice.name]: settingsSlice.reducer,
      [handoffSlice.name]: handoffSlice.reducer,
      [mcpSlice.name]: mcpSlice.reducer,
      [installSlice.name]: installSlice.reducer,
      [filesSlice.name]: filesSlice.reducer,
      [pptSlice.name]: pptSlice.reducer,
      [prototypeSlice.name]: prototypeSlice.reducer,
      [runsSlice.name]: runsSlice.reducer,
      [userWorkflowsSlice.name]: userWorkflowsSlice.reducer,
      [adminSlice.name]: adminSlice.reducer,
      [healthSlice.name]: healthSlice.reducer,
    },
  });

export type AppStore = ReturnType<typeof makeStore>;
export type RootState = ReturnType<AppStore['getState']>;
export type AppDispatch = AppStore['dispatch'];
```

Using `[slice.name]: slice.reducer` (RTK's `createSlice` return value carries its own `name`) instead of re-typing each reducer key as a string literal is one more place duplication was designed out: the slice's own `name: 'library'` passed to `createSlice({ name: 'library', ... })` is the single source of truth for its reducer key, its action-type prefix (`'library/fetch'`), *and* its `RootState` key — never three independently-typed strings that could drift.

No module-level `store` export (see Audit finding #1) — every consumer (the app's `StoreProvider`, and unit tests) calls `makeStore()` to get its own instance. Typed hooks (`useAppDispatch`, `useAppSelector`) live in `store/hooks.ts`, standard RTK convention.

## Wiring into the app shell

`src/app/layout.tsx` is a server component today (no `"use client"`), wrapping children in `SkillsHooksProvider` + `RunConnectionProvider` (both client components). Add a `StoreProvider` client component alongside them:

```tsx
// src/providers/StoreProvider.tsx
"use client";
export function StoreProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<AppStore | null>(null);
  if (!storeRef.current) storeRef.current = makeStore();
  return <Provider store={storeRef.current}>{children}</Provider>;
}
```

(`useRef` lazy-init, not a module-level `store` export — see Audit finding #1. This is required, not optional, for correctness on the server.)

Mount order in `layout.tsx` (outermost so everything — including auth pages — has store access):

```tsx
<StoreProvider>
  <SkillsHooksProvider>
    <RunConnectionProvider>{children}</RunConnectionProvider>
  </SkillsHooksProvider>
</StoreProvider>
```

### Preload trigger

The actual "home" surface after login is `/dashboard` (`src/app/dashboard/page.tsx`, the `DashboardLayout` shell) — `/` just redirects to `/login`. Add a preload effect at the top of the dashboard page's existing auth-resolution block (it already has a `mounted`/`token`/`isAuthenticated` effect at line ~77):

```ts
const dispatch = useAppDispatch();
useEffect(() => {
  if (isAuthenticated) dispatch(fetchLibrary());
}, [isAuthenticated, dispatch]);
```

This fires once per session-start (and again only after the 10-minute TTL lapses on a later dashboard remount, or immediately after a logout→login cycle since `sessionEnded` clears the TTL guard — Audit finding #2), not on every Library-page visit. `skills`/`hooks` need no preload call — they're populated at store creation as part of `initialState`.

The logout handler must also dispatch `sessionEnded()` before navigating to `/login` (Audit finding #2):

```ts
const handleLogout = useCallback(async () => {
  await logout(getToken() ?? "");
  dispatch(sessionEnded());
  router.replace("/login");
}, [router, dispatch]);
```

## Consumer migration

### `useAgentLibrary.ts` / `useWorkflowLibrary.ts`

Rewrite both as thin selector hooks over the store instead of independent fetchers, keeping their exported shapes (`{ workflows, agents, loading, error }` / `{ workflows, loading, error }`) unchanged so `LibraryPage.tsx` and `AgentLibrary.tsx` need **zero** changes to their consumption code:

```ts
// useWorkflowLibrary.ts
import { fetchLibrary, selectWorkflows, selectLibraryStatus, selectLibraryError } from '@/store/slices/librarySlice';

export function useWorkflowLibrary(): UseWorkflowLibraryResult {
  const dispatch = useAppDispatch();
  const workflows = useAppSelector(selectWorkflows);
  const status = useAppSelector(selectLibraryStatus);
  const error = useAppSelector(selectLibraryError);
  useEffect(() => { dispatch(fetchLibrary()); }, [dispatch]);
  return { workflows, loading: status === 'loading' || status === 'idle', error };
}

// useAgentLibrary.ts
import { selectAgents } from '@/store/slices/librarySlice';

export function useAgentLibrary(): UseAgentLibraryResult {
  const { workflows, loading, error } = useWorkflowLibrary(); // dispatch already covered
  const agents = useAppSelector(selectAgents);
  return { workflows, agents, loading, error };
}
```

Note the exported selectors rather than inlined `useAppSelector(s => s.library.x)` (see "Selector exports" above). Because `fetchLibrary`'s `condition` is the sole TTL/in-flight guard (Audit finding #4), dispatching it from both hooks (as happens today when `useAgentLibrary` mounts `useWorkflowLibrary`, and again independently from `AgentLibrary.tsx`'s always-mounted `useAgentLibrary()` call) is safe — every call after the first in a given staleness window is a no-op, verified manually per the Testing plan rather than assumed.

Drop the `console.trace('normalizeAgents', ...)` left in `normalizeAgents` (`useAgentLibrary.ts:27`) during the move — it's debug scaffolding, not something to carry into the slice.

### `LibraryPage.tsx`, `AgentLibrary.tsx`

No changes required for agents/workflows (same hook contract). `LibraryPage.tsx` swaps its direct `SKILLS`/`HOOKS` imports for `useAppSelector(selectSkills)` / `useAppSelector(selectHooks)` — now that skills/hooks live in the same slice as agents/workflows, this is the natural single-source read and is included in scope (not deferred). `AgentLibrary.tsx` doesn't reference `SKILLS`/`HOOKS` today, so no change there.

## Cache/TTL behavior summary

- First dashboard load after login (or hard refresh): `status: 'idle'` → fetch runs, spinner shows once.
- Library page visited within 10 minutes of that fetch: store already has data, `status: 'succeeded'` → hooks return instantly, no spinner, no network call.
- Library page visited after 10 minutes: `fetchLibrary`'s `condition` (via `createTtlCondition`) sees the cache is stale → refetches transparently (existing data stays visible until the new data lands, since we don't clear `agents`/`workflows` on refetch start — only `status` flips to `'loading'`).
- Logout → different (or same) user logs back in on the same tab: `sessionEnded` clears `status`/`lastFetchedAt` on every slice listening for it, so the dashboard's next preload effect fetches fresh data unconditionally rather than serving the previous session's cache (Audit finding #2).
- Partial failure (one of workflows/agents fails, not both): the failed side's `error` is set (via `getErrorMessage()`) and its array is left as whatever it was before (empty on first load, previous data on a background refresh); the succeeded side updates normally. The whole thunk is never "failed" just because one of the two calls was (Audit finding #3).
- Full failure: `status: 'failed'`, `error` set, `lastFetchedAt` left untouched so the *next* mount retries immediately rather than waiting out the TTL on a failure.

## Testing plan

- Unit test `store/types.ts`'s shared helpers directly and once: `isStale` boundary conditions, `createTtlCondition` (fresh → skipped, stale → refetched, `loading` → skipped, `force: true` → always runs), `getErrorMessage` (Error vs. non-Error input). Because every slice's TTL logic is this one function, testing it once here is what makes testing each individual slice's `condition` unnecessary — the slice tests below only need to confirm they *wired* the helper in, not re-verify its branches.
- Unit test `librarySlice` reducer/thunk using a fresh `makeStore()` per test (never a shared instance, per Audit finding #1):
  - `fetchLibrary` wires `createTtlCondition` correctly (one fresh-vs-stale round trip is enough, given the helper itself is tested above).
  - Partial-failure handling: one of `Promise.allSettled`'s two results rejected → only that side's data/error updates, the other side's existing data survives (Audit finding #3).
  - `sessionEnded`: resets `agents`/`workflows`/`status`/`lastFetchedAt` to `initialState`, leaves `skills`/`hooks` untouched (Audit finding #2).
  - Normalization functions (reuse any existing test fixtures for `normalizeAgents`/`normalizeWorkflows` if present, else add minimal ones).
- Update/extend existing hook-level tests (check for `useAgentLibrary`/`useWorkflowLibrary` test files — none found in current tree, so these would be new) to assert the hooks read from a mocked store rather than mocking `agentsApi`/`workflowsApi` directly.
- Lighter unit tests for each scaffold slice: reducer shape + that its ✅ thunks pass the right selector into `createTtlCondition` and its ⚙️ thunks patch state correctly on `fulfilled`, against a mocked `store/api` module. No manual UI verification needed (nothing renders from them yet) — a `tsc --noEmit`/build pass plus these unit tests is the acceptance bar.
- Manual verification for the wired `librarySlice` path only (per repo convention — no UI test harness run automatically):
  - Start dev server, log in, confirm Library page shows agents/workflows.
  - Open the Agent drawer from the workflow builder and confirm no duplicate network call (Network tab) — the concrete check for the "safe to dispatch from multiple mounted hooks" claim in Consumer migration.
  - Wait/force TTL expiry (temporarily lower `DEFAULT_TTL_MS` locally) to confirm refetch happens.
  - Log out, log in as a different (or the same) user, confirm the Library page re-fetches rather than flashing stale data from the previous session (Audit finding #2) — check the Network tab fires a request immediately post-login even though the previous fetch was well within 10 minutes.
  - Simulate one endpoint failing (e.g. temporarily point `workflowsApi.list()` at a bad path) and confirm agents still load (Audit finding #3).

## Open questions for the user

1. **Stale-while-revalidate display**: while a background refetch is in flight after TTL expiry, should the UI keep showing the old list silently (recommended — avoids a jarring reload every 10 min) or show the loading state again? Plan above assumes silent background refresh.

## File-by-file change list

**Wired (behavior changes):**

| File | Change |
|---|---|
| `frontend/package.json` | add `@reduxjs/toolkit`, `react-redux` |
| `frontend/src/store/store.ts` | new — `makeStore()` factory combining all 15 reducers (14 domain slices + auth), `RootState`, `AppDispatch`, `AppStore` (no module-level `store` export) |
| `frontend/src/store/hooks.ts` | new — typed `useAppDispatch`/`useAppSelector` |
| `frontend/src/store/types.ts` | new — shared `AsyncStatus`, `DEFAULT_TTL_MS`, `isStale()`, `createTtlCondition()`, `getErrorMessage()` |
| `frontend/src/store/slices/librarySlice.ts` | new — agents+workflows+skills+hooks in one `library` state; `fetchLibrary` thunk built on `createTtlCondition` + `Promise.allSettled`; listens for `sessionEnded`; exported selectors; normalization (moved from hooks) |
| `frontend/src/store/slices/authSlice.ts` | new — scaffold (see below) **plus** the shared `sessionEnded` action every user-scoped slice listens for |
| `frontend/src/providers/StoreProvider.tsx` | new — client component, `useRef`-lazy `makeStore()`, wraps `<Provider store={...}>` |
| `frontend/src/app/layout.tsx` | wrap children in `<StoreProvider>` (outermost) |
| `frontend/src/app/dashboard/page.tsx` | dispatch `fetchLibrary()` once `isAuthenticated`; dispatch `sessionEnded()` in `handleLogout` before `router.replace` |
| `frontend/src/hooks/useWorkflowLibrary.ts` | rewrite as selector hook over `library` slice (imported selectors, not inlined paths) |
| `frontend/src/hooks/useAgentLibrary.ts` | rewrite as selector hook over `library` slice; drop `console.trace` |
| `frontend/src/components/library/LibraryPage.tsx` | swap `SKILLS`/`HOOKS` static imports for `useAppSelector(selectSkills/selectHooks)` |
| `frontend/src/components/workflow/AgentLibrary.tsx` | no required change |

**Scaffold only (new files, zero other existing call sites touched):**

| File |
|---|
| `frontend/src/store/slices/chatsSlice.ts` |
| `frontend/src/store/slices/capabilitiesSlice.ts` |
| `frontend/src/store/slices/settingsSlice.ts` |
| `frontend/src/store/slices/handoffSlice.ts` |
| `frontend/src/store/slices/mcpSlice.ts` |
| `frontend/src/store/slices/installSlice.ts` |
| `frontend/src/store/slices/filesSlice.ts` |
| `frontend/src/store/slices/pptSlice.ts` |
| `frontend/src/store/slices/prototypeSlice.ts` |
| `frontend/src/store/slices/runsSlice.ts` |
| `frontend/src/store/slices/userWorkflowsSlice.ts` |
| `frontend/src/store/slices/adminSlice.ts` |
| `frontend/src/store/slices/healthSlice.ts` |

(`authSlice.ts` is listed under "Wired" above because it's the origin of `sessionEnded`, even though its own thunks — `login`/`register`/`fetchMe`/`logout`/`changePassword` — are scaffold-only like the rest, unused by any existing call site.)

## Rollout order

1. Add deps, create `store/types.ts` (shared helpers) first — everything else depends on it.
2. Create `store/slices/authSlice.ts`, including the exported `sessionEnded` action — needed by every other user-scoped slice next.
3. Create `store/slices/librarySlice.ts` (`fetchLibrary`, `sessionEnded` listener, selectors) and `store/hooks.ts`.
4. Scaffold the remaining 12 slices (`chatsSlice` … `healthSlice`) per the inventory above, each importing only its own `store/api/*` module plus `store/types.ts` (and `authSlice`'s `sessionEnded` for the six that reset on logout).
5. Create `store/store.ts` combining all 15 reducers via `makeStore()`.
6. Wire `StoreProvider` (ref-lazy `makeStore()`) into `layout.tsx`. This makes the whole store reachable app-wide, including the 13 unused scaffold slices — that's expected and fine, an unused reducer costs nothing at runtime.
7. Add dashboard preload dispatch (`fetchLibrary()` on `isAuthenticated`) and the `sessionEnded()` dispatch in `handleLogout` — the *only* two call-site changes outside the store files themselves.
8. Rewrite `useWorkflowLibrary`/`useAgentLibrary` to read from the store via exported selectors; verify `LibraryPage`/`AgentLibrary` still work for agents/workflows.
9. Swap `LibraryPage.tsx`'s `SKILLS`/`HOOKS` imports for store selectors.
10. Unit test `store/types.ts`'s shared helpers once, `librarySlice` end-to-end, and each scaffold slice lightly (reducer shape + thunk wiring) per the Testing plan.
11. Manual smoke test per Testing plan — including the logout/re-login and partial-failure checks, not just the happy path. Scaffold slices need no manual UI verification — a `tsc --noEmit`/build pass plus their unit tests is the acceptance bar for those.
