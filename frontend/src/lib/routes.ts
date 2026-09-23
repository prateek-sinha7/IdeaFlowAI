/**
 * Typed path builders for all routes in the app.
 * Every route is defined here; no hand-written route literals elsewhere.
 * Query params use a shared URLSearchParams helper to ensure clean URLs.
 */

function buildQueryString(params?: Record<string, string | number | boolean | undefined>): string {
  if (!params) return '';

  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      sp.set(key, String(value));
    }
  }

  const qs = sp.toString();
  return qs ? `?${qs}` : '';
}

type LibraryParams = {
  tab?: 'agents' | 'skills' | 'hooks';
  category?: string;
  search?: string;
};

// Shared by the /library list route and the three item-detail routes below:
// `agents` is the default tab and `all` the default category, so neither is
// emitted.
function libraryQuery(params?: LibraryParams): string {
  return buildQueryString({
    tab: params?.tab === 'agents' ? undefined : params?.tab,
    category: params?.category === 'all' ? undefined : params?.category,
    search: params?.search,
  });
}

export const routes = {
  // ─────────────────────────────────────────────────────────────
  // Auth & root
  // ─────────────────────────────────────────────────────────────
  // ISS-322: `redirect` carries the protected route a mid-session expiry bounced
  // the user off (api.ts's handleSessionExpiry), so re-login returns there
  // instead of the /dashboard default. It goes through buildQueryString like
  // every other param, so a target carrying its own query string
  // (/analytics?range=7d) is percent-encoded into ONE value rather than leaking
  // out as top-level /login params.
  login: (params?: { expired?: boolean; redirect?: string }): string => {
    return `/login${buildQueryString(params)}`;
  },

  register: (): string => '/register',

  // ─────────────────────────────────────────────────────────────
  // Home & creation
  // ─────────────────────────────────────────────────────────────
  home: (): string => '/dashboard',

  dashboard: (): string => '/dashboard',

  create: (): string => '/create',

  createPpt: (): string => '/create/ppt',

  createPrototype: (): string => '/create/prototype',

  createApp: (): string => '/create/app',

  createUserStories: (): string => '/create/user-stories',

  workflowNew: (): string => '/workflows/new',

  // Legacy wizard page (`app/workflow/create/page.tsx`). Not a MainView —
  // `/create/ppt`, `/create/prototype`, and the ppt/prototype branch of
  // `/workflows/{id}/run` redirect here today, matching the pre-existing
  // click-driven behavior in DashboardLayout.tsx. Retired by FR-007/T17 in
  // favor of `createPpt`/`createPrototype` above; kept as a builder (not a
  // hand-written literal) until that redirect lands.
  workflowCreateLegacy: (mode: string): string => `/workflow/create${buildQueryString({ mode })}`,

  // ─────────────────────────────────────────────────────────────
  // Runs
  // ─────────────────────────────────────────────────────────────
  runHistory: (params?: { type?: string; sort?: string }): string => {
    return `/runs${buildQueryString(params)}`;
  },

  // ISS-230: every run-tab route takes the pinned version as an OPTIONAL
  // second argument, so a tab switch made while `/runs/{id}/versions/{v}` is
  // on screen keeps the pin instead of collapsing back to the root run.
  // Omitting it yields the un-versioned route these builders always returned.
  runDetail: (id: string, version?: string): string =>
    version ? `/runs/${id}/versions/${version}` : `/runs/${id}`,

  runSteps: (id: string, version?: string): string =>
    version ? `/runs/${id}/versions/${version}/steps` : `/runs/${id}/steps`,

  // ISS-386: add version? to match every other run-tab builder and close the
  // builder/parser asymmetry. Parser already returns {version} for this screen
  // (parseViewPath:339); now the builder can also PRODUCE the versioned form.
  runStepsAgent: (id: string, agentId: string, version?: string): string =>
    version
      ? `/runs/${id}/versions/${version}/steps/${agentId}`
      : `/runs/${id}/steps/${agentId}`,

  runFiles: (id: string, version?: string): string =>
    version ? `/runs/${id}/versions/${version}/files` : `/runs/${id}/files`,

  runWorkspace: (id: string, version?: string): string =>
    version ? `/runs/${id}/versions/${version}/workspace` : `/runs/${id}/workspace`,

  runAudit: (id: string, version?: string): string =>
    version ? `/runs/${id}/versions/${version}/audit` : `/runs/${id}/audit`,

  runStream: (id: string): string => `/runs/${id}/stream`,

  runVersion: (id: string, v: string): string => `/runs/${id}/versions/${v}`,

  runPreviewFull: (id: string): string => `/runs/${id}/preview/full`,

  // ─────────────────────────────────────────────────────────────
  // Saved workflows
  // ─────────────────────────────────────────────────────────────
  workflows: (): string => '/workflows',

  workflow: (id: string): string => `/workflows/${id}`,

  workflowEdit: (id: string): string => `/workflows/${id}/edit`,
  /** A BUILT-IN workflow on the full canvas: explore, change, Run — Save makes a copy.
   *  `workflowEdit` is the saved-row counterpart, whose Save overwrites. */
  workflowCanvas: (pipelineType: string): string =>
    `/workflows/${encodeURIComponent(pipelineType)}/canvas`,

  workflowRun: (id: string): string => `/workflows/${id}/run`,

  // ─────────────────────────────────────────────────────────────
  // Library
  // ─────────────────────────────────────────────────────────────
  // Post-close amendment (015-frontend-routing, 2026-08-21): the 3 list
  // screens (agents/skills/hooks) collapsed from 3 path segments into ONE
  // path with the tab as a query param — see spec.md Clarifications,
  // Session 2026-08-21. Item-DETAIL routes below are unaffected.
  library: (params?: LibraryParams): string => `/library${libraryQuery(params)}`,

  // ISS-360/592/593/594: an item-detail navigation changes the [...view]
  // catch-all's own segments, which remounts the page (see that file's T6
  // comment) and reinitializes every LibraryPage state hook. The list's
  // tab/category/search ride along on the detail URL so the fresh mount can
  // seed them straight back off it.
  libraryAgent: (slug: string, params?: LibraryParams): string =>
    `/library/agents/${slug}${libraryQuery(params)}`,

  librarySkill: (slug: string, params?: LibraryParams): string =>
    `/library/skills/${slug}${libraryQuery(params)}`,

  libraryHook: (slug: string, params?: LibraryParams): string =>
    `/library/hooks/${slug}${libraryQuery(params)}`,

  // ─────────────────────────────────────────────────────────────
  // Settings, analytics, admin
  // ─────────────────────────────────────────────────────────────
  settingsProfile: (): string => '/settings/profile',

  settingsAiModel: (): string => '/settings/ai-model',

  settingsUsage: (): string => '/settings/usage',

  settingsConstitution: (): string => '/settings/constitution',

  // The MFA/two-factor controls that used to live at a standalone
  // /settings/security PAGE are now a tab on this surface. The page is gone
  // (dev's change, kept); the URL stays so the tab is addressable exactly
  // like the other four — /settings/{tab} maps to a tab, uniformly.
  settingsSecurity: (): string => '/settings/security',

  analytics: (params?: { range?: string; pipeline?: string }): string => {
    return `/analytics${buildQueryString(params)}`;
  },

  // Intentionally unreachable dead code: static app/admin/page.tsx takes precedence over [...view] catch-all for /admin path; kept for routes.ts documentation.
  admin: (): string => '/admin',
};

export type Routes = typeof routes;

/**
 * Parsed view descriptor — discriminated union of all navigable screens.
 * This is the inverse of the routes.* builders.
 */
export type ParsedView =
  | { screen: 'login'; expired?: boolean }
  | { screen: 'register' }
  | { screen: 'home' }
  | { screen: 'create' }
  | { screen: 'create-ppt' }
  | { screen: 'create-prototype' }
  | { screen: 'create-app' }
  | { screen: 'create-user-stories' }
  // Any other /create/{type}: a catalog-driven workflow with no hand-written
  // route of its own. Carries the raw pipeline_type so a COLD load can open the
  // right launch panel — see the parser note below.
  | { screen: 'create-workflow'; pipelineType: string }
  // /workflows/{pipelineType}/canvas — a BUILT-IN workflow opened on the full canvas.
  // Distinct from `workflow-edit` ({uuid}/edit), which targets a saved row the user
  // owns and whose Save overwrites it. A built-in is a workflow.yaml on disk: there is
  // no row to write back to, so its canvas is explore-and-copy — Run works, Save
  // creates a NEW user workflow.
  | { screen: 'workflow-canvas'; pipelineType: string }
  | { screen: 'workflow-new' }
  | { screen: 'run-history'; type?: string; sort?: string }
  // ISS-230: `version` is the `/versions/{v}` pin the path carries, present on
  // every run tab that can be reached while pinned (`/runs/{id}/versions/{v}/{tab}`)
  // and undefined on the plain, un-pinned form of the same route.
  | { screen: 'run-detail'; runId: string; version?: string }
  | { screen: 'run-steps'; runId: string; version?: string }
  | { screen: 'run-steps-agent'; runId: string; agentId: string; version?: string }
  | { screen: 'run-files'; runId: string; version?: string }
  | { screen: 'run-workspace'; runId: string; version?: string }
  | { screen: 'run-audit'; runId: string; version?: string }
  | { screen: 'run-stream'; runId: string }
  | { screen: 'run-version'; runId: string; version: string }
  | { screen: 'run-preview-full'; runId: string }
  | { screen: 'workflows' }
  | { screen: 'workflow'; workflowId: string }
  | { screen: 'workflow-edit'; workflowId: string }
  | { screen: 'workflow-run'; workflowId: string }
  | { screen: 'library'; tab?: 'agents' | 'skills' | 'hooks'; category?: string }
  | { screen: 'library-agent'; slug: string }
  | { screen: 'library-skill'; slug: string }
  | { screen: 'library-hook'; slug: string }
  | { screen: 'settings-profile' }
  | { screen: 'settings-ai-model' }
  | { screen: 'settings-usage' }
  | { screen: 'settings-constitution' }
  | { screen: 'settings-security' }
  | { screen: 'analytics'; range?: string; pipeline?: string }
  | { screen: 'admin' }
  | { screen: 'unknown' };

/**
 * Parse a URL path (as segments from [[...view]]) into a descriptor.
 * Returns a discriminated union indicating which screen was matched and what params it has.
 * Unrecognized paths return { screen: "unknown" }.
 */
export function parseViewPath(segments: string[] | undefined): ParsedView {
  // Handle undefined or empty segments — both resolve to home
  if (!segments || segments.length === 0) {
    return { screen: 'home' };
  }

  const head = segments[0];

  // ─────────────────────────────────────────────────────────────
  // Auth & root
  // ─────────────────────────────────────────────────────────────
  if (head === 'login') {
    // Extract query params from the URL if they exist
    // Note: parseViewPath only receives segments, not query params directly
    // Query params must be handled at the call site using useSearchParams
    return { screen: 'login' };
  }

  // ISS-238: the `segments.length === 1` guard is load-bearing. Without it any
  // /register/<sub-path> also resolved to { screen: 'register' }, and since
  // [...view]/page.tsx has no branch for that screen it fell through to the
  // default dashboard render instead of the `unknown` -> notFound() gate below.
  if (head === 'register' && segments.length === 1) {
    return { screen: 'register' };
  }

  // ─────────────────────────────────────────────────────────────
  // Home & creation
  // ─────────────────────────────────────────────────────────────
  if (head === 'dashboard') {
    return { screen: 'home' };
  }

  if (head === 'create') {
    if (segments.length === 1) {
      return { screen: 'create' };
    }

    const mode = segments[1];
    if (mode === 'ppt') return { screen: 'create-ppt' };
    if (mode === 'prototype') return { screen: 'create-prototype' };
    if (mode === 'app') return { screen: 'create-app' };
    if (mode === 'user-stories') return { screen: 'create-user-stories' };

    // Everything else is a live-catalog workflow (any manifest with
    // user_launchable: true and is_beta: false gets a card, so this set is
    // open-ended and cannot be enumerated here). It used to fall through to
    // 'unknown', which was fine for the CLICK path — DashboardLayout sets the
    // view optimistically before pushing the URL, and 'unknown' produces no
    // initialMainView to stomp it (see createRouteForType's note). But a COLD
    // load of the same URL — typed, refreshed, or shared — had no in-memory
    // state and nothing to render from, so /create/ex_A2_branch failed. Carry
    // the type instead so the cold path can resolve the same launch panel.
    return { screen: 'create-workflow', pipelineType: decodeURIComponent(mode) };
  }

  if (head === 'workflows') {
    if (segments.length === 1) {
      return { screen: 'workflows' };
    }

    const workflowSegment = segments[1];
    if (workflowSegment === 'new') {
      return { screen: 'workflow-new' };
    }

    // /workflows/{id} or /workflows/{id}/edit or /workflows/{id}/run
    const workflowId = workflowSegment;
    if (segments.length === 2) {
      return { screen: 'workflow', workflowId };
    }

    const action = segments[2];
    if (action === 'canvas') {
      // The segment is a pipeline_type (a manifest directory name), not a saved-row
      // UUID. The two can never collide: a UUID is not a legal directory name here,
      // and `/{uuid}/canvas` is not a route anyone builds. No hardcoded workflow list
      // is needed to tell them apart (SC-001) — the URL's own verb does it.
      return { screen: 'workflow-canvas', pipelineType: decodeURIComponent(workflowSegment) };
    }
    if (action === 'edit') {
      return { screen: 'workflow-edit', workflowId };
    }
    if (action === 'run') {
      return { screen: 'workflow-run', workflowId };
    }

    return { screen: 'unknown' };
  }

  // ─────────────────────────────────────────────────────────────
  // Runs
  // ─────────────────────────────────────────────────────────────
  if (head === 'runs') {
    if (segments.length === 1) {
      return { screen: 'run-history' };
    }

    const runId = segments[1];

    // /runs/{id}
    if (segments.length === 2) {
      return { screen: 'run-detail', runId };
    }

    // ISS-230: a `/versions/{v}` pin sits BETWEEN the run id and the tab
    // (`/runs/{id}/versions/{v}/{tab}`) so a tab switch can carry it. Lift it
    // out here and parse what follows exactly as the un-pinned form, rather
    // than duplicating every tab arm below. A bare pin with no tab after it
    // stays its own screen (`run-version`), unchanged.
    let version: string | undefined;
    let tail = segments;
    if (segments[2] === 'versions') {
      version = segments[3];
      if (segments.length <= 4) {
        return { screen: 'run-version', runId, version };
      }
      tail = [segments[0], runId, ...segments.slice(4)];
    }

    const subpath = tail[2];

    // /runs/{id}/steps
    if (subpath === 'steps') {
      if (tail.length === 3) {
        return { screen: 'run-steps', runId, version };
      }

      // /runs/{id}/steps/{agentId}
      const agentId = tail[3];
      return { screen: 'run-steps-agent', runId, agentId, version };
    }

    // /runs/{id}/files
    if (subpath === 'files') {
      return { screen: 'run-files', runId, version };
    }

    // /runs/{id}/workspace
    if (subpath === 'workspace') {
      return { screen: 'run-workspace', runId, version };
    }

    // /runs/{id}/audit
    if (subpath === 'audit') {
      return { screen: 'run-audit', runId, version };
    }

    // /runs/{id}/stream
    if (subpath === 'stream') {
      return { screen: 'run-stream', runId };
    }

    // /runs/{id}/preview/full
    if (subpath === 'preview' && tail[3] === 'full') {
      return { screen: 'run-preview-full', runId };
    }

    return { screen: 'unknown' };
  }

  // ─────────────────────────────────────────────────────────────
  // Library
  // ─────────────────────────────────────────────────────────────
  if (head === 'library') {
    // Post-close amendment (2026-08-21): a bare /library (plus ?tab=/?category=,
    // read at the call site via useSearchParams — parseViewPath only sees path
    // segments, matching every other query-bearing screen in this file, e.g.
    // login/runHistory/analytics above) is now the unified list screen itself,
    // not an unknown/redirect stub.
    if (segments.length === 1) {
      return { screen: 'library' };
    }

    const type = segments[1];

    // ISS-572: the legacy 2-segment list shape (/library/agents,
    // /library/skills, /library/hooks with no slug). next.config.ts's
    // redirects() sends these to /library server-side, but that rule only
    // runs for a full/document navigation — a client-side history transition
    // reaches this parser directly, so the destination screen is mirrored
    // here too. (The ?tab= half of the skills/hooks destinations is a query
    // param, which parseViewPath structurally never sees — same convention
    // as the bare /library case above.)
    if (segments.length === 2 && (type === 'agents' || type === 'skills' || type === 'hooks')) {
      return { screen: 'library' };
    }

    // Item-DETAIL routes only — unchanged from before this amendment.
    if (segments.length >= 3) {
      const slug = segments[2];
      if (type === 'agents') return { screen: 'library-agent', slug };
      if (type === 'skills') return { screen: 'library-skill', slug };
      if (type === 'hooks') return { screen: 'library-hook', slug };
    }

    return { screen: 'unknown' };
  }

  // ─────────────────────────────────────────────────────────────
  // Settings, analytics, admin
  // ─────────────────────────────────────────────────────────────
  if (head === 'settings') {
    if (segments.length === 1) {
      // ISS-339: /settings with no tab. next.config.ts's redirects() sends it
      // to /settings/profile server-side, but that rule only runs for a
      // full/document navigation — a client-side history transition reaches
      // this parser directly, so the same destination is mirrored here rather
      // than dead-ending at unknown -> 404.
      return { screen: 'settings-profile' };
    }

    const tab = segments[1];

    if (tab === 'profile') return { screen: 'settings-profile' };
    if (tab === 'ai-model') return { screen: 'settings-ai-model' };
    if (tab === 'usage') return { screen: 'settings-usage' };
    if (tab === 'constitution') return { screen: 'settings-constitution' };
    if (tab === 'security') return { screen: 'settings-security' };

    return { screen: 'unknown' };
  }

  // ISS-350: the same missing-depth-guard shape as ISS-238/register — matches
  // `segments[0] === 'analytics'` alone, so `/analytics/<sub-path>` resolved
  // to the real Analytics screen instead of the `unknown` -> notFound() gate.
  // Unlike register (which had no initialMainViewFor case), analytics DOES have
  // one, so the symptom is "renders the real page under a bogus URL" rather
  // than "renders the dashboard" — still a URL/content mismatch per ADR-0018.
  // Fix: add segments.length === 1 guard, same shape as register/create/workflows.
  if (head === 'analytics' && segments.length === 1) {
    return { screen: 'analytics' };
  }

  // Intentionally unreachable dead code: static app/admin/page.tsx takes precedence over [...view] catch-all for /admin path; kept for parseViewPath documentation.
  if (head === 'admin') {
    return { screen: 'admin' };
  }

  // ─────────────────────────────────────────────────────────────
  // Unrecognized
  // ─────────────────────────────────────────────────────────────
  return { screen: 'unknown' };
}

/**
 * Get a stable, distinct screen label for tracking and observability.
 * Returns the screen discriminator value — the canonical identifier for each view.
 */
export function screenLabel(parsed: ParsedView): string {
  return parsed.screen;
}
