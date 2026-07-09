import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { RunSummary } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// Mocks. Hoisted by vitest before module imports.
//
// Mock ONLY the api layer (getToken + getRunSummary) and the motion proxy —
// the shared surfaces (VersionTimeline, DegradedRunAffordance) render for REAL
// so this test PROVES they are reused, not re-implemented (D-15 / no dual impl).
// ─────────────────────────────────────────────────────────────────

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

// Motion proxy — preserves the underlying HTML tag so role/text/label queries
// keep working (same idiom as SavedWorkflowsPage.test / HomeLaunchGrid.test).
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
import { RunDetailPage } from "./RunDetailPage";

// ─────────────────────────────────────────────────────────────────
// Fixtures.
// ─────────────────────────────────────────────────────────────────
const COMPLETED: RunSummary = {
  id: "run-2",
  title: "My prototype run",
  type: "prototype",
  status: "completed",
  duration: 125,
  agent_count: 2,
  token_usage: {
    total_input_tokens: 1200,
    total_output_tokens: 800,
    total_tokens: 2000,
  },
  error: null,
  agents: [
    { agent_id: "domain-analyst", name: "Domain Analyst", role: "Analysis", icon: "🧠", duration: 12, total_tokens: 1000 },
    { agent_id: "prototype-build", name: "Prototype Builder", role: "Build", icon: "🔨", duration: 40, total_tokens: 1000 },
  ],
  root_id: "run-1",
  members: [
    { id: "run-1", type: "prototype", title: "v1", status: "completed", revision_index: 1, parent_run_id: null, created_at: "2026-07-01T10:00:00", completed_at: "2026-07-01T10:02:00" },
    { id: "run-2", type: "prototype_revision", title: "v2", status: "completed", revision_index: 2, parent_run_id: "run-1", created_at: "2026-07-01T11:00:00", completed_at: "2026-07-01T11:02:00" },
  ],
};

const FAILED: RunSummary = {
  id: "run-9",
  title: "Broken run",
  type: "prototype",
  status: "failed",
  duration: 30,
  agent_count: 1,
  token_usage: { total_input_tokens: 100, total_output_tokens: 0, total_tokens: 100 },
  error: "Pipeline degraded — agent(s) failed: prototype-build",
  agents: [
    { agent_id: "prototype-build", name: "Prototype Builder", role: "Build", icon: "🔨", duration: 30, total_tokens: 100 },
  ],
  root_id: "run-9",
  members: [
    { id: "run-9", type: "prototype", title: "Broken run", status: "failed", revision_index: 1, parent_run_id: null, created_at: "2026-07-01T10:00:00", completed_at: null },
  ],
};

const CANCELLED: RunSummary = { ...FAILED, id: "run-c", title: "Stopped run", status: "cancelled", error: null };

// Retired-palette guard: no hexes / fonts from the pre-Phase-32 palette may
// appear in the class strings RunDetailPage itself renders (token authority).
const RETIRED = /#1B2A4A|#2563eb|#f5f5f0|\bInter\b|\bFraunces\b|\bJetBrains\b/;

beforeEach(() => {
  vi.clearAllMocks();
  mockGetToken.mockReturnValue("test-token");
});

describe("RunDetailPage", () => {
  it("completed run → KPI stats + per-agent breakdown + VersionTimeline render off getRunSummary", async () => {
    mockGetRunSummary.mockResolvedValue(COMPLETED);
    render(<RunDetailPage runId="run-2" onBack={() => {}} />);

    // KPI strip: total / input / output tokens (fmt M/K formatter) + duration.
    expect(await screen.findByText(/2\.0K/)).toBeInTheDocument();   // total
    expect(screen.getByText(/1\.2K/)).toBeInTheDocument();          // input
    expect(screen.getByText(/\b800\b/)).toBeInTheDocument();        // output
    expect(screen.getByText(/2m 5s/)).toBeInTheDocument();          // duration 125s

    // Per-agent breakdown cards.
    expect(screen.getByText("Domain Analyst")).toBeInTheDocument();
    expect(screen.getByText("Prototype Builder")).toBeInTheDocument();

    // Reused VersionTimeline (>=2 members → radiogroup with v1/v2).
    expect(screen.getByRole("radiogroup", { name: /workflow versions/i })).toBeInTheDocument();
    const versionRadios = screen.getAllByRole("radio");
    expect(versionRadios).toHaveLength(2);
    expect(versionRadios[0]).toHaveAccessibleName(/version 1/i);
    expect(versionRadios[1]).toHaveAccessibleName(/version 2/i);

    // Fed by the owner JWT.
    expect(mockGetRunSummary).toHaveBeenCalledWith("test-token", "run-2");
  });

  it("failed run → reused DegradedRunAffordance banner renders (keyed on generic status)", async () => {
    mockGetRunSummary.mockResolvedValue(FAILED);
    const { container } = render(<RunDetailPage runId="run-9" onBack={() => {}} />);

    expect(await screen.findByText(/did not complete successfully/i)).toBeInTheDocument();
    // Failed-agent id parsed from the generic error string + resolved to a name.
    expect(screen.getByText(/Prototype Builder/)).toBeInTheDocument();

    // Retired-palette guard on the rendered frame (single-member → no timeline
    // subtree, so this is RunDetailPage's own chrome + DegradedRunAffordance).
    expect(RETIRED.test(container.innerHTML)).toBe(false);
  });

  it("cancelled run → DegradedRunAffordance shows the cancelled copy", async () => {
    mockGetRunSummary.mockResolvedValue(CANCELLED);
    render(<RunDetailPage runId="run-c" onBack={() => {}} />);
    expect(await screen.findByText(/this run was cancelled/i)).toBeInTheDocument();
  });

  it("fetch error → graceful error state, no crash", async () => {
    mockGetRunSummary.mockRejectedValue(new Error("boom"));
    render(<RunDetailPage runId="run-x" onBack={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/could not load|failed to load|error/i)).toBeInTheDocument(),
    );
  });

  it("back control is keyboard/aria accessible", async () => {
    mockGetRunSummary.mockResolvedValue(COMPLETED);
    render(<RunDetailPage runId="run-2" onBack={() => {}} />);
    await screen.findByText("My prototype run");
    const back = screen.getByRole("button", { name: /back/i });
    expect(back).toBeInTheDocument();
  });
});
