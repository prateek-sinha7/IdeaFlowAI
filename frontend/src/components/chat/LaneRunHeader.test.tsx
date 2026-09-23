import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PipelineRunState } from "@/types/index";
import {
  LaneRunHeader,
  humanizeRunType,
  deriveLaneMeta,
  formatRelativeAge,
} from "./LaneRunHeader";

// ─── LaneRunHeader — the run-screen left-lane header ──────────────────────────
// Reproduces the mock's settled header composition (back link · type eyebrow ·
// status token · title · meta row) from GENERIC props. SC-001: the type is
// humanized from `pipeline_type` / `runType`, never branched on a workflow name;
// meta is derived from live `pipelineState`, never the mock's fixed values.

function ps(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "generic",
    agents: [],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

describe("humanizeRunType", () => {
  it("title-cases a snake/kebab type", () => {
    expect(humanizeRunType("app_builder")).toBe("App Builder");
    expect(humanizeRunType("user_stories")).toBe("User Stories");
  });

  it("drops a leading engine-domain segment (od_)", () => {
    expect(humanizeRunType("od_prototype")).toBe("Prototype");
    expect(humanizeRunType("od_ppt")).toBe("Ppt");
  });

  it("returns empty for a missing type", () => {
    expect(humanizeRunType(undefined)).toBe("");
    expect(humanizeRunType("")).toBe("");
  });
});

describe("deriveLaneMeta", () => {
  it("formats elapsed / agents / tokens from live pipelineState", () => {
    const meta = deriveLaneMeta(
      ps({
        totalDuration: 1446,
        agents: [1, 2, 3, 4, 5].map((n) => ({
          id: `a${n}`,
          name: `A${n}`,
          role: "",
          icon: "",
          status: "done",
          output: "",
          thinking: "",
          duration: null,
          error: null,
          index: n,
        })),
        completedCount: 5,
        totalTokens: 14_800_000,
      }),
    );
    expect(meta.elapsed).toBe("24m 6s");
    expect(meta.agents).toBe("5/5 agents");
    expect(meta.tokens).toBe("14.8M tokens");
  });

  it("omits empty parts (no agents / no tokens / no duration)", () => {
    const meta = deriveLaneMeta(ps());
    expect(meta.elapsed).toBe("");
    expect(meta.agents).toBe("");
    expect(meta.tokens).toBe("");
  });
});

describe("formatRelativeAge", () => {
  it("formats an ISO timestamp as a compact relative age", () => {
    const hoursAgo = (h: number) =>
      new Date(Date.now() - h * 3_600_000).toISOString();
    expect(formatRelativeAge(hoursAgo(23))).toBe("23h ago");
    expect(formatRelativeAge(hoursAgo(48))).toBe("2d ago");
    expect(formatRelativeAge(new Date(Date.now() - 5 * 60_000).toISOString())).toBe(
      "5m ago",
    );
    expect(formatRelativeAge(undefined)).toBe("");
  });
});

describe("LaneRunHeader", () => {
  it("SETTLED meta = relative-age · duration · tokens (no agent count)", () => {
    render(
      <LaneRunHeader
        runState="complete"
        runTitle="Modern Website Prototype Design Reference"
        pipelineState={ps({
          pipeline_type: "od_prototype",
          createdAt: new Date(Date.now() - 23 * 3_600_000).toISOString(),
          totalDuration: 1446,
          agents: [
            {
              id: "a1",
              name: "A1",
              role: "",
              icon: "",
              status: "done",
              output: "",
              thinking: "",
              duration: null,
              error: null,
              index: 1,
            },
          ],
          completedCount: 1,
          totalTokens: 14_800_000,
        })}
      />,
    );
    expect(screen.getByTestId("lane-run-type")).toHaveTextContent("Prototype");
    expect(screen.getByTestId("lane-run-title")).toHaveTextContent(
      "Modern Website Prototype Design Reference",
    );
    const meta = screen.getByTestId("lane-run-meta");
    expect(meta).toHaveTextContent("23h ago");
    expect(meta).toHaveTextContent("24m 6s");
    expect(meta).toHaveTextContent("14.8M tokens");
    // Settled omits the agent count.
    expect(meta).not.toHaveTextContent("agents");
  });

  it("LIVE/terminal meta = duration · N/M agents · tokens (no relative age)", () => {
    render(
      <LaneRunHeader
        runState="building"
        pipelineState={ps({
          createdAt: new Date(Date.now() - 23 * 3_600_000).toISOString(),
          totalDuration: 1446,
          completedCount: 3,
          totalTokens: 2_100_000,
          agents: [1, 2, 3, 4, 5].map((n) => ({
            id: `a${n}`,
            name: `A${n}`,
            role: "",
            icon: "",
            status: "done" as const,
            output: "",
            thinking: "",
            duration: null,
            error: null,
            index: n,
          })),
        })}
      />,
    );
    const meta = screen.getByTestId("lane-run-meta");
    expect(meta).toHaveTextContent("3/5 agents");
    expect(meta).toHaveTextContent("2.1M tokens");
    // Live omits the relative age.
    expect(meta).not.toHaveTextContent("ago");
  });

  it("shows a Done status token when complete", () => {
    render(<LaneRunHeader runState="complete" pipelineState={ps()} />);
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Done");
  });

  it("shows a Running phase pill while building", () => {
    render(<LaneRunHeader runState="building" pipelineState={ps({ isRunning: true })} />);
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Running");
  });

  it("shows a Clarifying phase pill in clarify", () => {
    render(<LaneRunHeader runState="clarify" pipelineState={ps()} />);
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Clarifying");
  });

  it("shows an Awaiting approval phase pill in gate", () => {
    render(<LaneRunHeader runState="gate" pipelineState={ps()} />);
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent(
      "Awaiting approval",
    );
  });

  it("shows a Failed status token for a failed terminal run", () => {
    render(
      <LaneRunHeader
        runState="terminal"
        pipelineState={ps({ failed: true, failedAgents: ["a1"] })}
      />,
    );
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Failed");
  });

  // Task 11.5 (Req 20): "degraded" must NOT render as "Done", "Completed", or
  // "Issues" — it has its own distinct label text and amber tone.
  it("shows a Degraded status token for a degraded terminal run (Req 20 distinctness)", () => {
    render(
      <LaneRunHeader
        runState="terminal"
        pipelineState={ps({ degraded: true })}
      />,
    );
    const token = screen.getByTestId("lane-run-status");
    expect(token).toHaveTextContent("Degraded");
    // Amber tone — not the done/success tone.
    expect(token).toHaveAttribute("data-status-tone", "amber");
    // Semantically distinct: not the same text as completed or done.
    expect(token).not.toHaveTextContent(/done/i);
    expect(token).not.toHaveTextContent(/complete/i);
  });

  it("always renders the Back-to-history link; the callback overrides the target", () => {
    const onBackToHistory = vi.fn();
    const { rerender } = render(
      <LaneRunHeader runState="complete" pipelineState={ps()} />,
    );
    // Renders even without a callback (mock fidelity) — default = history.back().
    const backSpy = vi.spyOn(window.history, "back").mockImplementation(() => {});
    fireEvent.click(screen.getByTestId("lane-back"));
    expect(backSpy).toHaveBeenCalledTimes(1);
    backSpy.mockRestore();

    // When supplied, the callback overrides the default target.
    rerender(
      <LaneRunHeader
        runState="complete"
        pipelineState={ps()}
        onBackToHistory={onBackToHistory}
      />,
    );
    fireEvent.click(screen.getByTestId("lane-back"));
    expect(onBackToHistory).toHaveBeenCalledTimes(1);
  });

  it("prefers an explicit runType over the pipeline_type", () => {
    render(
      <LaneRunHeader
        runState="complete"
        runType="Prototype"
        pipelineState={ps({ pipeline_type: "od_prototype" })}
      />,
    );
    expect(screen.getByTestId("lane-run-type")).toHaveTextContent("Prototype");
  });

  it("humanizes a RAW snake_case runType in the eyebrow (BUG-020)", () => {
    render(
      <LaneRunHeader
        runState="complete"
        runType="od_prototype"
        pipelineState={ps({ pipeline_type: "od_prototype" })}
      />,
    );
    expect(screen.getByTestId("lane-run-type")).toHaveTextContent("Prototype");
  });

  // A14 — a review-loop cap absorbed with a resolved deliverable stays a clean
  // "completed" run server-side (never degraded), but the cap message must
  // still surface — amber, never red/Failed.
  describe("A14 — warnings on a completed run", () => {
    it("plain Done (no expander) when there are no warnings", () => {
      render(<LaneRunHeader runState="complete" pipelineState={ps()} />);
      expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Done");
      expect(screen.queryByTestId("lane-run-warnings-toggle")).toBeNull();
    });

    it('"Completed with warnings" amber token + expander when warnings are present', () => {
      render(
        <LaneRunHeader
          runState="complete"
          pipelineState={ps({
            warnings: [
              "step 'review-planner' would be revisited 3 time(s), exceeding loop_max_iterations=2 (R-07) — stopped looping, continuing forward",
            ],
          })}
        />,
      );
      const status = screen.getByTestId("lane-run-status");
      expect(status).toHaveTextContent("Completed with warnings");
      expect(status).toHaveAttribute("data-status-tone", "amber");
      expect(screen.getByTestId("lane-run-warnings-toggle")).toHaveTextContent("1 warning");
    });

    it("expander lists every warning string verbatim, pluralized", () => {
      render(
        <LaneRunHeader
          runState="complete"
          pipelineState={ps({ warnings: ["first cap message", "second cap message"] })}
        />,
      );
      expect(screen.getByTestId("lane-run-warnings-toggle")).toHaveTextContent("2 warnings");
      const list = screen.getByTestId("lane-run-warnings-list");
      expect(list).toHaveTextContent("first cap message");
      expect(list).toHaveTextContent("second cap message");
    });

    it("an empty warnings array reads exactly like no warnings (Done, no expander)", () => {
      render(<LaneRunHeader runState="complete" pipelineState={ps({ warnings: [] })} />);
      expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Done");
      expect(screen.queryByTestId("lane-run-warnings-toggle")).toBeNull();
    });

    it("never surfaces on a Failed terminal run, even if warnings are present", () => {
      render(
        <LaneRunHeader
          runState="terminal"
          pipelineState={ps({ failed: true, warnings: ["some cap message"] })}
        />,
      );
      expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Failed");
      expect(screen.queryByTestId("lane-run-warnings-toggle")).toBeNull();
    });
  });
});
