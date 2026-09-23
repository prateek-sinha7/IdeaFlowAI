/**
 * BUG-20260828-074900-workflow-r2 — the legacy `/workflow` builder's attach/remove
 * cycle is asymmetric: attaching a file injects a literal `[Attached: <name>]`
 * marker into the idea textarea (`WorkflowView.tsx:337-340`), but the chip's
 * remove handler (`WorkflowView.tsx:388`) only filters `attachedFiles` — it never
 * strips the marker back out of `ideaInput`. See:
 *   - ISS-345 (root): single-file attach/remove leaves the marker behind.
 *   - ISS-583 (sibling): 2+ files in one multi-select join into one marker block;
 *     a blanket-clear "fix" would also erase the marker for a file that is still
 *     attached, so removing one of two must leave the OTHER file's marker intact.
 *   - ISS-579 (sibling): the same stale `ideaInput` is forwarded verbatim as the
 *     run brief by `handleRun` once `onStartPipeline` is wired.
 *   - ISS-603 (fixture): third test case fixed — typed brief + stubbed library
 *     so the Run button is not disabled when the attachment is removed.
 */
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { WorkflowView } from "./WorkflowView";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

// ISS-603: stub useAgentLibrary so pipelineAgents is non-empty (avoids the
// post-ISS-328 guard that disables the Run button when there are no agents).
// Hoisted by vitest to the top of the module regardless of where it appears.
vi.mock("@/hooks/useAgentLibrary", () => ({
  useAgentLibrary: () => ({
    allAgents: [{ id: "stub-agent", name: "Stub", pipeline_type: "user_stories", order: 0, description: "", role: "", estimated_duration: 0, has_skill: false, gate: null, skills: [] }],
    libraryAgents: [{ id: "stub-agent", name: "Stub", pipeline_type: "user_stories", order: 0, description: "", role: "", estimated_duration: 0, has_skill: false, gate: null, skills: [] }],
  }),
}));

function makeFile(name: string) {
  return new File(["zz-hunt content"], name, { type: "text/plain" });
}

async function attach(user: ReturnType<typeof userEvent.setup>, container: HTMLElement, files: File[]) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, files);
}

async function removeChip(user: ReturnType<typeof userEvent.setup>, filename: string) {
  const chip = screen.getByText(filename).closest("span") as HTMLElement;
  const removeBtn = chip.querySelector("button") as HTMLElement;
  await user.click(removeBtn);
}

describe("WorkflowView — attachment remove leaves stale marker (BUG-20260828-074900-workflow-r2)", () => {
  it("ISS-345 — removing the only attachment strips its [Attached: ...] marker from the brief", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <WorkflowView pipelineType="user_stories" userMessage="" onClose={vi.fn()} />
    );

    await attach(user, container, [makeFile("zz-hunt-single.txt")]);

    const textarea = screen.getByPlaceholderText(/describe what you want to build/i) as HTMLTextAreaElement;
    expect(textarea.value).toContain("[Attached: zz-hunt-single.txt]");

    await removeChip(user, "zz-hunt-single.txt");

    expect(textarea.value).not.toContain("[Attached:");
  });

  it("ISS-583 — removing one of two files from a joined marker keeps the still-attached file's marker intact", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <WorkflowView pipelineType="user_stories" userMessage="" onClose={vi.fn()} />
    );

    await attach(user, container, [makeFile("zz-hunt-a.txt"), makeFile("zz-hunt-b.txt")]);

    const textarea = screen.getByPlaceholderText(/describe what you want to build/i) as HTMLTextAreaElement;
    expect(textarea.value).toContain("zz-hunt-a.txt");
    expect(textarea.value).toContain("zz-hunt-b.txt");

    await removeChip(user, "zz-hunt-a.txt");

    // The removed file's reference must be gone...
    expect(textarea.value).not.toContain("zz-hunt-a.txt");
    // ...but the still-attached file's marker must survive the removal.
    expect(textarea.value).toContain("[Attached: zz-hunt-b.txt]");
  });

  it("ISS-579 — a run launched after removing an attachment does not forward its stale marker as the brief", async () => {
    // ISS-603: the original fixture was broken in two ways:
    //   1. No brief text was typed, so after removing the attachment the textarea
    //      was "" and handleRun's `if (!ideaInput.trim()) return` short-circuited.
    //   2. useAgentLibrary was unstubbed, so pipelineAgents.length === 0 and the
    //      "Run workflow" button was disabled by the post-ISS-328 guard.
    // Fix (from ISS-603's "What a correct fixture looks like"):
    //   type real brief text FIRST (so a run is legitimately allowed once the
    //   attachment is removed), then attach + remove, then click Run.
    // useAgentLibrary is stubbed at the top of this file (vi.mock hoisted) so the
    // Run button is enabled for all three tests in this suite.
    const user = userEvent.setup();
    const onStartPipeline = vi.fn();
    const { container } = renderWithProviders(
      <WorkflowView
        pipelineType="user_stories"
        userMessage="My actual brief text"
        onClose={vi.fn()}
        onStartPipeline={onStartPipeline}
      />
    );

    await attach(user, container, [makeFile("zz-hunt-run.txt")]);
    await removeChip(user, "zz-hunt-run.txt");

    const runButton = screen.getByRole("button", { name: /run workflow/i });
    await user.click(runButton);

    expect(onStartPipeline).toHaveBeenCalled();
    const [, message] = onStartPipeline.mock.calls[0];
    expect(message).not.toContain("[Attached:");
  });
});
