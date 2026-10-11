import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AgentRunState } from "@/types/index";

// SkillManager (a real child) talks to the backend through these boundaries.
// No token => it renders its modal shell without issuing any request.
vi.mock("@/lib/api", () => ({
  authedFetch: vi.fn(),
  getToken: () => null,
}));

import { AgentNode } from "./AgentNode";

function makeAgent(overrides: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id: "agent-1",
    name: "Requirements Analyst",
    role: "Analyses the brief",
    icon: "🧠",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...overrides,
  };
}

describe("AgentNode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("header", () => {
    it("renders the agent name, role and icon", () => {
      render(<AgentNode agent={makeAgent()} isActive={false} />);

      expect(screen.getByText("Requirements Analyst")).toBeInTheDocument();
      expect(screen.getByText("Analyses the brief")).toBeInTheDocument();
      expect(screen.getByText("🧠")).toBeInTheDocument();
    });

    it("falls back to the robot emoji when the agent has no icon", () => {
      render(<AgentNode agent={makeAgent({ icon: "" })} isActive={false} />);

      expect(screen.getByText("🤖")).toBeInTheDocument();
    });

    it("shows the duration with one decimal when duration is a number", () => {
      render(<AgentNode agent={makeAgent({ duration: 12.345 })} isActive={false} />);

      expect(screen.getByText("12.3s")).toBeInTheDocument();
    });

    it("shows a zero duration rather than hiding it", () => {
      render(<AgentNode agent={makeAgent({ duration: 0 })} isActive={false} />);

      expect(screen.getByText("0.0s")).toBeInTheDocument();
    });

    it("omits the duration when it is null", () => {
      render(<AgentNode agent={makeAgent({ duration: null })} isActive={false} />);

      expect(screen.queryByText(/\d+\.\ds$/)).not.toBeInTheDocument();
    });
  });

  describe("status badge", () => {
    it.each([
      ["idle", /^Idle$/],
      ["thinking", /Thinking\.\.\./],
      ["running", /Running/],
      ["done", /Done/],
      ["error", /Error/],
    ] as const)("renders the %s badge", (status, label) => {
      render(<AgentNode agent={makeAgent({ status })} isActive={false} />);

      expect(screen.getByText(label)).toBeInTheDocument();
    });

    it("renders no badge for an unmapped status such as skipped", () => {
      render(<AgentNode agent={makeAgent({ status: "skipped" })} isActive={false} />);

      expect(screen.queryByText(/^Idle$/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Running|Thinking|Done|Error/)).not.toBeInTheDocument();
    });
  });

  describe("expand / collapse", () => {
    it("starts collapsed and reports aria-expanded=false", () => {
      render(
        <AgentNode agent={makeAgent({ status: "done", output: "result text" })} isActive={false} />,
      );

      expect(screen.getByRole("button", { expanded: false })).toBeInTheDocument();
      expect(screen.queryByText("result text")).not.toBeInTheDocument();
    });

    it("reveals the output and calls onExpand when the header is clicked", async () => {
      const user = userEvent.setup();
      const onExpand = vi.fn();
      render(
        <AgentNode
          agent={makeAgent({ status: "done", output: "result text" })}
          isActive
          onExpand={onExpand}
        />,
      );

      await user.click(screen.getByRole("button", { expanded: false }));

      expect(screen.getByText("result text")).toBeInTheDocument();
      expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
      expect(onExpand).toHaveBeenCalledTimes(1);
    });

    it("collapses again on a second click", async () => {
      const user = userEvent.setup();
      render(
        <AgentNode agent={makeAgent({ status: "done", output: "result text" })} isActive />,
      );
      const header = screen.getByRole("button", { expanded: false });

      await user.click(header);
      await user.click(screen.getByRole("button", { expanded: true }));

      expect(screen.queryByText("result text")).not.toBeInTheDocument();
    });

    it("toggles with the Enter key", async () => {
      const user = userEvent.setup();
      render(
        <AgentNode agent={makeAgent({ status: "done", output: "result text" })} isActive />,
      );

      screen.getByRole("button", { expanded: false }).focus();
      await user.keyboard("{Enter}");

      expect(screen.getByText("result text")).toBeInTheDocument();
    });

    it("toggles with the Space key", async () => {
      const user = userEvent.setup();
      render(
        <AgentNode agent={makeAgent({ status: "done", output: "result text" })} isActive />,
      );

      screen.getByRole("button", { expanded: false }).focus();
      await user.keyboard(" ");

      expect(screen.getByText("result text")).toBeInTheDocument();
    });

    it("ignores other keys", async () => {
      const user = userEvent.setup();
      const onExpand = vi.fn();
      render(
        <AgentNode
          agent={makeAgent({ status: "done", output: "result text" })}
          isActive
          onExpand={onExpand}
        />,
      );

      screen.getByRole("button", { expanded: false }).focus();
      await user.keyboard("a");

      expect(onExpand).not.toHaveBeenCalled();
      expect(screen.queryByText("result text")).not.toBeInTheDocument();
    });

    it("toggles aria-expanded without an onExpand callback even when there is no output", async () => {
      const user = userEvent.setup();
      render(<AgentNode agent={makeAgent({ status: "done", output: "" })} isActive />);

      await user.click(screen.getByRole("button", { expanded: false }));

      expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
    });
  });

  describe("thinking and error panels", () => {
    it("shows the thinking text while the agent is thinking", () => {
      render(
        <AgentNode
          agent={makeAgent({ status: "thinking", thinking: "weighing options" })}
          isActive
        />,
      );

      expect(screen.getByText("weighing options")).toBeInTheDocument();
    });

    it("hides the thinking text when the agent is not thinking", () => {
      render(
        <AgentNode
          agent={makeAgent({ status: "running", thinking: "weighing options" })}
          isActive
        />,
      );

      expect(screen.queryByText("weighing options")).not.toBeInTheDocument();
    });

    it("shows the error message when the agent failed", () => {
      render(
        <AgentNode agent={makeAgent({ status: "error", error: "model timed out" })} isActive />,
      );

      expect(screen.getByText("model timed out")).toBeInTheDocument();
    });

    it("shows no error panel when the agent failed with a null error", () => {
      render(<AgentNode agent={makeAgent({ status: "error", error: null })} isActive />);

      expect(screen.getByText(/Error/)).toBeInTheDocument();
      expect(screen.queryByText("model timed out")).not.toBeInTheDocument();
    });

    it("hides a stale error message once the agent is no longer in error", () => {
      render(
        <AgentNode agent={makeAgent({ status: "done", error: "old failure" })} isActive />,
      );

      expect(screen.queryByText("old failure")).not.toBeInTheDocument();
    });
  });

  describe("skill manager", () => {
    it("offers the manage-skill button only while the agent is idle", () => {
      const { rerender } = render(<AgentNode agent={makeAgent({ status: "idle" })} isActive={false} />);
      expect(screen.getByRole("button", { name: "Manage skill" })).toBeInTheDocument();

      rerender(<AgentNode agent={makeAgent({ status: "running" })} isActive={false} />);
      expect(screen.queryByRole("button", { name: "Manage skill" })).not.toBeInTheDocument();
    });

    it("opens the skill editor for the agent without toggling the row", async () => {
      const user = userEvent.setup();
      const onExpand = vi.fn();
      render(<AgentNode agent={makeAgent()} isActive={false} onExpand={onExpand} />);

      await user.click(screen.getByRole("button", { name: "Manage skill" }));

      expect(screen.getByRole("heading", { name: "Skill Editor" })).toBeInTheDocument();
      expect(screen.getByText("Skill for: Requirements Analyst")).toBeInTheDocument();
      expect(onExpand).not.toHaveBeenCalled();
    });

    it("closes the skill editor from its close button", async () => {
      const user = userEvent.setup();
      render(<AgentNode agent={makeAgent()} isActive={false} />);
      await user.click(screen.getByRole("button", { name: "Manage skill" }));

      // The modal's close control is an icon-only button with no accessible
      // name (reported as a suspected a11y gap), so it is the only button with
      // neither text nor an aria-label.
      const [closeButton] = screen
        .getAllByRole("button")
        .filter((button) => button.textContent === "" && !button.hasAttribute("aria-label"));
      await user.click(closeButton);

      expect(screen.queryByRole("heading", { name: "Skill Editor" })).not.toBeInTheDocument();
    });
  });
});
