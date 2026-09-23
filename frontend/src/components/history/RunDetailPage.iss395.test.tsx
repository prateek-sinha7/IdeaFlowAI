import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import type { RunSummary } from "@/lib/api";

/**
 * ISS-395 — RunDetailPage's `terminalFailure` triad (RunDetailPage.tsx:230-233)
 * omits "diverted", so a diverted run's Agents tab lists its partially-run
 * agents as a plain completed-looking list, with no DegradedRunAffordance
 * banner explaining that the pipeline stopped for good at a divert point and
 * a further agent never ran.
 *
 * Scaffold cloned from the neighbouring FAILED/CANCELLED cases in
 * RunDetailPage.test.tsx.
 */

const mockGetToken = vi.fn(() => "test-token");
const mockGetRunSummary =
  vi.fn<(token: string, runId: string) => Promise<RunSummary>>();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => mockGetToken(),
    getRunSummary: (token: string, runId: string) =>
      mockGetRunSummary(token, runId),
  };
});

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

import { RunDetailPage } from "./RunDetailPage";

// Mirrors the seeded repro run "Ex A4 Human Divert" — 2/3 agents ran, no error.
const DIVERTED: RunSummary = {
  id: "run-d",
  title: "Ex A4 Human Divert",
  type: "prototype",
  status: "diverted",
  duration: 90,
  agent_count: 2,
  token_usage: { total_input_tokens: 500, total_output_tokens: 300, total_tokens: 800 },
  error: null,
  agents: [
    { agent_id: "domain-analyst", name: "Domain Analyst", role: "Analysis", icon: "🧠", duration: 12, total_tokens: 400 },
    { agent_id: "prototype-build", name: "Prototype Builder", role: "Build", icon: "🔨", duration: 40, total_tokens: 400 },
  ],
  root_id: "run-d",
  members: [
    { id: "run-d", type: "prototype", title: "Ex A4 Human Divert", status: "diverted", revision_index: 1, parent_run_id: null, created_at: "2026-08-24T13:00:00", completed_at: "2026-08-24T13:27:57" },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetToken.mockReturnValue("test-token");
});

describe("RunDetailPage — ISS-395 diverted-run Agents tab", () => {
  it("diverted run → DegradedRunAffordance (or diverted-aware banner) renders instead of a plain, unexplained agent list", async () => {
    mockGetRunSummary.mockResolvedValue(DIVERTED);
    render(<RunDetailPage runId="run-d" onBack={() => {}} />);

    // Correct behaviour: a diverted run is a terminal, non-resumable state —
    // it must surface the same explanatory affordance the failed/cancelled/
    // degraded siblings already get, not render as if it completed normally.
    expect(await screen.findByText(/did not complete successfully/i)).toBeInTheDocument();
  });
});
