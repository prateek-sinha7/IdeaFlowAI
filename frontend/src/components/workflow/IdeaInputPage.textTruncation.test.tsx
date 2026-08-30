/**
 * ISS-312 — oversized .txt/.md/.json/.csv attachments are silently truncated
 * by `useBriefAttachments()`'s `isTextFile` branch (`content.slice(0,
 * ATTACH_MAX_CHARS)`), unlike the sibling `isBinaryFile` branch which appends
 * a visible `[Content truncated to N chars]` note when `res.truncated` is
 * true. This proves the text-file branch should do the same.
 *
 * Mirrors IdeaInputPage.imageInput.test.tsx (mocked AgentsPopup /
 * ReviewGatesSection / useSpeechRecognition, SkillsHooksProvider render).
 */

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { ATTACH_MAX_CHARS } from "@/lib/constants";
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
    }
  );
  return { onRun, container };
}

describe("ISS-312 — oversized .txt attachment truncation must be visible", () => {
  it("appends a truncation note when a .txt attachment exceeds ATTACH_MAX_CHARS", async () => {
    const user = userEvent.setup();
    const { onRun, container } = renderPage();

    await user.type(screen.getByRole("textbox"), "Summarize the attached notes.");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const oversizedContent = "a".repeat(ATTACH_MAX_CHARS + 1000);
    const file = new File([oversizedContent], "huge.txt", { type: "text/plain" });
    await user.upload(fileInput, file);

    // FileReader is async — wait for the attachment chip.
    await waitFor(() => expect(screen.getByText("huge.txt")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [message] = onRun.mock.calls[0];

    // Sibling binary (.pdf/.docx/.pptx) path appends this exact note when
    // truncated — the text path must give the user the same signal.
    expect(message).toContain(`[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]`);
  });
});
