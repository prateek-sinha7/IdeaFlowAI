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
import { render, screen, waitFor, within } from "@testing-library/react";
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
    // ISS-034 default: spend_full === spend → a ZERO delta, so the prompt-cache
    // line renders nothing and the pre-existing cases stay untouched.
    spend_full: 1.23,
    metered_runs: 0,
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
    // The first payload's spend is rendered (appears in the KPI tile + spend chip).
    // Cost renders in the mock's 2-dp currency format (40-04 number-format parity).
    await waitFor(() =>
      expect(screen.getAllByText("$1.23").length).toBeGreaterThan(0),
    );

    await user.click(screen.getByRole("button", { name: "7d" }));

    // Server recompute: refetched with the new range (NOT re-filtered in memory).
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "7d"),
    );
    // A number re-renders from the SECOND payload.
    await waitFor(() =>
      expect(screen.getAllByText("$4.56").length).toBeGreaterThan(0),
    );
  });

  it("renders the charts with role='img' (a11y via the 38-02 primitives)", async () => {
    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );
    await waitFor(() => expect(screen.getAllByRole("img").length).toBeGreaterThan(0));
  });
});

describe("AnalyticsPage — Avg / Run KPI math (MD-2)", () => {
  it("divides all-run tokens by ALL runs (totalCount), not completed runs", async () => {
    // Settle the KPI count-up animation in a single frame: jsdom's rAF never
    // advances performance.now() to completion, freezing the value mid-flight.
    // A huge timestamp makes AnimatedNumber's t reach 1 on the first tick.
    let rafTime = 1e9;
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((cb: FrameRequestCallback) => {
        rafTime += 1_000;
        cb(rafTime);
        return 0;
      });
    try {
      mockGetAnalyticsSummary.mockReset();
      mockGetAnalyticsSummary.mockResolvedValue(
        summary({
          // 900 tokens are summed over ALL 10 runs (backend _aggregate); only 4
          // completed. Fixed avg = 900/10 = 90; the pre-fix bug divided by the
          // completed count → 900/4 = 225.
          kpis: { total: 10, completed: 4, failed: 1, success_rate: 0.4 },
          token_totals: { input: 600, output: 300, cache_read: 0, cache_write: 0, total: 900 },
        }),
      );
      render(<AnalyticsPage onBack={() => {}} />);
      await waitFor(() =>
        expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
      );

      // Scope to the Avg / Run card so no other animated counter can collide.
      const card = (await screen.findByText("Avg / Run")).closest(
        "div.bg-surface-card",
      ) as HTMLElement;
      expect(card).not.toBeNull();
      await waitFor(() =>
        expect(within(card).getByText("90")).toBeInTheDocument(),
      );
      expect(within(card).queryByText("225")).not.toBeInTheDocument();
    } finally {
      rafSpy.mockRestore();
    }
  });
});

/**
 * ISS-034 — the SIGNED prompt-cache delta.
 *
 * The renderer must never say "saved" unconditionally: 6 of the 11 runs measured
 * when this shipped were net-NEGATIVE (a run that writes cache entries it never
 * re-reads pays the 1.25x cache_write premium for nothing). The sign is the
 * product of the data. A zero delta — including a window of only pre-ISS-034
 * rows, which the backend folds to zero rather than a fabricated $0 baseline —
 * renders NOTHING, because a "0%" would imply caching ran and broke even.
 */
describe("AnalyticsPage — signed prompt-cache delta (ISS-034)", () => {
  beforeEach(() => {
    mockGetAnalyticsSummary.mockReset();
  });

  async function renderWith(over: Partial<AnalyticsSummary>) {
    mockGetAnalyticsSummary.mockResolvedValue(summary(over));
    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );
  }

  it("says SAVED with the percentage primary when caching paid off", async () => {
    // Observed run 6e38b9a7: $7.07 paid vs $42.20 uncached → +83%.
    await renderWith({ spend: 7.06875, spend_full: 42.196866, metered_runs: 1 });

    const row = await screen.findByTestId("cache-delta");
    expect(within(row).getByText("Prompt caching saved")).toBeInTheDocument();
    expect(within(row).getByText("83%")).toBeInTheDocument();
    expect(within(row).getByText("$35.13")).toBeInTheDocument();
    expect(screen.queryByText(/cost more/i)).not.toBeInTheDocument();
  });

  it("says COST MORE when caching was a net loss", async () => {
    // Observed run a7dba362: $0.344028 paid vs $0.320110 uncached → -7.47%.
    await renderWith({ spend: 0.344028, spend_full: 0.32011, metered_runs: 1 });

    const row = await screen.findByTestId("cache-delta");
    expect(within(row).getByText("Prompt caching cost more")).toBeInTheDocument();
    expect(within(row).getByText("7%")).toBeInTheDocument();
    // The dollar is unsigned in the figure — the WORDING carries the sign.
    expect(within(row).getByText("$0.02")).toBeInTheDocument();
    expect(screen.queryByText("Prompt caching saved")).not.toBeInTheDocument();
  });

  it("renders NOTHING on a zero delta", async () => {
    await renderWith({ spend: 5.0, spend_full: 5.0, metered_runs: 3 });

    await screen.findByText("Est. Cost");
    expect(screen.queryByTestId("cache-delta")).not.toBeInTheDocument();
  });

  it("renders NOTHING for a window of only legacy (unmetered) runs", async () => {
    // The backend folds a legacy row to a zero delta, so spend_full === spend.
    // This is the case that would otherwise print "cost you $17.69 more (-100%)".
    await renderWith({ spend: 17.689716, spend_full: 17.689716, metered_runs: 0 });

    await screen.findByText("Est. Cost");
    expect(screen.queryByTestId("cache-delta")).not.toBeInTheDocument();
    expect(screen.queryByText(/-100%/)).not.toBeInTheDocument();
  });

  it("states the coverage and the scope when only part of the window is metered", async () => {
    await renderWith({
      kpis: { total: 10, completed: 8, failed: 2, success_rate: 0.8 },
      spend: 7.06875,
      spend_full: 42.196866,
      metered_runs: 4,
    });

    await screen.findByTestId("cache-delta");
    expect(screen.getByText(/Measured on 4 of 10 runs/)).toBeInTheDocument();
    expect(
      screen.getByText(/Engine agent tokens only/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/handoff runs are not metered/),
    ).toBeInTheDocument();
  });
});
