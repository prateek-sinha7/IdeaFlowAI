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

export const routes = {
  // ─────────────────────────────────────────────────────────────
  // Auth & root
  // ─────────────────────────────────────────────────────────────
  login: (params?: { expired?: boolean }): string => {
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

  runDetail: (id: string): string => `/runs/${id}`,

  runSteps: (id: string): string => `/runs/${id}/steps`,

  runStepsAgent: (id: string, agentId: string): string =>
    `/runs/${id}/steps/${agentId}`,

  runFiles: (id: string): string => `/runs/${id}/files`,

  runAudit: (id: string): string => `/runs/${id}/audit`,

  runStream: (id: string): string => `/runs/${id}/stream`,

  runVersion: (id: string, v: string): string => `/runs/${id}/versions/${v}`,

  runPreviewFull: (id: string): string => `/runs/${id}/preview/full`,

  // ─────────────────────────────────────────────────────────────
  // Saved workflows
  // ─────────────────────────────────────────────────────────────
  workflows: (): string => '/workflows',

  workflow: (id: string): string => `/workflows/${id}`,

  workflowEdit: (id: string): string => `/workflows/${id}/edit`,

  workflowRun: (id: string): string => `/workflows/${id}/run`,

  // ─────────────────────────────────────────────────────────────
  // Library
  // ─────────────────────────────────────────────────────────────
  // Post-close amendment (015-frontend-routing, 2026-08-21): the 3 list
  // screens (agents/skills/hooks) collapsed from 3 path segments into ONE
  // path with the tab as a query param — see spec.md Clarifications,
  // Session 2026-08-21. Item-DETAIL routes below are unaffected.
  library: (params?: { tab?: 'agents' | 'skills' | 'hooks'; category?: string }): string => {
    const tab = params?.tab === 'agents' ? undefined : params?.tab;
    const category = params?.category === 'all' ? undefined : params?.category;
    return `/library${buildQueryString({ tab, category })}`;
  },

  libraryAgent: (slug: string): string => `/library/agents/${slug}`,

  librarySkill: (slug: string): string => `/library/skills/${slug}`,

  libraryHook: (slug: string): string => `/library/hooks/${slug}`,

  // ─────────────────────────────────────────────────────────────
  // Settings, analytics, admin
  // ─────────────────────────────────────────────────────────────
  settingsProfile: (): string => '/settings/profile',

  settingsAiModel: (): string => '/settings/ai-model',

  settingsUsage: (): string => '/settings/usage',

  settingsConstitution: (): string => '/settings/constitution',

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
  | { screen: 'workflow-new' }
  | { screen: 'run-history'; type?: string; sort?: string }
  | { screen: 'run-detail'; runId: string }
  | { screen: 'run-steps'; runId: string }
  | { screen: 'run-steps-agent'; runId: string; agentId: string }
  | { screen: 'run-files'; runId: string }
  | { screen: 'run-audit'; runId: string }
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

  if (head === 'register') {
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

    return { screen: 'unknown' };
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

    const subpath = segments[2];

    // /runs/{id}/steps
    if (subpath === 'steps') {
      if (segments.length === 3) {
        return { screen: 'run-steps', runId };
      }

      // /runs/{id}/steps/{agentId}
      const agentId = segments[3];
      return { screen: 'run-steps-agent', runId, agentId };
    }

    // /runs/{id}/files
    if (subpath === 'files') {
      return { screen: 'run-files', runId };
    }

    // /runs/{id}/audit
    if (subpath === 'audit') {
      return { screen: 'run-audit', runId };
    }

    // /runs/{id}/stream
    if (subpath === 'stream') {
      return { screen: 'run-stream', runId };
    }

    // /runs/{id}/versions/{v}
    if (subpath === 'versions') {
      const version = segments[3];
      return { screen: 'run-version', runId, version };
    }

    // /runs/{id}/preview/full
    if (subpath === 'preview' && segments[3] === 'full') {
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
    // not an unknown/redirect stub. The legacy 2-segment list shape
    // (/library/agents, /library/skills, /library/hooks with no slug) is
    // intercepted by next.config.ts redirects before it ever reaches here.
    if (segments.length === 1) {
      return { screen: 'library' };
    }

    const type = segments[1];

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
      // /settings with no tab — could redirect to profile, but we'll parse as unknown
      return { screen: 'unknown' };
    }

    const tab = segments[1];

    if (tab === 'profile') return { screen: 'settings-profile' };
    if (tab === 'ai-model') return { screen: 'settings-ai-model' };
    if (tab === 'usage') return { screen: 'settings-usage' };
    if (tab === 'constitution') return { screen: 'settings-constitution' };

    return { screen: 'unknown' };
  }

  if (head === 'analytics') {
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
