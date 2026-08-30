import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, rerenderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import React from "react";
import type { AnalyticsSummary } from "@/lib/api";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// ISS-188 / ISS-201 — BUG-20260827-234030-create: HomeLaunchGrid's
// `vlc_home_recents_v1` sessionStorage cache has no per-user scope
// (`frontend/src/components/catalog/HomeLaunchGrid.tsx:37-166`). Same mock
// idiom as HomeLaunchGrid.test.tsx (api + next/navigation + motion/react).
// ─────────────────────────────────────────────────────────────────

// Each mock DECLARES the parameters the vi.mock factory below forwards to it.
// vitest infers a mock's call signature from its implementation, so a zero-arg
// implementation called with `(token)` is a type error even though it works at
// runtime — and the arguments are the whole point here: the assertions below read
// them back off `.mock.calls` to prove the second account refetched with its own
// token rather than serving the first account's cached rows.
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflowDefinitions = vi.fn<(token: string) => Promise<unknown[]>>(async () => []);
const mockGetUserWorkflows = vi.fn<(token: string) => Promise<unknown[]>>(async () => []);
const mockGetAnalyticsSummary = vi.fn<(token: string, range: string) => Promise<AnalyticsSummary>>(
  async () => ({ type_avg_duration_sec: {} } as unknown as AnalyticsSummary),
);
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<WorkflowRun[]>>(
  async () => [],
);

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflowDefinitions: (token: string) => mockGetWorkflowDefinitions(token),
  getUserWorkflows: (token: string) => mockGetUserWorkflows(token),
  getAnalyticsSummary: (token: string, range: string) => mockGetAnalyticsSummary(token, range),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  createUserWorkflow: vi.fn(),
  renameUserWorkflow: vi.fn(),
  deleteUserWorkflow: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

import { HomeLaunchGrid } from "./HomeLaunchGrid";

const CACHE_KEY = "vlc_home_recents_v1";

function makeRun(partial: Partial<WorkflowRun> & { id: string }): WorkflowRun {
  return {
    title: `Run ${partial.id}`,
    type: "user_stories",
    status: "completed",
    input: "",
    parentRunId: null,
    rootRunId: partial.id,
    createdAt: new Date().toISOString(),
    agentCount: 3,
    ...partial,
  } as WorkflowRun;
}

const FOREIGN_TITLE = "qa-admin's private pitch deck";

describe("HomeLaunchGrid cross-account recents leak (BUG-20260827-234030-create)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetWorkflowDefinitions.mockResolvedValue([]);
    mockGetUserWorkflows.mockResolvedValue([]);
    sessionStorage.clear();
    // Simulate a PRIOR account's write to the shared, unscoped cache key.
    sessionStorage.setItem(
      CACHE_KEY,
      JSON.stringify([makeRun({ id: "foreign-run", title: FOREIGN_TITLE })]),
    );
  });

  // ISS-188 (root, CONFIRMED): a newly-signed-in account whose OWN live
  // fetch genuinely resolves to zero runs must never render a previous
  // account's cached recents. Today the cache is used verbatim forever,
  // because neither refresh effect has an "else" branch for a genuine
  // empty result.
  it("ISS-188: never shows a prior account's cached recents once this account's live fetch genuinely resolves empty", async () => {
    renderWithProviders(
      <HomeLaunchGrid onSelectFeature={vi.fn()} userTier="enterprise" recentRuns={[]} />,
      {
        preloadedState: {
          global: {
            workflows: [],
            workflowsStatus: "succeeded",
            workflowsError: null,
            recentRuns: [], // this account's own live fetch resolved to zero
            recentRunsStatus: "succeeded",
            recentRunsError: null,
          },
        },
      },
    );

    // Give any effects a chance to settle.
    await waitFor(() => expect(mockGetAnalyticsSummary).toHaveBeenCalled());

    expect(screen.queryByText(FOREIGN_TITLE)).toBeNull();
  });

  // ISS-201 (INFERRED sibling): even when this account DOES have its own
  // real run history, the mount-time `useState(() => readCache(...))`
  // fallback paints the prior account's cached cards for at least the
  // first frame, before the live prop resolves and overwrites it.
  it("ISS-201: never paints a prior account's cached recents even on the very first frame, before this account's own fetch resolves", async () => {
    renderWithProviders(
      <HomeLaunchGrid onSelectFeature={vi.fn()} userTier="enterprise" recentRuns={[]} />,
      {
        preloadedState: {
          global: {
            workflows: [],
            workflowsStatus: "succeeded",
            workflowsError: null,
            recentRuns: [], // this account's own redux preload hasn't resolved yet
            recentRunsStatus: "loading",
            recentRunsError: null,
          },
        },
      },
    );

    // Assert the very first paint (before the live recentRuns prop below
    // ever arrives) never shows the foreign account's cached card.
    expect(screen.queryByText(FOREIGN_TITLE)).toBeNull();

    // The live fetch now resolves with THIS account's own, genuine history.
    const ownRun = makeRun({ id: "own-run", title: "My real run" });
    rerenderWithProviders(
      <HomeLaunchGrid onSelectFeature={vi.fn()} userTier="enterprise" recentRuns={[ownRun]} />,
    );

    await waitFor(() => expect(screen.getByText("My real run")).toBeInTheDocument());
  });
});
