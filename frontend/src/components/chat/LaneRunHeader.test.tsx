import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PipelineRunState } from "@/types/index";
import {
  LaneRunHeader,
  humanizeRunType,
  deriveLaneMeta,
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

describe("LaneRunHeader", () => {
  it("renders the humanized type eyebrow, title and derived meta", () => {
    render(
      <LaneRunHeader
        runState="complete"
        runTitle="Modern Website Prototype Design Reference"
        pipelineState={ps({
          pipeline_type: "od_prototype",
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
    expect(meta).toHaveTextContent("24m 6s");
    expect(meta).toHaveTextContent("1/1 agents");
    expect(meta).toHaveTextContent("14.8M tokens");
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
});
