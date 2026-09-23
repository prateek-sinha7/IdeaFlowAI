/**
 * Bug: a file whose client-side preview extraction (POST /api/files/extract-text)
 * fails but WAS successfully staged server-side (POST /api/runs/uploads/stage)
 * must never contribute a "[could not extract text]" brief block — agents read
 * the real content from `.uploads/` via the `extract_text` tool, and a defeatist
 * client-side note convinced a past run's journey-designer agent the document
 * was genuinely unreadable, silently dropping two screens from the plan.
 *
 * The chip (attachedFiles) must still render either way — only the brief text
 * for the unpreviewable file changes.
 */

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import renderWithProviders from "@/test/renderWithProviders";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

vi.mock("./AgentsPopup", () => ({
  AgentsPopup: () => null,
}));

vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: () => null,
}));

const mockExtractFileText = vi.fn();
const mockStageRunFile = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  extractFileText: (token: string, file: File) => mockExtractFileText(token, file),
  stageRunFile: (token: string, file: File) => mockStageRunFile(token, file),
  createUserWorkflow: vi.fn(),
  getWorkflowDetail: vi.fn(),
  setWorkflowOverrideEnabled: vi.fn(),
}));

const TEST_AGENTS = [
  {
    id: "domain-analyst",
    name: "Domain Discovery Agent",
    role: "Market & Persona Research",
    description: "Research market and personas",
    pipeline_type: "user_stories",
    order: 1,
    icon: "🔍",
    estimated_duration: 60,
    has_skill: false,
  },
];

function renderPage(onRun = vi.fn()) {
  const { container } = renderWithProviders(
    <SkillsHooksProvider>
      <IdeaInputPage workflowType="user_stories" onBack={vi.fn()} onRun={onRun} />
    </SkillsHooksProvider>,
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
  return { onRun, container };
}

describe("IdeaInputPage — brief never claims a staged document is unreadable", () => {
  it("omits any '[could not extract text]' block for a staged file whose preview extraction failed, but still shows its chip", async () => {
    mockStageRunFile.mockResolvedValue({ stage_id: "stage-1", files: ["4-azure.xlsx"] });
    mockExtractFileText.mockRejectedValue(new Error("415"));

    const user = userEvent.setup();
    const { onRun, container } = renderPage();

    await user.type(screen.getByRole("textbox"), "Build the app.");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["binary content"], "4-azure.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await user.upload(fileInput, file);

    // Chip renders immediately (attach-time), regardless of extraction outcome.
    await waitFor(() => expect(screen.getByText("4-azure.xlsx")).toBeInTheDocument());
    // Staging resolves before extraction settles the catch handler.
    await waitFor(() => expect(mockStageRunFile).toHaveBeenCalled());
    await waitFor(() => expect(mockExtractFileText).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [message] = onRun.mock.calls[0];
    expect(message).not.toContain("[could not extract text]");
    expect(message).not.toContain("=== Attached: 4-azure.xlsx ===");
  });

  it("keeps the normal inlined block for a file whose extraction succeeds", async () => {
    mockStageRunFile.mockResolvedValue({ stage_id: "stage-2", files: ["notes.pdf"] });
    mockExtractFileText.mockResolvedValue({
      filename: "notes.pdf",
      text: "Real extracted content.",
      truncated: false,
    });

    const user = userEvent.setup();
    const { onRun, container } = renderPage();

    await user.type(screen.getByRole("textbox"), "Build the app.");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["binary content"], "notes.pdf", { type: "application/pdf" });
    await user.upload(fileInput, file);

    await waitFor(() => expect(screen.getByText("notes.pdf")).toBeInTheDocument());
    await waitFor(() => expect(mockExtractFileText).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [message] = onRun.mock.calls[0];
    expect(message).toContain("=== Attached: notes.pdf ===");
    expect(message).toContain("Real extracted content.");
  });

  it("gives an honest, non-defeatist note (not '[could not extract text]') when staging itself also fails", async () => {
    mockStageRunFile.mockRejectedValue(new Error("stage failed"));
    mockExtractFileText.mockRejectedValue(new Error("415"));

    const user = userEvent.setup();
    const { onRun, container } = renderPage();

    await user.type(screen.getByRole("textbox"), "Build the app.");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["binary content"], "unstageable.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await user.upload(fileInput, file);

    await waitFor(() => expect(screen.getByText("unstageable.xlsx")).toBeInTheDocument());
    await waitFor(() => expect(mockExtractFileText).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [message] = onRun.mock.calls[0];
    expect(message).toContain("=== Attached: unstageable.xlsx ===");
    expect(message).not.toContain("[could not extract text]");
    expect(message).not.toMatch(/unreadable|empty/i);
    expect(message).toContain("extract_text");
  });
});
