import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AgentRunState } from "@/types/index";

// AgentNode embeds SkillManager, which imports the authed API client.
vi.mock("@/lib/api", () => ({
  authedFetch: vi.fn(),
  getToken: () => null,
}));

import { PipelineGraph } from "./PipelineGraph";

function makeAgent(id: string, overrides: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id,
    name: `Agent ${id}`,
    role: `Role ${id}`,
    icon: "🤖",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...overrides,
  };
}

// jsdom does not implement scrollIntoView; the component calls it on the active node.
const scrollIntoView = vi.fn();

describe("PipelineGraph", () => {
  beforeEach(() => {
    scrollIntoView.mockClear();
    Element.prototype.scrollIntoView = scrollIntoView;
  });

  afterEach(() => {
    // @ts-expect-error restoring the jsdom default (property is absent there)
    delete Element.prototype.scrollIntoView;
  });

  describe("header", () => {
    it("shows the completed count out of the total agents", () => {
      const agents = [
        makeAgent("a", { status: "done" }),
        makeAgent("b", { status: "running" }),
        makeAgent("c"),
      ];

      render(<PipelineGraph agents={agents} currentIndex={1} />);

      expect(screen.getByText("1 of 3 agents complete")).toBeInTheDocument();
    });

    it.each([
      ["user_stories", "User Stories"],
      ["ppt", "Presentation"],
      ["prototype", "Prototype"],
    ])("maps the %s pipeline type to the label %s", (pipelineType, label) => {
      render(<PipelineGraph agents={[]} currentIndex={-1} pipelineType={pipelineType} />);

      expect(screen.getByText(label)).toBeInTheDocument();
    });

    it("falls back to the raw pipeline type when it has no label mapping", () => {
      render(<PipelineGraph agents={[]} currentIndex={-1} pipelineType="custom_flow" />);

      expect(screen.getByText("custom_flow")).toBeInTheDocument();
    });

    it("renders no pipeline badge when pipelineType is omitted", () => {
      render(<PipelineGraph agents={[]} currentIndex={-1} />);

      expect(screen.queryByText("User Stories")).not.toBeInTheDocument();
      expect(screen.queryByText("Presentation")).not.toBeInTheDocument();
      expect(screen.queryByText("Prototype")).not.toBeInTheDocument();
    });

    it("shows the total duration with one decimal", () => {
      render(<PipelineGraph agents={[]} currentIndex={-1} totalDuration={42.26} />);

      expect(screen.getByText("42.3s total")).toBeInTheDocument();
    });

    it("shows a zero total duration rather than hiding it", () => {
      render(<PipelineGraph agents={[]} currentIndex={-1} totalDuration={0} />);

      expect(screen.getByText("0.0s total")).toBeInTheDocument();
    });

    it.each([[null], [undefined]])("hides the total duration when it is %s", (totalDuration) => {
      render(<PipelineGraph agents={[]} currentIndex={-1} totalDuration={totalDuration} />);

      expect(screen.queryByText(/s total$/)).not.toBeInTheDocument();
    });
  });

  describe("agent list", () => {
    it("renders one node per agent in order", () => {
      const agents = [makeAgent("a"), makeAgent("b"), makeAgent("c")];

      render(<PipelineGraph agents={agents} currentIndex={0} />);

      const names = screen.getAllByText(/^Agent [abc]$/).map((el) => el.textContent);
      expect(names).toEqual(["Agent a", "Agent b", "Agent c"]);
    });

    it("renders an empty list with a zero-of-zero summary and no completion banner", () => {
      render(<PipelineGraph agents={[]} currentIndex={-1} />);

      expect(screen.getByText("0 of 0 agents complete")).toBeInTheDocument();
      expect(screen.queryByText("Pipeline Complete")).not.toBeInTheDocument();
    });
  });

  describe("completion indicator", () => {
    it("shows Pipeline Complete when every agent is done", () => {
      const agents = [makeAgent("a", { status: "done" }), makeAgent("b", { status: "done" })];

      render(<PipelineGraph agents={agents} currentIndex={1} />);

      expect(screen.getByText("Pipeline Complete")).toBeInTheDocument();
      expect(screen.getByText("2 of 2 agents complete")).toBeInTheDocument();
    });

    it("omits Pipeline Complete while at least one agent is not done", () => {
      const agents = [makeAgent("a", { status: "done" }), makeAgent("b", { status: "error" })];

      render(<PipelineGraph agents={agents} currentIndex={1} />);

      expect(screen.queryByText("Pipeline Complete")).not.toBeInTheDocument();
    });
  });

  describe("auto-scroll", () => {
    it("scrolls the active agent into view centered and smooth", () => {
      render(
        <PipelineGraph agents={[makeAgent("a"), makeAgent("b")]} currentIndex={1} />,
      );

      expect(scrollIntoView).toHaveBeenCalledTimes(1);
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "center" });
    });

    it("scrolls again when the current index advances", () => {
      const agents = [makeAgent("a"), makeAgent("b")];
      const { rerender } = render(<PipelineGraph agents={agents} currentIndex={0} />);

      rerender(<PipelineGraph agents={agents} currentIndex={1} />);

      expect(scrollIntoView).toHaveBeenCalledTimes(2);
    });

    it("does not scroll when no agent matches the current index", () => {
      render(<PipelineGraph agents={[makeAgent("a")]} currentIndex={-1} />);

      expect(scrollIntoView).not.toHaveBeenCalled();
    });
  });
});
