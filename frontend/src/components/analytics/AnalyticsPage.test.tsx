/**
 * Phase 38 plan-04 (B4-04) — AnalyticsPage endpoint-recompute contract (RED-first).
 *
 * Locks SC-1: the dashboard sources its numbers from the owner-scoped, date-scoped
 * `getAnalyticsSummary(token, range)` endpoint (38-01) — NOT a client-side rollup of
 * up-to-500 raw runs. Changing the date filter must RE-QUERY the server with the new
 * range and re-render a KPI from the fresh payload (server recompute), and the charts
 * must expose role="img" (a11y via the 38-02 primitives).
 *
 * Authored BEFORE AnalyticsPage is rewired, so the current getWorkflows-based page
 * never calls getAnalyticsSummary → RED. Task 3 turns it GREEN.
 *
 * Mock idiom mirrors SavedWorkflowsPage.test.tsx: vi.mock("@/lib/api", ...) for the
 * fetchers + the motion proxy that preserves the underlying HTML tag so role/text
 * queries keep resolving.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { AnalyticsSummary } from "@/lib/api";

const mockGetToken = vi.fn(() => "test-token");
const mockGetAnalyticsSummary =
  vi.fn<(token: string, range: string) => Promise<AnalyticsSummary>>();
const mockGetPreferences = vi.fn(() =>
  Promise.resolve({ preferred_model: null, available_models: [] }),
);
const mockGetWorkflows = vi.fn(() => Promise.resolve([]));

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getAnalyticsSummary: (token: string, range: string) =>
    mockGetAnalyticsSummary(token, range),
  getPreferences: () => mockGetPreferences(),
  getWorkflows: () => mockGetWorkflows(),
}));

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

// Imported AFTER the mocks so the component picks up the mocked deps.
import { AnalyticsPage } from "./AnalyticsPage";

function summary(overrides: Partial<AnalyticsSummary>): AnalyticsSummary {
  return {
    kpis: { total: 10, completed: 8, failed: 2, success_rate: 0.8 },
    daily: [
      { date: "2026-07-01", total: 3, completed: 3, failed: 0, input_tokens: 100, output_tokens: 50, total_tokens: 150 },
      { date: "2026-07-02", total: 4, completed: 3, failed: 1, input_tokens: 200, output_tokens: 80, total_tokens: 280 },
    ],
    pipelines: [
      { type: "prototype", count: 5, total_tokens: 500, cost: 0.5, avg_duration: 12 },
    ],
    models: [
      { model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0", count: 5, total_tokens: 500, cost: 0.5 },
    ],
    spend: 1.23,
    token_totals: { input: 300, output: 130, cache_read: 0, cache_write: 0, total: 430 },
    type_avg_duration_sec: { prototype: 12 },
    ...overrides,
  };
}

const PAYLOAD_30D = summary({ spend: 1.23 });
const PAYLOAD_7D = summary({ spend: 4.56, token_totals: { input: 400, output: 200, cache_read: 0, cache_write: 0, total: 600 } });

describe("AnalyticsPage — server recompute (SC-1)", () => {
  beforeEach(() => {
    mockGetAnalyticsSummary.mockReset();
    mockGetAnalyticsSummary
      .mockResolvedValueOnce(PAYLOAD_30D)
      .mockResolvedValue(PAYLOAD_7D);
  });

  it("queries getAnalyticsSummary on mount with the default range", async () => {
    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );
  });

  it("re-queries the server with the NEW range on a date-filter change and re-renders a KPI from the fresh payload", async () => {
    const user = userEvent.setup();
    render(<AnalyticsPage onBack={() => {}} />);

    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );
    // The first payload's spend is rendered.
    await waitFor(() => expect(screen.getByText("$1.230")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "7d" }));

    // Server recompute: refetched with the new range (NOT re-filtered in memory).
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "7d"),
    );
    // A number re-renders from the SECOND payload.
    await waitFor(() => expect(screen.getByText("$4.560")).toBeInTheDocument());
  });

  it("renders the charts with role='img' (a11y via the 38-02 primitives)", async () => {
    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );
    await waitFor(() => expect(screen.getAllByRole("img").length).toBeGreaterThan(0));
  });
});
