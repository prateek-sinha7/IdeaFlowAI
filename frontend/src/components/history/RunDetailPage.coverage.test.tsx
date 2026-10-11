/**
 * RunDetailPage — branch/interaction coverage: auth + error + empty states,
 * live-pipeline affordance, manual / auto refresh, version switching (standalone
 * and caller-owned), tab switching, agent-row variants and the KPI strip.
 *
 * Mocks only the API boundary (getToken / getRunSummary) and the motion shim;
 * VersionTimeline, DegradedRunAffordance, Tabs and Badge render for real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { RunSummary } from "@/lib/api";
import type { FamilyMember } from "@/types/index";
import globalReducer from "@/store/slices/globalSlice";
import { renderWithProviders } from "@/test/renderWithProviders";

const mockGetToken = vi.fn<() => string | null>(() => "test-token");
const mockGetRunSummary =
  vi.fn<(token: string, runId: string) => Promise<RunSummary>>();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => mockGetToken(),
    getRunSummary: (token: string, runId: string) => mockGetRunSummary(token, runId),
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

function member(overrides: Partial<FamilyMember> & { id: string }): FamilyMember {
  return {
    type: "prototype",
    title: overrides.id,
    status: "completed",
    revision_index: 1,
    parent_run_id: null,
    created_at: "2026-07-01T10:00:00",
    completed_at: "2026-07-01T10:02:00",
    ...overrides,
  };
}

function summary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    id: "run-1",
    title: "Quarterly report",
    type: "prototype",
    status: "completed",
    duration: null,
    agent_count: 0,
    token_usage: {},
    error: null,
    agents: [],
    root_id: "run-1",
    members: [member({ id: "run-1" })],
    ...overrides,
  };
}

const FAMILY: FamilyMember[] = [
  member({ id: "run-2", title: "Second draft", revision_index: 2, parent_run_id: "run-1", git_tag: "v2" }),
  member({ id: "run-1", title: "First draft", revision_index: 1 }),
];

beforeEach(() => {
  vi.clearAllMocks();
  mockGetToken.mockReturnValue("test-token");
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("RunDetailPage — load states", () => {
  it("shows a busy skeleton while the summary is still loading", () => {
    mockGetRunSummary.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(screen.getByRole("region", { name: "Run detail" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Back to history" })).toBeInTheDocument();
  });

  it("shows 'Not authenticated.' and never calls the API when there is no token", async () => {
    mockGetToken.mockReturnValue(null);
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText("Not authenticated.")).toBeInTheDocument();
    expect(screen.getByText("Could not load this run")).toBeInTheDocument();
    expect(mockGetRunSummary).not.toHaveBeenCalled();
  });

  it("shows the rejection message when the summary request fails with an Error", async () => {
    mockGetRunSummary.mockRejectedValue(new Error("Run not found"));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText("Run not found")).toBeInTheDocument();
  });

  it("falls back to a generic message when the rejection carries no message", async () => {
    mockGetRunSummary.mockRejectedValue(undefined);
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText("Could not load this run.")).toBeInTheDocument();
  });

  it("shows the 'unavailable' copy when the API resolves with no summary", async () => {
    mockGetRunSummary.mockResolvedValue(null as unknown as RunSummary);
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText("The run summary is unavailable.")).toBeInTheDocument();
  });

  it("calls onBack from the error state's back button", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    mockGetRunSummary.mockRejectedValue(new Error("nope"));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={onBack} />);
    await screen.findByText("nope");

    await user.click(screen.getByRole("button", { name: "Back to history" }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("does not report an error or crash when unmounted before the request settles", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    let rejectLater: (e: Error) => void = () => {};
    mockGetRunSummary.mockReturnValue(
      new Promise<RunSummary>((_resolve, reject) => {
        rejectLater = reject;
      }),
    );
    const { unmount } = renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    unmount();
    await act(async () => {
      rejectLater(new Error("late failure"));
    });

    expect(errorSpy).not.toHaveBeenCalled();
  });

  it("refetches the new run when the caller changes runId", async () => {
    mockGetRunSummary.mockImplementation(async (_t, id) => summary({ id, title: `Title for ${id}` }));
    const { rerender } = renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    expect(await screen.findByRole("heading", { name: "Title for run-1" })).toBeInTheDocument();

    rerender(<RunDetailPage runId="run-7" onBack={() => {}} />);

    expect(await screen.findByRole("heading", { name: "Title for run-7" })).toBeInTheDocument();
    expect(mockGetRunSummary).toHaveBeenLastCalledWith("test-token", "run-7");
  });
});

describe("RunDetailPage — header, KPI strip and chain lineage", () => {
  it("omits the KPI strip when there are no tokens and no duration", async () => {
    mockGetRunSummary.mockResolvedValue(summary({ agent_count: 3 }));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    expect(screen.queryByText("3 agents")).not.toBeInTheDocument();
    expect(screen.queryByText(/total$/)).not.toBeInTheDocument();
  });

  it("shows only duration and agent count when tokens are zero but duration exists", async () => {
    mockGetRunSummary.mockResolvedValue(summary({ duration: 45, agent_count: 2 }));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText("45s")).toBeInTheDocument();
    expect(screen.getByText("2 agents")).toBeInTheDocument();
    expect(screen.queryByText(/ input$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ output$/)).not.toBeInTheDocument();
  });

  it("shows token totals without a duration chip when only tokens exist", async () => {
    mockGetRunSummary.mockResolvedValue(
      summary({
        duration: null,
        agent_count: 1,
        token_usage: { total_tokens: 2_500_000, total_input_tokens: 2_000_000, total_output_tokens: 500 },
      }),
    );
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText("2.5M")).toBeInTheDocument();
    expect(screen.getByText("2.0M input")).toBeInTheDocument();
    expect(screen.getByText("500 output")).toBeInTheDocument();
    expect(screen.getByText("1 agents")).toBeInTheDocument();
  });

  it("renders the chain lineage badge, resolving the workflow name from the catalog", async () => {
    mockGetRunSummary.mockResolvedValue(
      summary({
        chain_context_installed: true,
        chain_source_workflow_id: "user_stories",
        chain_source_short_id: "abc123",
        chain_source_visible_tag: "v1",
      }),
    );
    const base = globalReducer(undefined, { type: "@@init" });
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />, {
      preloadedState: {
        global: {
          ...base,
          workflows: [
            { id: "user_stories", name: "User Stories", short_name: "Stories", display_name: "User Stories", description: "", step_count: 1, steps: [] },
          ] as unknown as typeof base.workflows,
        },
      },
    });

    expect(await screen.findByLabelText("Chained from Stories v1")).toBeInTheDocument();
  });

  it("does not render the chain lineage badge for a run without an installed chain", async () => {
    mockGetRunSummary.mockResolvedValue(summary({ chain_context_installed: false, chain_source_workflow_id: "user_stories" }));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    expect(screen.queryByLabelText(/^Chained from/)).not.toBeInTheDocument();
  });
});

describe("RunDetailPage — live pipeline affordance", () => {
  it("offers 'View live pipeline' when this run is the active one and fires the callback with its id", async () => {
    const user = userEvent.setup();
    const onView = vi.fn();
    mockGetRunSummary.mockResolvedValue(summary({ id: "run-live", status: "running" }));
    renderWithProviders(
      <RunDetailPage runId="run-live" onBack={() => {}} activeRunId="run-live" onViewRunningPipeline={onView} />,
    );

    await user.click(await screen.findByRole("button", { name: /view live pipeline/i }));

    expect(onView).toHaveBeenCalledWith("run-live");
  });

  it("hides the affordance when a different run is the active one", async () => {
    mockGetRunSummary.mockResolvedValue(summary({ id: "run-1" }));
    renderWithProviders(
      <RunDetailPage runId="run-1" onBack={() => {}} activeRunId="other" onViewRunningPipeline={() => {}} />,
    );
    await screen.findByRole("heading", { name: "Quarterly report" });

    expect(screen.queryByRole("button", { name: /view live pipeline/i })).not.toBeInTheDocument();
  });

  it("hides the affordance when no handler is supplied even if the run is active", async () => {
    mockGetRunSummary.mockResolvedValue(summary({ id: "run-1" }));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} activeRunId="run-1" />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    expect(screen.queryByRole("button", { name: /view live pipeline/i })).not.toBeInTheDocument();
  });
});

describe("RunDetailPage — Agents tab", () => {
  it("renders per-agent rows with icon, initials fallback, role, duration, tokens and error badge", async () => {
    mockGetRunSummary.mockResolvedValue(
      summary({
        agents: [
          { agent_id: "a1", name: "Domain Analyst", role: "Analysis", icon: "🧠", duration: 12, total_tokens: 1500 },
          { agent_id: "a2", name: "Prototype Builder", duration: null, total_tokens: 0, error: "boom" },
          { agent_id: "a3" },
        ],
      }),
    );
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    const panel = await screen.findByRole("tabpanel", { name: "Agents" });
    const rows = within(panel).getAllByRole("listitem");
    expect(rows).toHaveLength(3);

    // Row 1: icon, role, formatted duration + tokens, "Done" badge.
    expect(within(rows[0]).getByText("🧠")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Analysis")).toBeInTheDocument();
    expect(within(rows[0]).getByText("12s")).toBeInTheDocument();
    expect(within(rows[0]).getByText("1.5K tok")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Done")).toBeInTheDocument();

    // Row 2: initials from name, no duration / tokens chips, errored agent → Failed.
    expect(within(rows[1]).getByText("PB")).toBeInTheDocument();
    expect(within(rows[1]).queryByText(/tok$/)).not.toBeInTheDocument();
    expect(within(rows[1]).getByText("Failed")).toBeInTheDocument();

    // Row 3: nameless agent shows the "Agent" label and the "A" initial.
    expect(within(rows[2]).getByText("Agent")).toBeInTheDocument();
    expect(within(rows[2]).getByText("A")).toBeInTheDocument();
  });

  it("shows 'No agent data' when a non-terminal run has no agents", async () => {
    mockGetRunSummary.mockResolvedValue(summary({ status: "running", agents: [] }));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText("No agent data")).toBeInTheDocument();
  });

  it("builds the failed-run banner from agents named in the error", async () => {
    mockGetRunSummary.mockResolvedValue(
      summary({
        status: "degraded",
        error: "Pipeline degraded — agent(s) failed: a1",
        agents: [{ agent_id: "a1", name: "Validation Agent" }, { name: "No id agent" }],
      }),
    );
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);

    expect(await screen.findByText(/did not complete successfully/i)).toBeInTheDocument();
    expect(screen.getByText(/Validation Agent/)).toBeInTheDocument();
  });
});

describe("RunDetailPage — Timeline tab and version switching", () => {
  it("switches to the Timeline tab and lists versions ordered by revision with tags and the active marker", async () => {
    const user = userEvent.setup();
    mockGetRunSummary.mockResolvedValue(summary({ id: "run-2", root_id: "run-1", members: FAMILY }));
    renderWithProviders(<RunDetailPage runId="run-2" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    await user.click(screen.getByRole("tab", { name: "Timeline" }));

    const panel = screen.getByRole("tabpanel", { name: "Timeline" });
    const items = within(panel).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("v1")).toBeInTheDocument();
    expect(within(items[0]).getByText("First draft")).toBeInTheDocument();
    expect(within(items[1]).getByText("v2")).toBeInTheDocument();
    expect(within(items[1]).getByLabelText("Tagged v2")).toBeInTheDocument();
    expect(within(items[1]).getByRole("button")).toHaveAttribute("aria-current", "true");
    expect(within(items[0]).getByRole("button")).not.toHaveAttribute("aria-current");
  });

  it("refetches that version when a timeline row is clicked and returns to the Agents tab on demand", async () => {
    const user = userEvent.setup();
    mockGetRunSummary.mockImplementation(async (_t, id) =>
      summary({ id, title: `Summary of ${id}`, root_id: "run-1", members: FAMILY }),
    );
    renderWithProviders(<RunDetailPage runId="run-2" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Summary of run-2" });
    await user.click(screen.getByRole("tab", { name: "Timeline" }));

    await user.click(within(screen.getByRole("tabpanel", { name: "Timeline" })).getByText("First draft"));

    expect(await screen.findByRole("heading", { name: "Summary of run-1" })).toBeInTheDocument();
    expect(mockGetRunSummary).toHaveBeenLastCalledWith("test-token", "run-1");

    await user.click(screen.getByRole("tab", { name: "Agents" }));
    expect(screen.getByRole("tabpanel", { name: "Agents" })).toBeInTheDocument();
  });

  it("switches this page's own summary when a version chip is chosen (standalone use)", async () => {
    const user = userEvent.setup();
    mockGetRunSummary.mockImplementation(async (_t, id) =>
      summary({ id, title: `Summary of ${id}`, root_id: "run-1", members: FAMILY }),
    );
    renderWithProviders(<RunDetailPage runId="run-2" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Summary of run-2" });

    await user.click(screen.getByRole("radio", { name: /^Version 1/ }));

    expect(await screen.findByRole("heading", { name: "Summary of run-1" })).toBeInTheDocument();
  });

  it("delegates version switching to the caller when onSelectVersion is supplied", async () => {
    const user = userEvent.setup();
    const onSelectVersion = vi.fn();
    mockGetRunSummary.mockResolvedValue(summary({ id: "run-2", root_id: "run-1", members: FAMILY }));
    renderWithProviders(<RunDetailPage runId="run-2" onBack={() => {}} onSelectVersion={onSelectVersion} />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    await user.click(screen.getByRole("radio", { name: /^Version 1/ }));

    expect(onSelectVersion).toHaveBeenCalledWith("run-1");
    expect(mockGetRunSummary).toHaveBeenCalledTimes(1);
  });
});

describe("RunDetailPage — refresh", () => {
  it("re-fetches in place on manual refresh without showing the loading skeleton", async () => {
    const user = userEvent.setup();
    mockGetRunSummary.mockResolvedValueOnce(summary({ title: "Before" }));
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Before" });
    mockGetRunSummary.mockResolvedValueOnce(summary({ title: "After" }));

    await user.click(screen.getByRole("button", { name: "Refresh run data" }));

    expect(await screen.findByRole("heading", { name: "After" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Run detail" })).not.toHaveAttribute("aria-busy");
  });

  it("disables the refresh button while a refresh is in flight and re-enables it afterwards", async () => {
    const user = userEvent.setup();
    mockGetRunSummary.mockResolvedValueOnce(summary());
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });
    let resolveRefresh: (s: RunSummary) => void = () => {};
    mockGetRunSummary.mockReturnValueOnce(new Promise<RunSummary>((r) => { resolveRefresh = r; }));

    await user.click(screen.getByRole("button", { name: "Refresh run data" }));
    expect(screen.getByRole("button", { name: "Refresh run data" })).toBeDisabled();

    await act(async () => {
      resolveRefresh(summary());
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh run data" })).toBeEnabled());
  });

  it("surfaces an error screen when a manual refresh fails", async () => {
    const user = userEvent.setup();
    mockGetRunSummary.mockResolvedValueOnce(summary());
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });
    mockGetRunSummary.mockRejectedValueOnce(new Error("refresh exploded"));

    await user.click(screen.getByRole("button", { name: "Refresh run data" }));

    expect(await screen.findByText("refresh exploded")).toBeInTheDocument();
  });

  it("does nothing on manual refresh when the token has gone away", async () => {
    const user = userEvent.setup();
    mockGetRunSummary.mockResolvedValue(summary());
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });
    mockGetToken.mockReturnValue(null);

    await user.click(screen.getByRole("button", { name: "Refresh run data" }));

    expect(mockGetRunSummary).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { name: "Quarterly report" })).toBeInTheDocument();
  });

  it("counts down after an interval is chosen, refreshes at zero, and restarts the countdown", async () => {
    mockGetRunSummary.mockResolvedValue(summary());
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    // Only the countdown interval is faked; setTimeout stays real so user-event / RTL polling keep working.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Auto-refresh interval" }), "10000");

    expect(screen.getByRole("button", { name: /next auto-refresh in 10s/ })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByRole("button", { name: /next auto-refresh in 7s/ })).toBeInTheDocument();

    const callsBeforeExpiry = mockGetRunSummary.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    expect(mockGetRunSummary.mock.calls.length).toBeGreaterThan(callsBeforeExpiry);
    expect(screen.getByRole("button", { name: /next auto-refresh in 10s/ })).toBeInTheDocument();
  });

  it("restarts the countdown on a manual refresh while auto-refresh is on", async () => {
    mockGetRunSummary.mockResolvedValue(summary());
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    // Only the countdown interval is faked; setTimeout stays real so user-event / RTL polling keep working.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Auto-refresh interval" }), "30000");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByRole("button", { name: /next auto-refresh in 25s/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /next auto-refresh in 25s/ }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByRole("button", { name: /next auto-refresh in 30s/ })).toBeInTheDocument();
  });

  it("stops the countdown when auto-refresh is switched back off", async () => {
    mockGetRunSummary.mockResolvedValue(summary());
    renderWithProviders(<RunDetailPage runId="run-1" onBack={() => {}} />);
    await screen.findByRole("heading", { name: "Quarterly report" });

    // Only the countdown interval is faked; setTimeout stays real so user-event / RTL polling keep working.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const user = userEvent.setup();
    const select = screen.getByRole("combobox", { name: "Auto-refresh interval" });
    await user.selectOptions(select, "15000");
    await user.selectOptions(select, "0");

    expect(screen.getByRole("button", { name: "Refresh run data" })).toBeInTheDocument();
    expect(screen.getByText("Refresh")).toBeInTheDocument();
  });
});
