/**
 * IdeaInputPage — attach/remove chips, the Ctrl/Cmd+Enter submit shortcut, and
 * the in-flight double-submit guard (ISS-729). Complements the existing
 * imageInput / textTruncation / staleExtractionBrief files, which cover what a
 * successful attach puts into the run payload.
 *
 * Boundary: `@/lib/api` (staging/extraction transport), speech recognition,
 * `createImageBitmap` (absent in jsdom). AgentsPopup / ReviewGatesSection are
 * inert doubles, as in the sibling files.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import renderWithProviders from "@/test/renderWithProviders";
import type { AgentDef } from "@/types/index";

const api = vi.hoisted(() => ({
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  extractFileText: (token: string, file: File) => api.extractFileText(token, file),
  stageRunFile: (token: string, file: File) => api.stageRunFile(token, file),
  createUserWorkflow: vi.fn(),
  getWorkflowDetail: vi.fn(),
  setWorkflowOverrideEnabled: vi.fn(),
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

vi.mock("./AgentsPopup", () => ({ AgentsPopup: () => null }));
vi.mock("./ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));

const TEST_AGENTS: AgentDef[] = [
  {
    id: "domain-analyst",
    name: "Domain Discovery Agent",
    role: "Market & Persona Research",
    description: "Research market and personas",
    pipeline_type: "user_stories",
    order: 1,
    icon: "search",
    estimated_duration: 60,
    has_skill: false,
  },
];

function renderPage(onRun = vi.fn()) {
  const { container } = renderWithProviders(
    <IdeaInputPage workflowType="user_stories" onBack={vi.fn()} onRun={onRun} />,
    {
      preloadedState: {
        agents: {
          agents: TEST_AGENTS,
          totalCount: TEST_AGENTS.length,
          pipelines: {},
          status: "succeeded",
          error: null,
        },
      },
    },
  );
  const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
  return { onRun, fileInput };
}

/** The chip `<span>` that holds a file name and its remove button. */
const chipFor = (name: string) => screen.getByText(name) as HTMLElement;

beforeEach(() => {
  api.stageRunFile.mockResolvedValue({ stage_id: "stage-1", files: [] });
  api.extractFileText.mockResolvedValue({ filename: "x", text: "extracted", truncated: false });
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(async () => ({ width: 10, height: 10, close: vi.fn() })),
  );
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("IdeaInputPage attachments", () => {
  it("opens the file picker when Attach file is clicked", async () => {
    const user = userEvent.setup();
    const { fileInput } = renderPage();
    const onPickerClick = vi.fn();
    fileInput.addEventListener("click", onPickerClick);

    await user.click(screen.getByRole("button", { name: /attach file/i }));

    expect(onPickerClick).toHaveBeenCalledTimes(1);
  });

  it("removes a text attachment chip and leaves its content out of the run message", async () => {
    const user = userEvent.setup();
    const { onRun, fileInput } = renderPage();
    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "Summarise this.");
    await user.upload(fileInput, new File(["secret notes"], "notes.txt", { type: "text/plain" }));
    await waitFor(() => expect(screen.getByText("notes.txt")).toBeInTheDocument());

    await user.click(within(chipFor("notes.txt")).getByRole("button"));
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onRun.mock.calls[0][0]).toBe("Summarise this.");
  });

  it("removes an image chip and omits images from the launch payload", async () => {
    const user = userEvent.setup();
    const { onRun, fileInput } = renderPage();
    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "Describe it.");
    await user.upload(fileInput, new File(["png-bytes"], "shot.png", { type: "image/png" }));
    await waitFor(() => expect(screen.getByText("shot.png")).toBeInTheDocument());

    await user.click(within(chipFor("shot.png")).getByRole("button"));
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(screen.queryByText("shot.png")).not.toBeInTheDocument();
    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: [] });
  });

  it("sends staged upload ids to the launch payload when a document was staged", async () => {
    let resolveStage!: (v: { stage_id: string; files: string[] }) => void;
    let resolveExtract!: (v: { filename: string; text: string; truncated: boolean }) => void;
    api.stageRunFile.mockReturnValue(new Promise((r) => (resolveStage = r)));
    api.extractFileText.mockReturnValue(new Promise((r) => (resolveExtract = r)));
    const user = userEvent.setup();
    const { onRun, fileInput } = renderPage();
    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "Use the plan.");
    await user.upload(fileInput, new File(["%PDF"], "plan.pdf", { type: "application/pdf" }));

    // Settle both server calls inside act so the hook state is committed before Run.
    await act(async () => {
      resolveStage({ stage_id: "stage-xyz", files: ["plan.pdf"] });
      resolveExtract({ filename: "plan.pdf", text: "plan text", truncated: false });
    });
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: [], staged_upload_ids: ["stage-xyz"] });
  });
});

describe("IdeaInputPage submit shortcut and run guards", () => {
  it.each([
    ["Control", "{Control>}{Enter}{/Control}"],
    ["Meta", "{Meta>}{Enter}{/Meta}"],
  ])("runs the workflow when %s+Enter is pressed in the brief", async (_key, keys) => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "Ship it");
    await user.keyboard(keys);

    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onRun.mock.calls[0][0]).toBe("Ship it");
  });

  it("does not run when Enter is pressed without a modifier", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "Ship it{Enter}");

    expect(onRun).not.toHaveBeenCalled();
  });

  it("does not run from the shortcut when the brief is blank", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "   ");
    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(onRun).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /run workflow/i })).toBeDisabled();
  });

  it("launches once and disables Run when the shortcut is pressed twice before the page unmounts", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();
    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "Ship it");

    await user.keyboard("{Control>}{Enter}{/Control}");
    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(onRun).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /run workflow/i })).toBeDisabled();
  });
});
