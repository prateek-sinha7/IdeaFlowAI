/**
 * IdeaInputPage — the "Save workflow" flow (Phase 21 SAVE-FROM-BOTH): the real
 * NameWorkflowModal, the exact `createUserWorkflow` payload, the Saved/error
 * feedback, plus the page chrome that has no other home (Back, initial focus).
 *
 * Boundaries: `@/lib/api` transport, speech stub, inert AgentsPopup, and a
 * ReviewGatesSection double that reports a gate selection.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IdeaInputPage } from "./IdeaInputPage";
import renderWithProviders from "@/test/renderWithProviders";
import type { AgentDef } from "@/types/index";

const api = vi.hoisted(() => ({
  getToken: vi.fn<() => string | null>(),
  createUserWorkflow: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => api.getToken(),
  createUserWorkflow: (token: string, body: unknown) => api.createUserWorkflow(token, body),
  getWorkflowDetail: vi.fn(),
  setWorkflowOverrideEnabled: vi.fn(),
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
}));

vi.mock("./AgentsPopup", () => ({ AgentsPopup: () => null }));

interface GatesHandle {
  onChange: (ids: string[], touched: boolean) => void;
}

vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: (props: GatesHandle) => (
    <>
      <button type="button" onClick={() => props.onChange(["domain-analyst"], true)}>check gate</button>
      <button type="button" onClick={() => props.onChange([], false)}>untouch gates</button>
    </>
  ),
}));

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

const DOMAIN: AgentDef = {
  id: "domain-analyst",
  name: "Domain Analyst",
  role: "role",
  description: "d",
  pipeline_type: "user_stories",
  order: 1,
  icon: "x",
  estimated_duration: 0,
  has_skill: false,
};

function renderPage(
  extra: Partial<React.ComponentProps<typeof IdeaInputPage>> = {},
  agents: AgentDef[] = [DOMAIN],
) {
  const onRun = vi.fn();
  const onBack = vi.fn();
  renderWithProviders(
    <IdeaInputPage workflowType="user_stories" onBack={onBack} onRun={onRun} {...extra} />,
    {
      preloadedState: {
        agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded", error: null },
      },
    },
  );
  return { onRun, onBack };
}

const brief = () => screen.getByRole("textbox", { name: "Brief description" });
const openSaveModal = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: /save workflow/i }));

async function saveAs(user: ReturnType<typeof userEvent.setup>, name: string, description = "") {
  await openSaveModal(user);
  // Use findByLabelText (async poll) so the modal is fully mounted before we interact.
  // Use paste() instead of type() — paste is atomic and does not dispatch individual
  // keydown/keypress events, so focus cannot drift back to the brief textarea between
  // characters on re-renders triggered by state changes (e.g. "untouch gates").
  const nameInput = await screen.findByLabelText("Workflow name");
  await user.click(nameInput);
  await user.paste(name);
  if (description) {
    const descInput = screen.getByLabelText(/Description/);
    await user.click(descInput);
    await user.paste(description);
  }
  await user.click(screen.getByRole("button", { name: "Save" }));
}

beforeEach(() => {
  api.getToken.mockReturnValue("test-token");
  api.createUserWorkflow.mockResolvedValue({ id: "saved-1" });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("IdeaInputPage Save workflow", () => {
  it("saves the composition with its brief and shows Saved", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(brief(), "  Brief text  ");

    await saveAs(user, "My flow", "Does things");

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(api.createUserWorkflow).toHaveBeenCalledWith("test-token", {
      name: "My flow",
      description: "Does things",
      base_pipeline_type: "user_stories",
      agent_ids: ["domain-analyst"],
      model_overrides: undefined,
      // Gate selection starts "touched" (FIX-323), so an empty list is saved explicitly.
      selections: { _wizard: { brief: "Brief text", gateAgentIds: [] } },
    });
    expect(screen.queryByRole("button", { name: /save workflow/i })).not.toBeInTheDocument();
  });

  it("omits the description when the user leaves it blank", async () => {
    const user = userEvent.setup();
    renderPage();

    await saveAs(user, "My flow");

    await screen.findByText("Saved");
    expect(api.createUserWorkflow.mock.calls[0][1].description).toBeUndefined();
  });

  it("includes touched gate ids, saved levers and model overrides in the saved payload", async () => {
    const user = userEvent.setup();
    renderPage({
      initialSelections: { "domain-analyst": { retry: 2 } },
      initialModelOverrides: { "domain-analyst": "model-x" },
    });
    await user.type(brief(), "Brief");
    await user.click(screen.getByRole("button", { name: "check gate" }));

    await saveAs(user, "My flow");

    await screen.findByText("Saved");
    expect(api.createUserWorkflow.mock.calls[0][1]).toMatchObject({
      model_overrides: { "domain-analyst": "model-x" },
      selections: {
        "domain-analyst": { retry: 2 },
        _wizard: { brief: "Brief", gateAgentIds: ["domain-analyst"] },
      },
    });
  });

  it("leaves gate ids out of the saved payload while the review gates are untouched", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(brief(), "Brief");
    await user.click(screen.getByRole("button", { name: "untouch gates" }));

    await saveAs(user, "My flow");

    await screen.findByText("Saved");
    expect(api.createUserWorkflow.mock.calls[0][1].selections).toEqual({ _wizard: { brief: "Brief" } });
  });

  it("keeps the modal's Save disabled until the name has non-blank text", async () => {
    const user = userEvent.setup();
    renderPage();
    await openSaveModal(user);

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.type(screen.getByLabelText("Workflow name"), "   ");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.type(screen.getByLabelText("Workflow name"), "x");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("closes the modal without saving when Cancel is clicked", async () => {
    const user = userEvent.setup();
    renderPage();
    await openSaveModal(user);

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByLabelText("Workflow name")).not.toBeInTheDocument());
    expect(api.createUserWorkflow).not.toHaveBeenCalled();
  });

  it("shows the server's message when saving fails, and clears it when the modal is reopened", async () => {
    const user = userEvent.setup();
    api.createUserWorkflow.mockRejectedValue(new Error("name already taken"));
    renderPage();

    await saveAs(user, "My flow");
    expect(await screen.findByText("name already taken")).toBeInTheDocument();
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();

    await openSaveModal(user);

    expect(screen.queryByText("name already taken")).not.toBeInTheDocument();
  });

  it("shows a generic message when saving fails without an error message", async () => {
    const user = userEvent.setup();
    api.createUserWorkflow.mockRejectedValue(undefined);
    renderPage();

    await saveAs(user, "My flow");

    expect(await screen.findByText("Failed to save workflow.")).toBeInTheDocument();
  });

  it("asks the user to sign in when there is no token at save time", async () => {
    const user = userEvent.setup();
    renderPage();
    await openSaveModal(user);
    await user.type(screen.getByLabelText("Workflow name"), "My flow");
    api.getToken.mockReturnValue(null);

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Not authenticated.")).toBeInTheDocument();
    expect(api.createUserWorkflow).not.toHaveBeenCalled();
  });

  it("disables Save workflow while the roster is empty", () => {
    renderPage({}, []);

    expect(screen.getByRole("button", { name: /save workflow/i })).toBeDisabled();
  });
});

describe("IdeaInputPage chrome", () => {
  it("calls onBack when the back button is clicked", async () => {
    const user = userEvent.setup();
    const { onBack } = renderPage();

    await user.click(screen.getByRole("button", { name: "Back to dashboard" }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("moves focus to the brief shortly after mount", async () => {
    renderPage();

    await waitFor(() => expect(brief()).toHaveFocus());
  });
});
