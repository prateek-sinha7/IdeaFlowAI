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
import type { AnalyticsSummary, CapabilityModelEntry, CapabilitiesPalette } from "@/lib/api";

const mockGetToken = vi.fn(() => "test-token");
const mockGetAnalyticsSummary =
  vi.fn<(token: string, range: string) => Promise<AnalyticsSummary>>();
const mockGetPreferences = vi.fn(() =>
  Promise.resolve({ preferred_model: null, available_models: [] }),
);
const mockGetWorkflows = vi.fn(() => Promise.resolve([]));
// RFN-002b — getCapabilities is called on mount to build the model catalog map.
// Return an empty catalog so model-label lookups degrade to raw id (not under test here).
// The return annotation is load-bearing: without it the empty array literal
// infers `model_catalog: never[]`, and the populated-catalog override in
// `renderWithModel` below cannot be assigned to it. Kept as a baked-in
// implementation rather than a `mockResolvedValue` so that a `mockReset()`
// restores this empty-catalog default instead of wiping it to `undefined`.
const mockGetCapabilities = vi.fn(
  (): Promise<CapabilitiesPalette> =>
    Promise.resolve({ capabilities: [], model_catalog: [] }),
);

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => ({
    get: vi.fn(() => null),
  }),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getAnalyticsSummary: (token: string, range: string) =>
    mockGetAnalyticsSummary(token, range),
  getPreferences: () => mockGetPreferences(),
  getWorkflows: () => mockGetWorkflows(),
  getCapabilities: () => mockGetCapabilities(),
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
    // RFN-002 — agents defaults to empty; individual tests can override via spread.
    agents: [],
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
      // The card is RE-QUERIED on every check: the motion mock's Proxy hands
      // back a fresh component type per `motion.div` access, so each post-load
      // re-render (catalog fetch, Model Details seed) remounts the StatCard and
      // detaches any previously captured node.
      const avgRunCard = () =>
        screen.getByText("Avg / Run").closest("div.bg-surface-card") as HTMLElement;
      await screen.findByText("Avg / Run");
      await waitFor(() => {
        const card = avgRunCard();
        expect(card).not.toBeNull();
        expect(within(card).getByText("90")).toBeInTheDocument();
      });
      expect(within(avgRunCard()).queryByText("225")).not.toBeInTheDocument();
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

/**
 * ISS-369 — Daily Activity chart tooltip formatting parity.
 *
 * Every other number on the page is routed through formatTokens() (K/M
 * abbreviation) before display. The Daily Activity bar chart's per-bar
 * tooltip is the one series AnalyticsPage never assigns a `tip` to, so it
 * falls through to BarChart's raw-number default and renders the bare JS
 * integer instead.
 */
describe("AnalyticsPage — Daily Activity tooltip number formatting (ISS-369)", () => {
  it("ISS-369 — formats the per-bar tooltip with K/M abbreviation, not the raw integer", async () => {
    mockGetAnalyticsSummary.mockReset();
    mockGetAnalyticsSummary.mockResolvedValue(
      summary({
        daily: [
          {
            date: "2026-08-24",
            total: 3,
            completed: 3,
            failed: 0,
            input_tokens: 1_500_000,
            output_tokens: 864_478,
            total_tokens: 2_364_478,
          },
        ],
      }),
    );
    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );

    // Expected: formatTokens(2364478) === "2.4M", matching every other number
    // on the page (KPI tiles, By Pipeline Type, By Model).
    expect(await screen.findByText("Aug 24: 2.4M")).toBeInTheDocument();
    // The raw unformatted integer must NOT appear anywhere.
    expect(screen.queryByText(/2364478/)).not.toBeInTheDocument();
  });
});


/**
 * ISS-643 — By Agent section pipeline workflow chips.
 *
 * Each agent row must render a coloured chip for every entry in
 * pipeline_types, using the PIPELINE_LABELS map.  An empty pipeline_types
 * array renders the agent name only — no chip.  A multi-pipeline agent
 * renders one chip per type.
 */
/**
 * QA-PS-009 — Analytics Model Details reasoning row wording.
 *
 * ISS-667: Sonnet 5 DOES run with adaptive thinking (locked product decision,
 * 2026-09-17) — the row stays, but the app never sends an `effort` parameter,
 * so "(effort: max)" is a fabricated qualifier. Fix is the label text only:
 * "Adaptive", not "Adaptive (effort: max)".
 *
 * ISS-668: Opus 4.5 / Opus 4.6 matched `_THINKING_FRAGMENTS` ("opus-4") in
 * capabilities.py but NOT `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` in
 * model_factory.py, so their real runtime thinking type was "enabled" while
 * this row claimed "adaptive". CLOSED by spec 020, which deleted both tuples:
 * the row now reads `reasoning_mode` off the same catalog capability the
 * runtime maps from, so the two cannot disagree again. The xfail marker is
 * gone with it.
 *
 * Spec 020 also renamed the row "Thinking" → "Reasoning" and its budget-mode
 * value "Enabled" → "Budget": the row can now read "Effort (none–max)" for a
 * GPT model, and GPT's effort is not extended thinking.
 */
describe("AnalyticsPage — Model Details Thinking row wording (QA-PS-009)", () => {
  beforeEach(() => {
    mockGetAnalyticsSummary.mockReset();
  });

  async function renderWithModel(modelId: string, catalogEntry: Record<string, unknown>) {
    // mockResolvedValueOnce — leaves the module-level empty-catalog default
    // (mockGetCapabilities) intact for every other describe block in this file.
    mockGetCapabilities.mockResolvedValueOnce({
      capabilities: [],
      model_catalog: [{ id: modelId, ...catalogEntry } as CapabilityModelEntry],
    });
    mockGetAnalyticsSummary.mockResolvedValue(
      summary({
        models: [{ model_id: modelId, count: 1, total_tokens: 100, cost: 0.01 }],
      }),
    );
    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );
    // Mirrors the component's own shortLabel(): strips "Claude " and a
    // trailing "(EU)"/"(US)" region suffix before rendering the card header.
    const shortName = (catalogEntry.label as string)
      .replace(/^Claude\s+/i, "")
      .replace(/\s*\((EU|US|APAC|Global)\)\s*$/i, "")
      .trim();
    // The single/top model card auto-expands on load (no click needed) —
    // see the "Seed the first catalog-matched model as expanded" effect.
    const detailsHeading = await screen.findByText("Model Details");
    const panel = detailsHeading.closest("div.bg-surface-card") as HTMLElement;
    const nameSpan = await within(panel).findByText(shortName);
    const toggle = nameSpan.closest("button") as HTMLElement;
    await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "true"));
  }

  it("ISS-667 — Sonnet 5 shows 'Adaptive' with no fabricated effort qualifier", async () => {
    await renderWithModel("eu.anthropic.claude-sonnet-5", {
      label: "Claude Sonnet 5 (EU)",
      tier: "standard",
      context_window: 200000,
      reasoning_mode: "adaptive",
      reasoning_levels: ["none", "on"],
    });

    const thinkingLabel = await screen.findByText("Reasoning");
    const row = thinkingLabel.closest("div") as HTMLElement;
    expect(within(row).getByText("Adaptive")).toBeInTheDocument();
    expect(screen.queryByText(/effort: max/)).not.toBeInTheDocument();
  });

  it("ISS-668 — Opus 4.5 shows 'Budget', not 'Adaptive', matching its real runtime reasoning mode", async () => {
    await renderWithModel("eu.anthropic.claude-opus-4-5-20251101-v1:0", {
      label: "Claude Opus 4.5 (EU)",
      tier: "premium",
      context_window: 200000,
      reasoning_mode: "budget",
      reasoning_levels: ["none", "on"],
    });

    const thinkingLabel = await screen.findByText("Reasoning");
    const row = thinkingLabel.closest("div") as HTMLElement;
    expect(within(row).getByText("Budget")).toBeInTheDocument();
    expect(within(row).queryByText(/Adaptive/)).not.toBeInTheDocument();
  });

  it("a GPT model shows its effort range, not a thinking type", async () => {
    await renderWithModel("global.openai.gpt-5.6-luna", {
      label: "GPT-5.6 Luna",
      tier: "fast",
      context_window: 1000000,
      reasoning_mode: "effort",
      reasoning_levels: ["none", "low", "medium", "high", "xhigh", "max"],
    });

    const thinkingLabel = await screen.findByText("Reasoning");
    const row = thinkingLabel.closest("div") as HTMLElement;
    expect(within(row).getByText("Effort (none–max)")).toBeInTheDocument();
    expect(within(row).queryByText(/Adaptive|Budget/)).not.toBeInTheDocument();
  });

  it("renders no reasoning row for a model that has no reasoning control", async () => {
    // Synthetic: no catalog model has reasoning_mode "none" since Haiku 3.5 was
    // removed (2026-09-22), but the row must still not render for one.
    await renderWithModel("eu.anthropic.claude-no-reasoning-v1:0", {
      label: "No-Reasoning Model",
      tier: "fast",
      context_window: 200000,
      reasoning_mode: "none",
      reasoning_levels: [],
    });

    expect(screen.queryByText("Reasoning")).not.toBeInTheDocument();
  });
});

describe("AnalyticsPage — By Agent pipeline chips (ISS-643)", () => {
  beforeEach(() => {
    mockGetAnalyticsSummary.mockReset();
  });

  // The agent name and chip labels render in their SOURCE case ("Build Agent",
  // "Prototype"); the all-caps look is CSS `uppercase`, which jsdom does not
  // apply to text content. Queries therefore use the source strings.
  //
  // Chip labels such as "Prototype" also appear in the pipeline <select> and the
  // By Pipeline Type rollup, so every chip query is scoped to the agent's own
  // name+chip row (the name span's parent). The row is re-queried on each call:
  // the motion mock remounts motion.div subtrees on re-render, detaching nodes.
  const agentChipRow = (agentName: string) =>
    screen.getByText(agentName).parentElement as HTMLElement;

  it("renders a workflow chip for a single-pipeline agent", async () => {
    mockGetAnalyticsSummary.mockResolvedValue(
      summary({
        agents: [
          {
            agent_id: "build-agent",
            agent_name: "Build Agent",
            count: 3,
            total_tokens: 900,
            input_tokens: 450,
            output_tokens: 450,
            cost: 0.09,
            pipeline_types: ["prototype"],
          },
        ],
      }),
    );

    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );

    // Agent name visible.
    await screen.findByText("Build Agent");
    await waitFor(() => {
      expect(screen.getByText("Build Agent")).toBeInTheDocument();
      const row = agentChipRow("Build Agent");
      // Exactly one chip (name + 1 chip), showing the PIPELINE_LABELS label.
      expect(row.children).toHaveLength(2);
      expect(within(row).getByText("Prototype")).toBeInTheDocument();
    });
  });

  it("renders no pipeline chip when pipeline_types is empty", async () => {
    mockGetAnalyticsSummary.mockResolvedValue(
      summary({
        agents: [
          {
            agent_id: "legacy-agent",
            agent_name: "Legacy Agent",
            count: 1,
            total_tokens: 200,
            input_tokens: 100,
            output_tokens: 100,
            cost: 0.02,
            pipeline_types: [],
          },
        ],
      }),
    );

    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );

    await screen.findByText("Legacy Agent");
    await waitFor(() => {
      expect(screen.getByText("Legacy Agent")).toBeInTheDocument();
      const row = agentChipRow("Legacy Agent");
      // No chip elements for this agent beyond the name.
      expect(row.children).toHaveLength(1);
      // "User Stories", "Prototype", "Presentation" etc. must be absent.
      expect(within(row).queryByText("Prototype")).not.toBeInTheDocument();
      expect(within(row).queryByText("Presentation")).not.toBeInTheDocument();
      expect(within(row).queryByText("User Stories")).not.toBeInTheDocument();
    });
  });

  it("renders one chip per pipeline for a multi-pipeline agent", async () => {
    mockGetAnalyticsSummary.mockResolvedValue(
      summary({
        agents: [
          {
            agent_id: "shared-agent",
            agent_name: "Shared Agent",
            count: 5,
            total_tokens: 2000,
            input_tokens: 1000,
            output_tokens: 1000,
            cost: 0.20,
            pipeline_types: ["ppt", "prototype", "user_stories"],
          },
        ],
      }),
    );

    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );

    await screen.findByText("Shared Agent");
    await waitFor(() => {
      expect(screen.getByText("Shared Agent")).toBeInTheDocument();
      const row = agentChipRow("Shared Agent");
      // All three pipeline labels rendered — one chip each (name + 3 chips).
      expect(row.children).toHaveLength(4);
      expect(within(row).getByText("Presentation")).toBeInTheDocument();
      expect(within(row).getByText("Prototype")).toBeInTheDocument();
      expect(within(row).getByText("User Stories")).toBeInTheDocument();
    });
  });

  it("uses PIPELINE_LABELS friendly name and normalises revision variants", async () => {
    mockGetAnalyticsSummary.mockResolvedValue(
      summary({
        agents: [
          {
            agent_id: "ppt-agent",
            agent_name: "PPT Agent",
            count: 2,
            total_tokens: 500,
            input_tokens: 250,
            output_tokens: 250,
            cost: 0.05,
            // ppt_revision should normalise to "Presentation" via normalizeType.
            pipeline_types: ["ppt_revision"],
          },
        ],
      }),
    );

    render(<AnalyticsPage onBack={() => {}} />);
    await waitFor(() =>
      expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "30d"),
    );

    await screen.findByText("PPT Agent");
    await waitFor(() => {
      expect(screen.getByText("PPT Agent")).toBeInTheDocument();
      const row = agentChipRow("PPT Agent");
      // ppt_revision normalises to ppt → PIPELINE_LABELS["ppt"] = "Presentation".
      expect(within(row).getByText("Presentation")).toBeInTheDocument();
      // The raw "ppt_revision" string must not appear as a chip label.
      expect(within(row).queryByText("ppt_revision")).not.toBeInTheDocument();
    });
  });
});
