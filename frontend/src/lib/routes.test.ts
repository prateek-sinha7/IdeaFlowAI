import { describe, it, expect } from 'vitest';
import { routes, parseViewPath, type ParsedView } from './routes';

/**
 * Round-trip tests for all routes: builder → path → parse → assert.
 * Every route in contracts/route-map.md must have at least one test case.
 */

describe('routes - round-trip tests', () => {
  /**
   * Helper to test a builder and its parser round-trip.
   * Parses the built path and asserts the result matches expected descriptor.
   */
  function testRoundTrip(
    name: string,
    builder: () => string,
    expectedDescriptor: ParsedView
  ) {
    it(`${name} round-trips`, () => {
      const path = builder();
      // Extract segments from path: /foo/bar/baz -> ['foo', 'bar', 'baz']
      const segments = path
        .split('/')
        .filter(Boolean)
        .map(decodeURIComponent);
      // Query params are NOT in segments; they're handled at call site via useSearchParams
      const parsed = parseViewPath(segments.length > 0 ? segments : undefined);
      expect(parsed).toEqual(expectedDescriptor);
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Auth & root
  // ─────────────────────────────────────────────────────────────

  describe('Auth & root', () => {
    testRoundTrip('login', () => routes.login(), { screen: 'login' });
    // Note: login with params (?expired=true) — query params are handled at call site via useSearchParams,
    // not in the path segments passed to parseViewPath. Round-trip tests only validate the path portion.
    testRoundTrip(
      'login path (query params handled separately)',
      () => routes.login({ expired: true }).split('?')[0], // Extract path only
      { screen: 'login' }
    );
    testRoundTrip('register', () => routes.register(), { screen: 'register' });

    // ISS-238: /register/<sub-path> must not be matched as the exact register screen —
    // [...view]/page.tsx has no branch for screen === 'register', so anything that resolves
    // to it silently falls through to the dashboard render instead of a 404. `create` and
    // `workflows` both guard with segments.length === 1; `register` did not.
    it('ISS-238: /register/<sub-path> is not the register screen', () => {
      const parsed = parseViewPath(['register', 'anything']);
      expect(parsed).not.toEqual({ screen: 'register' });
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Home & creation
  // ─────────────────────────────────────────────────────────────

  describe('Home & creation', () => {
    testRoundTrip('home', () => routes.home(), { screen: 'home' });
    testRoundTrip('dashboard', () => routes.dashboard(), { screen: 'home' });
    testRoundTrip('create', () => routes.create(), { screen: 'create' });
    testRoundTrip('createPpt', () => routes.createPpt(), {
      screen: 'create-ppt',
    });
    testRoundTrip('createPrototype', () => routes.createPrototype(), {
      screen: 'create-prototype',
    });
    testRoundTrip('createApp', () => routes.createApp(), {
      screen: 'create-app',
    });
    testRoundTrip('createUserStories', () => routes.createUserStories(), {
      screen: 'create-user-stories',
    });
    testRoundTrip('workflowNew', () => routes.workflowNew(), {
      screen: 'workflow-new',
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Runs
  // ─────────────────────────────────────────────────────────────

  describe('Runs', () => {
    testRoundTrip('runHistory', () => routes.runHistory(), {
      screen: 'run-history',
    });
    // Query params are handled at call site via useSearchParams, not in segments.
    // Round-trip tests validate the path portion only.
    testRoundTrip(
      'runHistory path (type param handled separately)',
      () => routes.runHistory({ type: 'all' }).split('?')[0],
      { screen: 'run-history' }
    );
    testRoundTrip(
      'runHistory path (sort param handled separately)',
      () => routes.runHistory({ sort: 'recent' }).split('?')[0],
      { screen: 'run-history' }
    );
    testRoundTrip(
      'runHistory path (type and sort params handled separately)',
      () => routes.runHistory({ type: 'all', sort: 'recent' }).split('?')[0],
      { screen: 'run-history' }
    );
    testRoundTrip('runHistory with empty params', () => routes.runHistory({}), {
      screen: 'run-history',
    });

    testRoundTrip('runDetail', () => routes.runDetail('run-123'), {
      screen: 'run-detail',
      runId: 'run-123',
    });
    testRoundTrip('runSteps', () => routes.runSteps('run-456'), {
      screen: 'run-steps',
      runId: 'run-456',
    });
    testRoundTrip('runStepsAgent', () => routes.runStepsAgent('run-789', 'agent-1'), {
      screen: 'run-steps-agent',
      runId: 'run-789',
      agentId: 'agent-1',
    });
    testRoundTrip('runFiles', () => routes.runFiles('run-111'), {
      screen: 'run-files',
      runId: 'run-111',
    });
    testRoundTrip('runAudit', () => routes.runAudit('run-222'), {
      screen: 'run-audit',
      runId: 'run-222',
    });
    testRoundTrip('runStream', () => routes.runStream('run-333'), {
      screen: 'run-stream',
      runId: 'run-333',
    });
    testRoundTrip('runVersion', () => routes.runVersion('run-444', 'v1'), {
      screen: 'run-version',
      runId: 'run-444',
      version: 'v1',
    });
    testRoundTrip('runPreviewFull', () => routes.runPreviewFull('run-555'), {
      screen: 'run-preview-full',
      runId: 'run-555',
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Saved workflows
  // ─────────────────────────────────────────────────────────────

  describe('Saved workflows', () => {
    testRoundTrip('workflows', () => routes.workflows(), {
      screen: 'workflows',
    });
    testRoundTrip('workflow', () => routes.workflow('workflow-1'), {
      screen: 'workflow',
      workflowId: 'workflow-1',
    });
    testRoundTrip('workflowEdit', () => routes.workflowEdit('workflow-2'), {
      screen: 'workflow-edit',
      workflowId: 'workflow-2',
    });
    testRoundTrip('workflowRun', () => routes.workflowRun('workflow-3'), {
      screen: 'workflow-run',
      workflowId: 'workflow-3',
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Library
  // ─────────────────────────────────────────────────────────────

  describe('Library', () => {
    // Post-close amendment (2026-08-21): the 3 list screens (agents/skills/
    // hooks) collapsed from 3 path segments into ONE path with tab/category
    // as query params. Item-DETAIL routes below are unaffected.
    testRoundTrip('library (default tab)', () => routes.library(), {
      screen: 'library',
    });
    // Query params (tab/category) are handled at call site via useSearchParams,
    // not in the path segments passed to parseViewPath — same convention as
    // every other query-bearing screen above (login, runHistory, analytics).
    testRoundTrip(
      'library path (tab param handled separately)',
      () => routes.library({ tab: 'skills' }).split('?')[0],
      { screen: 'library' }
    );
    testRoundTrip(
      'library path (category param handled separately)',
      () => routes.library({ tab: 'agents', category: 'sales' }).split('?')[0],
      { screen: 'library' }
    );
    testRoundTrip(
      'library with empty params',
      () => routes.library({}),
      { screen: 'library' }
    );

    it('omits ?tab= when tab is "agents" (the default)', () => {
      expect(routes.library({ tab: 'agents' })).toBe('/library');
    });
    it('omits ?tab= when tab is undefined', () => {
      expect(routes.library()).toBe('/library');
    });
    it('includes ?tab= for skills/hooks', () => {
      expect(routes.library({ tab: 'skills' })).toBe('/library?tab=skills');
      expect(routes.library({ tab: 'hooks' })).toBe('/library?tab=hooks');
    });
    it('omits ?category= when category is "all", undefined, or falsy', () => {
      expect(routes.library({ tab: 'skills', category: 'all' })).toBe('/library?tab=skills');
      expect(routes.library({ tab: 'skills', category: '' })).toBe('/library?tab=skills');
    });
    it('includes both tab and category together', () => {
      expect(routes.library({ tab: 'skills', category: 'research' })).toBe(
        '/library?tab=skills&category=research'
      );
    });

    testRoundTrip('libraryAgent', () => routes.libraryAgent('ai-analyst'), {
      screen: 'library-agent',
      slug: 'ai-analyst',
    });

    testRoundTrip('librarySkill', () => routes.librarySkill('web-scraper'), {
      screen: 'library-skill',
      slug: 'web-scraper',
    });

    testRoundTrip('libraryHook', () => routes.libraryHook('on-complete'), {
      screen: 'library-hook',
      slug: 'on-complete',
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Settings, analytics, admin
  // ─────────────────────────────────────────────────────────────

  describe('Settings, analytics, admin', () => {
    testRoundTrip('settingsProfile', () => routes.settingsProfile(), {
      screen: 'settings-profile',
    });
    testRoundTrip('settingsAiModel', () => routes.settingsAiModel(), {
      screen: 'settings-ai-model',
    });
    testRoundTrip('settingsUsage', () => routes.settingsUsage(), {
      screen: 'settings-usage',
    });
    testRoundTrip('settingsConstitution', () => routes.settingsConstitution(), {
      screen: 'settings-constitution',
    });

    testRoundTrip('analytics', () => routes.analytics(), {
      screen: 'analytics',
    });
    // Query params are handled at call site via useSearchParams.
    testRoundTrip(
      'analytics path (range param handled separately)',
      () => routes.analytics({ range: '7d' }).split('?')[0],
      { screen: 'analytics' }
    );
    testRoundTrip(
      'analytics path (pipeline param handled separately)',
      () => routes.analytics({ pipeline: 'main' }).split('?')[0],
      { screen: 'analytics' }
    );
    testRoundTrip(
      'analytics path (range and pipeline params handled separately)',
      () => routes.analytics({ range: '30d', pipeline: 'all' }).split('?')[0],
      { screen: 'analytics' }
    );
    testRoundTrip('analytics with empty params', () => routes.analytics({}), {
      screen: 'analytics',
    });

    testRoundTrip('admin', () => routes.admin(), { screen: 'admin' });
  });

  // ─────────────────────────────────────────────────────────────
  // Special cases: undefined, empty, unknown
  // ─────────────────────────────────────────────────────────────

  describe('Special cases', () => {
    it('undefined segments resolves to home', () => {
      const parsed = parseViewPath(undefined);
      expect(parsed).toEqual({ screen: 'home' });
    });

    it('["dashboard"] resolves to home', () => {
      const parsed = parseViewPath(['dashboard']);
      expect(parsed).toEqual({ screen: 'home' });
    });

    it('empty array resolves to home', () => {
      const parsed = parseViewPath([]);
      expect(parsed).toEqual({ screen: 'home' });
    });

    it('unknown path returns unknown screen', () => {
      const parsed = parseViewPath(['nonsense', 'path']);
      expect(parsed).toEqual({ screen: 'unknown' });
    });

    it('/library with no further segments returns the unified library screen', () => {
      const parsed = parseViewPath(['library']);
      expect(parsed).toEqual({ screen: 'library' });
    });

    // ISS-572: these three used to assert `unknown` on the premise that
    // next.config.ts intercepted them before they reached parseViewPath. That
    // holds only for a full/document navigation — a client-side transition
    // reaches the parser directly — so the parser now mirrors the redirect.
    it('/library/{type} with no slug (legacy list shape) mirrors the next.config.ts redirect to the library screen', () => {
      expect(parseViewPath(['library', 'agents'])).toEqual({ screen: 'library' });
      expect(parseViewPath(['library', 'skills'])).toEqual({ screen: 'library' });
      expect(parseViewPath(['library', 'hooks'])).toEqual({ screen: 'library' });
    });

    // ISS-339: same correction as above for the fourth next.config.ts redirect.
    it('/settings without tab mirrors the next.config.ts redirect to the profile tab', () => {
      const parsed = parseViewPath(['settings']);
      expect(parsed).toEqual({ screen: 'settings-profile' });
    });

    it('single-segment unknown path returns unknown', () => {
      const parsed = parseViewPath(['bogus']);
      expect(parsed).toEqual({ screen: 'unknown' });
    });
  });
});
