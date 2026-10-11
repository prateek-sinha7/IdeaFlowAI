import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkflowControls } from "./WorkflowControls";

interface Overrides {
  pipelineType?: string;
  isRunning?: boolean;
  estimatedDuration?: number;
  onRun?: () => void;
  onCancel?: () => void;
  onTypeChange?: (type: string) => void;
}

function renderControls(overrides: Overrides = {}) {
  const props = {
    pipelineType: "user_stories",
    isRunning: false,
    estimatedDuration: 120,
    onRun: vi.fn(),
    onCancel: vi.fn(),
    onTypeChange: vi.fn(),
    ...overrides,
  };
  render(<WorkflowControls {...props} />);
  return props;
}

describe("WorkflowControls", () => {
  describe("pipeline tabs", () => {
    it("renders a tab button for each pipeline type", () => {
      renderControls();

      expect(screen.getByRole("button", { name: "User Stories" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "PPT" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Prototype" })).toBeInTheDocument();
    });

    it.each([
      ["User Stories", "user_stories"],
      ["PPT", "ppt"],
      ["Prototype", "prototype"],
    ])("reports %s as %s when the tab is clicked", async (name, id) => {
      const user = userEvent.setup();
      const { onTypeChange } = renderControls({ pipelineType: "other" });

      await user.click(screen.getByRole("button", { name }));

      expect(onTypeChange).toHaveBeenCalledWith(id);
    });

    it("does not throw when a tab is clicked without an onTypeChange handler", async () => {
      const user = userEvent.setup();
      renderControls({ onTypeChange: undefined });

      await user.click(screen.getByRole("button", { name: "PPT" }));

      expect(screen.getByRole("button", { name: "PPT" })).toBeEnabled();
    });

    it("disables every tab and ignores clicks while a run is in progress", async () => {
      const user = userEvent.setup();
      const { onTypeChange } = renderControls({ isRunning: true });

      for (const name of ["User Stories", "PPT", "Prototype"]) {
        const tab = screen.getByRole("button", { name });
        expect(tab).toBeDisabled();
        await user.click(tab);
      }

      expect(onTypeChange).not.toHaveBeenCalled();
    });

    it("enables every tab when idle", () => {
      renderControls({ isRunning: false });

      for (const name of ["User Stories", "PPT", "Prototype"]) {
        expect(screen.getByRole("button", { name })).toBeEnabled();
      }
    });
  });

  describe("run / cancel", () => {
    it("shows Run Workflow and calls onRun when idle", async () => {
      const user = userEvent.setup();
      const { onRun, onCancel } = renderControls();

      await user.click(screen.getByRole("button", { name: "Run Workflow" }));

      expect(onRun).toHaveBeenCalledTimes(1);
      expect(onCancel).not.toHaveBeenCalled();
      expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    });

    it("shows Cancel and calls onCancel while running", async () => {
      const user = userEvent.setup();
      const { onRun, onCancel } = renderControls({ isRunning: true });

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(onCancel).toHaveBeenCalledTimes(1);
      expect(onRun).not.toHaveBeenCalled();
      expect(screen.queryByRole("button", { name: "Run Workflow" })).not.toBeInTheDocument();
    });

    it("does not throw when Cancel is clicked without an onCancel handler", async () => {
      const user = userEvent.setup();
      renderControls({ isRunning: true, onCancel: undefined });

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
    });

    it("activates Run Workflow from the keyboard", async () => {
      const user = userEvent.setup();
      const { onRun } = renderControls();

      screen.getByRole("button", { name: "Run Workflow" }).focus();
      await user.keyboard("{Enter}");

      expect(onRun).toHaveBeenCalledTimes(1);
    });
  });

  describe("estimated duration", () => {
    it.each([
      [120, "~2min"],
      [121, "~3min"],
      [1, "~1min"],
      [60, "~1min"],
      [0, "~0min"],
    ])("rounds %s seconds up to %s", (seconds, text) => {
      renderControls({ estimatedDuration: seconds });

      expect(screen.getByText(text)).toBeInTheDocument();
    });
  });
});
