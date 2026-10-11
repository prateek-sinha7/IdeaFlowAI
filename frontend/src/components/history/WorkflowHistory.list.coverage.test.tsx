/**
 * WorkflowHistory (list view) — branch/interaction coverage: initial load
 * outcomes, URL-seeded filter/sort, filter chips, search, empty states, date
 * buckets, manual / timer / parent-driven refresh, infinite-scroll load more,
 * and the delete flow.
 *
 * Boundaries mocked: @/lib/api, next/navigation, IntersectionObserver (absent
 * in jsdom), the interval timer, and the motion shim. RevisionFamilyView rows
 * and RunDetailPage render for real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";
import type { RunSummary } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";

type RunsPage = { runs: WorkflowRun[]; total: number };

const mockGetToken = vi.fn<() => string | null>(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number; offset?: number }) => Promise<RunsPage>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();
const mockGetRunSummary = vi.fn<(token: string, id: string) => Promise<RunSummary>>();
const mockReplace = vi.fn();
const searchParamValues = new Map<string, string>();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: mockReplace, prefetch: vi.fn() }),
  useSearchParams: () => ({ get: (key: string) => searchParamValues.get(key) ?? null }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => mockGetToken(),
    getWorkflows: (token: string, opts?: { limit?: number; offset?: number }) => mockGetWorkflows(token, opts),
    deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
    getRunSummary: (token: string, id: string) => mockGetRunSummary(token, id),
    getWorkflow: vi.fn(),
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
    getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
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

import { WorkflowHistory } from "./WorkflowHistory";

// ─── Builders ────────────────────────────────────────────────────────────────
const DAY = 86_400_000;
const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

function makeRun(overrides: Partial<WorkflowRun> & { id: string }): WorkflowRun {
  return {
    title: `Run ${overrides.id}`,
    type: "prototype",
    status: "completed",
    input: "brief",
    output: "output",
    createdAt: ago(60_000),
    agentCount: 2,
    parentRunId: null,
    rootRunId: overrides.id,
    ...overrides,
  } as WorkflowRun;
}

function page(runs: WorkflowRun[], total = runs.length): RunsPage {
  return { runs, total };
}

// IntersectionObserver is not implemented by jsdom; capture the callbacks so a
// test can simulate the sentinel scrolling into view.
const observers: Array<{ callback: IntersectionObserverCallback; disconnected: boolean }> = [];
class FakeIntersectionObserver {
  private record: { callback: IntersectionObserverCallback; disconnected: boolean };
  constructor(callback: IntersectionObserverCallback) {
    this.record = { callback, disconnected: false };
    observers.push(this.record);
  }
  observe() {}
  unobserve() {}
  disconnect() { this.record.disconnected = true; }
}

async function scrollSentinelIntoView(isIntersecting = true) {
  const live = observers.filter((o) => !o.disconnected);
  const latest = live[live.length - 1];
  await act(async () => {
    latest.callback([{ isIntersecting } as IntersectionObserverEntry], {} as IntersectionObserver);
  });
}

function renderHistory(props: Partial<React.ComponentProps<typeof WorkflowHistory>> = {}) {
  return renderWithProviders(<WorkflowHistory onBack={vi.fn()} {...props} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamValues.clear();
  observers.length = 0;
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  mockGetToken.mockReturnValue("test-token");
  mockGetWorkflows.mockResolvedValue(page([]));
  mockDeleteWorkflow.mockResolvedValue(undefined);
  mockGetRunSummary.mockRejectedValue(new Error("no summary in this test"));
});

afterEach(() => {
  // Unmount first so no late state update can re-run the load-more effect after the
  // IntersectionObserver stub has been removed.
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// ─── Initial load ────────────────────────────────────────────────────────────
describe("WorkflowHistory list — initial load", () => {
  it("shows the loading skeleton until the first page arrives, then the run count and rows", async () => {
    let resolvePage: (p: RunsPage) => void = () => {};
    mockGetWorkflows.mockReturnValue(new Promise<RunsPage>((r) => { resolvePage = r; }));
    renderHistory();

    expect(screen.getByText("Loading workflows")).toBeInTheDocument();
    await act(async () => {
      resolvePage(page([makeRun({ id: "a", title: "Alpha" })], 1));
    });

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("1 runs")).toBeInTheDocument();
    expect(screen.queryByText("Loading workflows")).not.toBeInTheDocument();
  });

  it("requests the first page of 50 with the owner token", async () => {
    renderHistory();
    await screen.findByText("No runs yet");

    expect(mockGetWorkflows).toHaveBeenCalledWith("test-token", { limit: 50 });
  });

  it("stays on the loading skeleton and never calls the API without a token", () => {
    mockGetToken.mockReturnValue(null);
    renderHistory();

    expect(screen.getByText("Loading workflows")).toBeInTheDocument();
    expect(mockGetWorkflows).not.toHaveBeenCalled();
  });

  it("falls back to the empty state when the first request fails", async () => {
    mockGetWorkflows.mockRejectedValue(new Error("network down"));
    renderHistory();

    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByText("0 runs")).toBeInTheDocument();
  });

  it("zero state offers 'Start a run' which leaves the history", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    renderHistory({ onBack });

    await user.click(await screen.findByRole("button", { name: "Start a run" }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("the header back control leaves the history", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a" })]));
    renderHistory({ onBack });
    await screen.findByText("Run a");

    // The header back button renders only an icon (no accessible name) — it is the
    // first button in DOM order; reported as an a11y gap in the evidence notes.
    await user.click(screen.getAllByRole("button")[0]);

    expect(onBack).toHaveBeenCalledTimes(1);
  });
});

// ─── Date buckets ────────────────────────────────────────────────────────────
describe("WorkflowHistory list — date buckets", () => {
  it("groups rows into Today / Earlier this week / Older sections with counts", async () => {
    mockGetWorkflows.mockResolvedValue(
      page([
        makeRun({ id: "t", title: "Fresh run", createdAt: ago(60_000) }),
        makeRun({ id: "e", title: "Midweek run", createdAt: ago(3 * DAY) }),
        makeRun({ id: "o", title: "Ancient run", createdAt: ago(30 * DAY) }),
      ]),
    );
    renderHistory();
    await screen.findByText("Fresh run");

    const today = screen.getByRole("region", { name: "Today" });
    const earlier = screen.getByRole("region", { name: "Earlier" });
    const older = screen.getByRole("region", { name: "Older" });
    expect(within(today).getByText("Fresh run")).toBeInTheDocument();
    expect(within(earlier).getByText("Earlier this week")).toBeInTheDocument();
    expect(within(earlier).getByText("Midweek run")).toBeInTheDocument();
    expect(within(older).getByText("Ancient run")).toBeInTheDocument();
  });
});

// ─── Filters, search, sort ───────────────────────────────────────────────────
describe("WorkflowHistory list — filters and sort", () => {
  const mixed = [
    makeRun({ id: "p1", title: "Landing prototype", type: "prototype", createdAt: ago(5 * 60_000), duration: 10, tokenUsage: { total_input_tokens: 0, total_output_tokens: 0, total_tokens: 100, estimated_cost_usd: 0 } }),
    makeRun({ id: "d1", title: "Sales deck", type: "ppt", createdAt: ago(10 * 60_000), duration: 500, tokenUsage: { total_input_tokens: 0, total_output_tokens: 0, total_tokens: 9000, estimated_cost_usd: 0 } }),
    makeRun({ id: "c1", title: "Odd pipeline", type: "sample_conditional_x" as WorkflowRun["type"], createdAt: ago(20 * 60_000) }),
  ];

  it("shows per-bucket chip counts, hides empty buckets, and folds non-framework types into Custom", async () => {
    mockGetWorkflows.mockResolvedValue(page(mixed));
    renderHistory();
    await screen.findByText("Landing prototype");

    expect(screen.getByRole("button", { name: /^All\s*3$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Presentation\s*1$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Prototype\s*1$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Custom\s*1$/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^User Stories/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^App Builder/ })).not.toBeInTheDocument();
  });

  it("filters by type chip, refetches, and mirrors the choice into the URL", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page(mixed));
    renderHistory();
    await screen.findByText("Landing prototype");

    await user.click(screen.getByRole("button", { name: /^Presentation/ }));

    await waitFor(() => expect(screen.queryByText("Landing prototype")).not.toBeInTheDocument());
    expect(screen.getByText("Sales deck")).toBeInTheDocument();
    expect(mockReplace).toHaveBeenLastCalledWith("/runs?type=ppt");
    expect(mockGetWorkflows).toHaveBeenCalledTimes(2);
  });

  it("returns to All and drops the type from the URL", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page(mixed));
    renderHistory();
    await screen.findByText("Landing prototype");
    await user.click(screen.getByRole("button", { name: /^Custom/ }));
    await screen.findByText("Odd pipeline");

    await user.click(screen.getByRole("button", { name: /^All/ }));

    expect(await screen.findByText("Landing prototype")).toBeInTheDocument();
    expect(mockReplace).toHaveBeenLastCalledWith("/runs");
  });

  it("seeds type and sort from the URL on mount", async () => {
    searchParamValues.set("type", "ppt");
    searchParamValues.set("sort", "tokens");
    mockGetWorkflows.mockResolvedValue(page(mixed));
    renderHistory();

    expect(await screen.findByText("Sales deck")).toBeInTheDocument();
    expect(screen.queryByText("Landing prototype")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sort by tokens" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Sort by recent" })).toHaveAttribute("aria-pressed", "false");
  });

  it("sorts by longest duration and by tokens, keeping the type filter in the URL", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page(mixed));
    renderHistory();
    await screen.findByText("Landing prototype");
    const titlesInOrder = () =>
      screen.getAllByRole("button", { name: /^Open / }).map((b) => b.getAttribute("aria-label"));

    await user.click(screen.getByRole("button", { name: "Sort by duration" }));
    expect(titlesInOrder()[0]).toMatch(/^Open Sales deck/);
    expect(mockReplace).toHaveBeenLastCalledWith("/runs?sort=duration");

    await user.click(screen.getByRole("button", { name: "Sort by tokens" }));
    expect(titlesInOrder()[0]).toMatch(/^Open Sales deck/);
    expect(mockReplace).toHaveBeenLastCalledWith("/runs?sort=tokens");

    await user.click(screen.getByRole("button", { name: "Sort by recent" }));
    expect(titlesInOrder()[0]).toMatch(/^Open Landing prototype/);
    expect(mockReplace).toHaveBeenLastCalledWith("/runs");
  });

  it("includes the active type when changing the sort", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page(mixed));
    renderHistory();
    await screen.findByText("Landing prototype");
    await user.click(screen.getByRole("button", { name: /^Prototype/ }));
    await screen.findByText("Landing prototype");

    await user.click(screen.getByRole("button", { name: "Sort by duration" }));

    expect(mockReplace).toHaveBeenLastCalledWith("/runs?type=prototype&sort=duration");
  });

  it("searches titles case-insensitively and clears from the filter-empty state", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page(mixed));
    renderHistory();
    await screen.findByText("Landing prototype");

    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), "SALES");
    expect(screen.getByText("Sales deck")).toBeInTheDocument();
    expect(screen.queryByText("Landing prototype")).not.toBeInTheDocument();

    await user.clear(screen.getByRole("textbox", { name: "Search workflows" }));
    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), "zzz-nothing");
    expect(screen.getByText("No runs match this filter")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show all runs" }));

    expect(screen.getByRole("textbox", { name: "Search workflows" })).toHaveValue("");
    expect(screen.getByText("Landing prototype")).toBeInTheDocument();
  });

  it("matches a family when any of its members matches the URL-seeded type filter", async () => {
    searchParamValues.set("type", "prototype");
    const root = makeRun({ id: "root", title: "Root deck", type: "ppt", createdAt: ago(2 * 60 * 60_000) });
    const rev = makeRun({ id: "rev", title: "Rebuilt as prototype", type: "prototype_revision" as WorkflowRun["type"], parentRunId: "root", rootRunId: "root", createdAt: ago(60_000) });
    const unrelated = makeRun({ id: "other", title: "Unrelated deck", type: "ppt", createdAt: ago(3 * 60 * 60_000) });
    mockGetWorkflows.mockResolvedValue(page([root, rev, unrelated]));
    renderHistory();

    expect(await screen.findByRole("button", { name: /^Open Root deck/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Open Unrelated deck/ })).not.toBeInTheDocument();
  });

  it("warns that search and sort only cover the loaded window when more runs exist", async () => {
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a" })], 120));
    renderHistory();

    expect(await screen.findByText("Showing 1 of 120 runs — scroll down to load more")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^All\s*120$/ })).toBeInTheDocument();
  });

  it("shows no partial-scope notice when everything is loaded", async () => {
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a" })]));
    renderHistory();
    await screen.findByText("Run a");

    expect(screen.queryByText(/scroll down to load more/)).not.toBeInTheDocument();
  });
});

// ─── Load more ───────────────────────────────────────────────────────────────
describe("WorkflowHistory list — load more", () => {
  it("appends the next page at the right offset when the sentinel scrolls into view", async () => {
    mockGetWorkflows
      .mockResolvedValueOnce(page([makeRun({ id: "a", title: "First page run" })], 2))
      .mockResolvedValueOnce(page([makeRun({ id: "b", title: "Second page run" })], 2));
    renderHistory();
    await screen.findByText("First page run");

    await scrollSentinelIntoView();

    expect(await screen.findByText("Second page run")).toBeInTheDocument();
    expect(mockGetWorkflows).toHaveBeenLastCalledWith("test-token", { limit: 50, offset: 1 });
    expect(screen.queryByText("Load more")).not.toBeInTheDocument();
  });

  it("ignores the observer while the sentinel is not intersecting", async () => {
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Only run" })], 5));
    renderHistory();
    await screen.findByText("Only run");

    await scrollSentinelIntoView(false);

    expect(mockGetWorkflows).toHaveBeenCalledTimes(1);
  });

  it("shows a spinner label while loading more and does not double-fetch", async () => {
    let resolveMore: (p: RunsPage) => void = () => {};
    mockGetWorkflows
      .mockResolvedValueOnce(page([makeRun({ id: "a", title: "First page run" })], 3))
      .mockReturnValueOnce(new Promise<RunsPage>((r) => { resolveMore = r; }));
    renderHistory();
    await screen.findByText("First page run");

    await scrollSentinelIntoView();
    expect(await screen.findByLabelText("Loading more runs")).toBeInTheDocument();
    await scrollSentinelIntoView();
    expect(mockGetWorkflows).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveMore(page([makeRun({ id: "b", title: "Late run" })], 3));
    });
    expect(await screen.findByText("Late run")).toBeInTheDocument();
  });

  it("keeps the existing rows when loading more fails", async () => {
    mockGetWorkflows
      .mockResolvedValueOnce(page([makeRun({ id: "a", title: "First page run" })], 3))
      .mockRejectedValueOnce(new Error("503"));
    renderHistory();
    await screen.findByText("First page run");

    await scrollSentinelIntoView();

    await waitFor(() => expect(screen.getByText("Load more")).toBeInTheDocument());
    expect(screen.getByText("First page run")).toBeInTheDocument();
  });

  it("does not load more without a token", async () => {
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "First page run" })], 3));
    renderHistory();
    await screen.findByText("First page run");
    mockGetToken.mockReturnValue(null);

    await scrollSentinelIntoView();

    expect(mockGetWorkflows).toHaveBeenCalledTimes(1);
  });
});

// ─── Refresh ─────────────────────────────────────────────────────────────────
describe("WorkflowHistory list — refresh", () => {
  it("manually refreshes in place without flashing the skeleton, requesting at least 50 rows", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValueOnce(page([makeRun({ id: "a", title: "Before" })]));
    renderHistory();
    await screen.findByText("Before");
    mockGetWorkflows.mockResolvedValueOnce(page([makeRun({ id: "b", title: "After" })]));

    await user.click(screen.getByRole("button", { name: "Refresh run history" }));

    expect(await screen.findByText("After")).toBeInTheDocument();
    expect(screen.queryByText("Loading workflows")).not.toBeInTheDocument();
    expect(mockGetWorkflows).toHaveBeenLastCalledWith("test-token", { limit: 50 });
  });

  it("disables the refresh control while a refresh is running", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValueOnce(page([makeRun({ id: "a", title: "Before" })]));
    renderHistory();
    await screen.findByText("Before");
    let resolveRefresh: (p: RunsPage) => void = () => {};
    mockGetWorkflows.mockReturnValueOnce(new Promise<RunsPage>((r) => { resolveRefresh = r; }));

    await user.click(screen.getByRole("button", { name: "Refresh run history" }));
    expect(screen.getByRole("button", { name: "Refresh run history" })).toBeDisabled();

    await act(async () => {
      resolveRefresh(page([makeRun({ id: "a", title: "Before" })]));
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh run history" })).toBeEnabled());
  });

  it("keeps the current rows when a manual refresh fails", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValueOnce(page([makeRun({ id: "a", title: "Stable row" })]));
    renderHistory();
    await screen.findByText("Stable row");
    mockGetWorkflows.mockRejectedValueOnce(new Error("blip"));

    await user.click(screen.getByRole("button", { name: "Refresh run history" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh run history" })).toBeEnabled());
    expect(screen.getByText("Stable row")).toBeInTheDocument();
  });

  it("does nothing on manual refresh when the token has gone away", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Stable row" })]));
    renderHistory();
    await screen.findByText("Stable row");
    mockGetToken.mockReturnValue(null);

    await user.click(screen.getByRole("button", { name: "Refresh run history" }));

    expect(mockGetWorkflows).toHaveBeenCalledTimes(1);
  });

  it("counts down once an interval is chosen, refreshes at zero and restarts", async () => {
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Stable row" })]));
    renderHistory();
    await screen.findByText("Stable row");

    // Only the countdown interval is faked; setTimeout stays real for user-event / RTL polling.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Auto-refresh interval" }), "10000");
    expect(screen.getByRole("button", { name: /next auto-refresh in 10s/ })).toBeInTheDocument();

    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(screen.getByRole("button", { name: /next auto-refresh in 6s/ })).toBeInTheDocument();

    const before = mockGetWorkflows.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(mockGetWorkflows.mock.calls.length).toBeGreaterThan(before);
    expect(screen.getByRole("button", { name: /next auto-refresh in 10s/ })).toBeInTheDocument();
  });

  it("restarts the countdown on a manual refresh while auto-refresh is on, and stops when turned off", async () => {
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Stable row" })]));
    renderHistory();
    await screen.findByText("Stable row");

    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const user = userEvent.setup();
    const select = screen.getByRole("combobox", { name: "Auto-refresh interval" });
    await user.selectOptions(select, "30000");
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

    await user.click(screen.getByRole("button", { name: /next auto-refresh in 25s/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("button", { name: /next auto-refresh in 30s/ })).toBeInTheDocument();

    await user.selectOptions(select, "0");
    expect(screen.getByRole("button", { name: "Refresh run history" })).toBeInTheDocument();
  });

  it("silently re-fetches when the parent hands in a new recentRuns reference", async () => {
    const first: WorkflowRun[] = [];
    mockGetWorkflows.mockResolvedValueOnce(page([makeRun({ id: "a", title: "Original row" })]));
    const { rerender } = renderHistory({ recentRuns: first });
    await screen.findByText("Original row");
    mockGetWorkflows.mockResolvedValueOnce(page([makeRun({ id: "b", title: "Diverted row" })]));

    rerender(<WorkflowHistory onBack={vi.fn()} recentRuns={[]} />);

    expect(await screen.findByText("Diverted row")).toBeInTheDocument();
    expect(screen.queryByText("Loading workflows")).not.toBeInTheDocument();
  });

  it("does not re-fetch when recentRuns keeps the same reference", async () => {
    const same: WorkflowRun[] = [];
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Original row" })]));
    const { rerender } = renderHistory({ recentRuns: same });
    await screen.findByText("Original row");

    rerender(<WorkflowHistory onBack={vi.fn()} recentRuns={same} />);

    expect(mockGetWorkflows).toHaveBeenCalledTimes(1);
  });

  it("skips the silent re-fetch without a token and swallows a failed one", async () => {
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Original row" })]));
    const { rerender } = renderHistory({ recentRuns: [] });
    await screen.findByText("Original row");

    mockGetToken.mockReturnValue(null);
    rerender(<WorkflowHistory onBack={vi.fn()} recentRuns={[]} />);
    expect(mockGetWorkflows).toHaveBeenCalledTimes(1);

    mockGetToken.mockReturnValue("test-token");
    mockGetWorkflows.mockRejectedValueOnce(new Error("blip"));
    rerender(<WorkflowHistory onBack={vi.fn()} recentRuns={[]} />);
    await waitFor(() => expect(mockGetWorkflows).toHaveBeenCalledTimes(2));

    expect(screen.getByText("Original row")).toBeInTheDocument();
  });
});

// ─── Opening a run ───────────────────────────────────────────────────────────
describe("WorkflowHistory list — opening a run", () => {
  it("jumps to the live pipeline when the clicked run is the active one", async () => {
    const user = userEvent.setup();
    const onViewRunningPipeline = vi.fn();
    const onOpenRun = vi.fn();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "live", title: "Live run", status: "running" })]));
    renderHistory({ activeRunId: "live", onViewRunningPipeline, onOpenRun });

    await user.click(await screen.findByRole("button", { name: /^Open Live run/ }));

    expect(onViewRunningPipeline).toHaveBeenCalledWith("live");
    expect(onOpenRun).not.toHaveBeenCalled();
  });

  it("falls through to onOpenRun when the clicked run is not the active one", async () => {
    const user = userEvent.setup();
    const onViewRunningPipeline = vi.fn();
    const onOpenRun = vi.fn();
    const run = makeRun({ id: "other", title: "Other run" });
    mockGetWorkflows.mockResolvedValue(page([run]));
    renderHistory({ activeRunId: "live", onViewRunningPipeline, onOpenRun });

    await user.click(await screen.findByRole("button", { name: /^Open Other run/ }));

    expect(onViewRunningPipeline).not.toHaveBeenCalled();
    expect(onOpenRun).toHaveBeenCalledWith(run);
  });

  it("opens the internal detail for a run with a stored output when no shared run screen is wired", async () => {
    const user = userEvent.setup();
    const run = makeRun({ id: "d1", title: "Detail run", output: "# Notes\nsome markdown" });
    mockGetWorkflows.mockResolvedValue(page([run]));
    mockGetRunSummary.mockResolvedValue({
      id: "d1", title: "Detail run", type: "prototype", status: "completed", duration: null, agent_count: 0,
      token_usage: {}, error: null, agents: [], root_id: "d1", members: [],
    });
    renderHistory();

    await user.click(await screen.findByRole("button", { name: /^Open Detail run/ }));

    expect(await screen.findByRole("region", { name: "Run detail" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Detail run" })).toBeInTheDocument();
  });
});

// ─── Delete flow ─────────────────────────────────────────────────────────────
describe("WorkflowHistory list — delete", () => {
  async function openDeleteDialog(user: ReturnType<typeof userEvent.setup>, title: string) {
    await screen.findByText(title);
    await user.click(screen.getByRole("button", { name: "Run actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    return screen.findByRole("dialog");
  }

  it("names the run in the confirmation dialog and focuses the primary action", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Doomed run" })]));
    renderHistory();

    const dialog = await openDeleteDialog(user, "Doomed run");

    expect(within(dialog).getByText(/“Doomed run” and all its output will be permanently deleted\./)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Delete" })).toHaveFocus();
  });

  it("uses generic copy when the run has no title to show", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "" })]));
    renderHistory();

    await screen.findByRole("button", { name: "Run actions" });
    await user.click(screen.getByRole("button", { name: "Run actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText("The workflow run and all its output will be permanently deleted.")).toBeInTheDocument();
  });

  it("deletes the run, removes it from the list and decrements the total", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(
      page([makeRun({ id: "a", title: "Doomed run" }), makeRun({ id: "b", title: "Survivor" })]),
    );
    renderHistory();
    await screen.findByText("Survivor");
    const doomedRow = screen.getByRole("button", { name: /^Open Doomed run/ });
    await user.click(within(doomedRow).getByRole("button", { name: "Run actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));

    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.queryByText("Doomed run")).not.toBeInTheDocument());
    expect(mockDeleteWorkflow).toHaveBeenCalledWith("test-token", "a");
    expect(screen.getByText("Survivor")).toBeInTheDocument();
    expect(screen.getByText("1 runs")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows an error and keeps the dialog open when the delete fails, clearing it on cancel", async () => {
    const user = userEvent.setup();
    mockDeleteWorkflow.mockRejectedValue(new Error("500"));
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Doomed run" })]));
    renderHistory();
    const dialog = await openDeleteDialog(user, "Doomed run");

    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    // Re-query: the test motion shim hands out a fresh component per render, so the dialog node is replaced.
    expect(await screen.findByText("Failed to delete run. Please try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Open Doomed run/ })).toBeInTheDocument();

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Run actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(within(await screen.findByRole("dialog")).queryByText(/Failed to delete/)).not.toBeInTheDocument();
  });

  it("closes the dialog on Escape without deleting", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Doomed run" })]));
    renderHistory();
    await openDeleteDialog(user, "Doomed run");

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockDeleteWorkflow).not.toHaveBeenCalled();
  });

  it("closes the dialog when the backdrop is clicked but not when the dialog itself is", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Doomed run" })]));
    renderHistory();
    const dialog = await openDeleteDialog(user, "Doomed run");

    await user.click(within(dialog).getByText("Delete workflow"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // The backdrop is the dialog's non-interactive parent; clicking it is the
    // pointer-equivalent of "click outside".
    await user.click(dialog.parentElement as HTMLElement);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not call the API on confirm when the token is gone", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Doomed run" })]));
    renderHistory();
    const dialog = await openDeleteDialog(user, "Doomed run");
    mockGetToken.mockReturnValue(null);

    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(mockDeleteWorkflow).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("toggles the row menu closed when its trigger is clicked again", async () => {
    const user = userEvent.setup();
    mockGetWorkflows.mockResolvedValue(page([makeRun({ id: "a", title: "Doomed run" })]));
    renderHistory();
    await screen.findByText("Doomed run");

    await user.click(screen.getByRole("button", { name: "Run actions" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run actions" }));

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

// --- Family expansion --------------------------------------------------------
describe("WorkflowHistory list — revision families", () => {
  it("expands a multi-version family to show every version and collapses it again", async () => {
    const user = userEvent.setup();
    const root = makeRun({ id: "root", title: "Root cut", createdAt: ago(2 * 60 * 60_000) });
    const rev = makeRun({
      id: "rev", title: "Second cut", type: "prototype_revision" as WorkflowRun["type"],
      parentRunId: "root", rootRunId: "root", createdAt: ago(60_000),
    });
    mockGetWorkflows.mockResolvedValue(page([root, rev]));
    renderHistory();
    await screen.findByRole("button", { name: "Show versions" });
    expect(screen.queryByRole("button", { name: /^Version 1,/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show versions" }));
    expect(screen.getByRole("button", { name: /^Version 1,/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Version 2,/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Collapse versions" }));
    expect(screen.queryByRole("button", { name: /^Version 1,/ })).not.toBeInTheDocument();
  });
});
