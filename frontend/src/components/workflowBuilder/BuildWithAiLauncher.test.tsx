import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BuilderModelsResponse } from "@/types/workflowBuilder";

import { isNewConversationPending, resetBuilderHandoff } from "./builderHandoff";

const mocks = vi.hoisted(() => ({
  getBuilderModels: vi.fn(),
  listSessions: vi.fn(),
  createSession: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: () => "token",
}));
vi.mock("@/lib/workflowBuilderApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/workflowBuilderApi")>()),
  getBuilderModels: mocks.getBuilderModels,
  listSessions: mocks.listSessions,
  createSession: mocks.createSession,
}));

import { BuildWithAiLauncher } from "./BuildWithAiLauncher";

const models: BuilderModelsResponse = {
  models: [
    {
      id: "sonnet",
      label: "Sonnet",
      description: "",
      tier: "standard",
      cost_class: "standard",
      provider: "anthropic",
      context_window: 200000,
      user_allowed: true,
      reasoning_mode: "adaptive",
      reasoning_levels: ["low", "high"],
    },
  ],
  default_model_id: "sonnet",
  default_efforts: { sonnet: "low" },
};

function renderLauncher(tier: "basic" | "enterprise" | null, onOpenComposer = vi.fn()) {
  render(
    <BuildWithAiLauncher tier={tier} onOpenComposer={onOpenComposer}>
      {(onBuildWithAi) =>
        onBuildWithAi ? (
          <button type="button" onClick={onBuildWithAi}>
            Build with AI
          </button>
        ) : (
          <p>no entry</p>
        )
      }
    </BuildWithAiLauncher>,
  );
  return onOpenComposer;
}

describe("BuildWithAiLauncher", () => {
  beforeEach(() => {
    resetBuilderHandoff();
    mocks.getBuilderModels.mockReset().mockResolvedValue(models);
    mocks.listSessions.mockReset().mockResolvedValue({ items: [], next_cursor: null });
    mocks.createSession.mockReset();
  });

  it("offersNoEntryAndMakesNoRequest_whenTheTierLacksTheCustomEntitlement", async () => {
    renderLauncher("basic");

    expect(screen.getByText("no entry")).toBeInTheDocument();
    expect(mocks.getBuilderModels).not.toHaveBeenCalled();
  });

  it("offersNoEntry_whenTheModelListFails", async () => {
    mocks.getBuilderModels.mockRejectedValue(new Error("404"));
    renderLauncher("enterprise");

    await waitFor(() => expect(mocks.getBuilderModels).toHaveBeenCalled());
    expect(screen.getByText("no entry")).toBeInTheDocument();
  });

  it("opensANewCanvasWithThePanelPending_whenTheEntryIsClicked", async () => {
    const onOpenComposer = renderLauncher("enterprise");

    await userEvent.click(await screen.findByRole("button", { name: "Build with AI" }));

    expect(onOpenComposer).toHaveBeenCalledTimes(1);
    expect(isNewConversationPending()).toBe(true);
  });

  it("opensNoPopupAndCreatesNoSession_whenTheEntryIsClicked", async () => {
    renderLauncher("enterprise");

    await userEvent.click(await screen.findByRole("button", { name: "Build with AI" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mocks.createSession).not.toHaveBeenCalled();
    expect(mocks.listSessions).not.toHaveBeenCalled();
  });
});
