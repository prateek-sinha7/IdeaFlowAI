import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { mockAuthedFetch, mockGetToken } = vi.hoisted(() => ({
  mockAuthedFetch: vi.fn(),
  mockGetToken: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  authedFetch: mockAuthedFetch,
  getToken: mockGetToken,
}));

vi.mock("@/lib/env", () => ({ ENV: { API_URL: "http://api.test" } }));

import { SkillManager } from "./SkillManager";

const SKILLS_URL = "http://api.test/api/agents/skills";

function okResponse(body: unknown = {}): Response {
  return { ok: true, json: async () => body } as unknown as Response;
}

function failResponse(): Response {
  return { ok: false, json: async () => ({}) } as unknown as Response;
}

interface Props {
  isOpen?: boolean;
  onClose?: () => void;
  agentId?: string;
  agentName?: string;
}

function renderManager({ isOpen = true, onClose = vi.fn(), agentId = "agent-1", agentName = "Planner" }: Props = {}) {
  const view = render(
    <SkillManager isOpen={isOpen} onClose={onClose} agentId={agentId} agentName={agentName} />,
  );
  return { ...view, onClose };
}

/** Opens the manager with a saved skill already loaded from the server. */
async function renderWithSavedSkill(content = "# Saved skill") {
  mockAuthedFetch.mockResolvedValueOnce(okResponse({ content }));
  const view = renderManager();
  await screen.findByText(content);
  return view;
}

describe("SkillManager", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("tok-123");
    mockAuthedFetch.mockResolvedValue(okResponse({ content: "" }));
    consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
    vi.useRealTimers();
  });

  describe("visibility", () => {
    it("renders nothing and fetches nothing when closed", () => {
      const { container } = renderManager({ isOpen: false });

      expect(container).toBeEmptyDOMElement();
      expect(mockAuthedFetch).not.toHaveBeenCalled();
    });

    it("shows the agent-specific subtitle when an agent name is given", async () => {
      renderManager({ agentName: "Planner" });

      expect(await screen.findByText("Skill for: Planner")).toBeInTheDocument();
    });

    it("shows the generic subtitle when no agent name is given", async () => {
      render(<SkillManager isOpen onClose={vi.fn()} />);

      expect(await screen.findByText("Agent Skill (SKILL.md)")).toBeInTheDocument();
    });

    it("calls onClose when the backdrop is clicked", async () => {
      const user = userEvent.setup();
      const { onClose } = renderManager();
      const dialogHeading = await screen.findByRole("heading", { name: "Skill Editor" });
      // The outermost fixed overlay is the backdrop.
      const backdrop = dialogHeading.closest(".fixed") as HTMLElement;

      await user.click(backdrop);

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("does not call onClose when the panel itself is clicked", async () => {
      const user = userEvent.setup();
      const { onClose } = renderManager();

      await user.click(await screen.findByRole("heading", { name: "Skill Editor" }));

      expect(onClose).not.toHaveBeenCalled();
    });

    it("calls onClose from the header close button", async () => {
      const user = userEvent.setup();
      const { onClose } = renderManager();
      await screen.findByText("No skill attached");

      // The close control is an icon-only button with no accessible name
      // (reported as a suspected a11y gap): the only button with no text and
      // no aria-label.
      const [closeButton] = screen
        .getAllByRole("button")
        .filter((button) => button.textContent === "" && !button.hasAttribute("aria-label"));
      await user.click(closeButton);

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("loading the saved skill", () => {
    it("requests the agent's skill with the bearer token and shows the content", async () => {
      await renderWithSavedSkill("# Planner skill");

      expect(mockAuthedFetch).toHaveBeenCalledWith(`${SKILLS_URL}/agent-1`, {
        headers: { Authorization: "Bearer tok-123" },
      });
      expect(screen.getByText("(15 characters)", { exact: false })).toBeInTheDocument();
    });

    it("shows a loading message while the request is pending", async () => {
      mockAuthedFetch.mockReturnValueOnce(new Promise(() => undefined));

      renderManager();

      expect(await screen.findByText("Loading skill...")).toBeInTheDocument();
    });

    it("shows the empty state when the server has no skill for the agent", async () => {
      mockAuthedFetch.mockResolvedValueOnce(failResponse());

      renderManager();

      expect(await screen.findByText("No skill attached")).toBeInTheDocument();
    });

    it("treats a response without content as an empty skill", async () => {
      mockAuthedFetch.mockResolvedValueOnce(okResponse({}));

      renderManager();

      expect(await screen.findByText("No skill attached")).toBeInTheDocument();
    });

    it("shows an error message and logs when the request rejects", async () => {
      mockAuthedFetch.mockRejectedValueOnce(new Error("network down"));

      renderManager();

      expect(await screen.findByText("Failed to load skill")).toBeInTheDocument();
      expect(consoleError).toHaveBeenCalledWith("Failed to load skill:", expect.any(Error));
    });

    it("does not fetch when there is no auth token", async () => {
      mockGetToken.mockReturnValue(null);

      renderManager();

      expect(await screen.findByText("No skill attached")).toBeInTheDocument();
      expect(mockAuthedFetch).not.toHaveBeenCalled();
    });

    it("does not fetch when no agent id is provided", async () => {
      render(<SkillManager isOpen onClose={vi.fn()} />);

      expect(await screen.findByText("No skill attached")).toBeInTheDocument();
      expect(mockAuthedFetch).not.toHaveBeenCalled();
    });

    it("fetches again when the agent changes", async () => {
      const { rerender } = renderManager({ agentId: "agent-1" });
      await screen.findByText("No skill attached");

      rerender(<SkillManager isOpen onClose={vi.fn()} agentId="agent-2" agentName="Other" />);

      await waitFor(() =>
        expect(mockAuthedFetch).toHaveBeenLastCalledWith(`${SKILLS_URL}/agent-2`, {
          headers: { Authorization: "Bearer tok-123" },
        }),
      );
    });
  });

  describe("toolbar by state", () => {
    it("offers Create New but neither Edit nor Delete when there is no skill", async () => {
      renderManager();
      await screen.findByText("No skill attached");

      expect(screen.getByRole("button", { name: /create new/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
    });

    it("offers Edit and Delete but not Create New when a skill exists", async () => {
      await renderWithSavedSkill();

      expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /create new/i })).not.toBeInTheDocument();
    });
  });

  describe("creating and editing", () => {
    it("seeds the editor with the SKILL.md template on Create New", async () => {
      const user = userEvent.setup();
      renderManager();
      await user.click(await screen.findByRole("button", { name: /create new/i }));

      const editor = screen.getByRole("textbox", { name: "Skill content" }) as HTMLTextAreaElement;
      expect(editor.value).toMatch(/^# Skill Name\n\n## Description/);
      expect(editor.value).toContain("## Constraints");
      expect(screen.getByRole("button", { name: /save skill/i })).toBeEnabled();
    });

    it("switches a saved skill into the editor on Edit", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill("# Saved skill");

      await user.click(screen.getByRole("button", { name: /^edit$/i }));

      expect(screen.getByRole("textbox", { name: "Skill content" })).toHaveValue("# Saved skill");
    });

    it("updates the character count as the content is edited", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill("abc");
      await user.click(screen.getByRole("button", { name: /^edit$/i }));

      await user.type(screen.getByRole("textbox", { name: "Skill content" }), "de");

      expect(screen.getByText("(5 characters)", { exact: false })).toBeInTheDocument();
    });
  });

  describe("file upload", () => {
    it("loads an uploaded file into the editor", async () => {
      const user = userEvent.setup();
      renderManager();
      await screen.findByText("No skill attached");

      await user.upload(
        screen.getByLabelText(/upload \.md/i),
        new File(["# From file"], "skill.md", { type: "text/markdown" }),
      );

      expect(await screen.findByRole("textbox", { name: "Skill content" })).toHaveValue("# From file");
    });

    it("keeps the current state when the file picker is cancelled with no file", async () => {
      renderManager();
      await screen.findByText("No skill attached");

      // user-event cannot dispatch a change carrying an empty FileList, so
      // fireEvent expresses the browser's "dialog dismissed" change event.
      fireEvent.change(screen.getByLabelText(/upload \.md/i), { target: { files: [] } });

      expect(screen.getByText("No skill attached")).toBeInTheDocument();
      expect(screen.queryByRole("textbox", { name: "Skill content" })).not.toBeInTheDocument();
    });

    it("restricts the picker to markdown and text files", async () => {
      renderManager();
      await screen.findByText("No skill attached");

      expect(screen.getByLabelText(/upload \.md/i)).toHaveAttribute("accept", ".md,.txt");
    });
  });

  describe("saving", () => {
    it("posts the agent id and content, then confirms and leaves edit mode", async () => {
      const user = userEvent.setup();
      renderManager();
      await user.click(await screen.findByRole("button", { name: /create new/i }));
      const editor = screen.getByRole("textbox", { name: "Skill content" });
      await user.clear(editor);
      await user.type(editor, "my skill");
      mockAuthedFetch.mockResolvedValueOnce(okResponse());

      await user.click(screen.getByRole("button", { name: /save skill/i }));

      expect(await screen.findByText("✓ Saved")).toBeInTheDocument();
      expect(mockAuthedFetch).toHaveBeenLastCalledWith(SKILLS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer tok-123" },
        body: JSON.stringify({ agent_id: "agent-1", content: "my skill" }),
      });
      expect(screen.queryByRole("textbox", { name: "Skill content" })).not.toBeInTheDocument();
      expect(screen.getByText("my skill")).toBeInTheDocument();
    });

    it("shows a disabled Saving... button while the request is pending", async () => {
      const user = userEvent.setup();
      renderManager();
      await user.click(await screen.findByRole("button", { name: /create new/i }));
      mockAuthedFetch.mockReturnValueOnce(new Promise(() => undefined));

      await user.click(screen.getByRole("button", { name: /save skill/i }));

      expect(await screen.findByRole("button", { name: /saving\.\.\./i })).toBeDisabled();
    });

    it("hides the saved confirmation after two seconds", async () => {
      const user = userEvent.setup();
      renderManager();
      await user.click(await screen.findByRole("button", { name: /create new/i }));
      mockAuthedFetch.mockResolvedValueOnce(okResponse());

      // Fake timers go on only for the timer-owned part: RTL's async wrapper
      // around user-event waits on a real setTimeout and would hang, so the
      // click is dispatched with fireEvent (wrapped in act by RTL).
      vi.useFakeTimers();
      fireEvent.click(screen.getByRole("button", { name: /save skill/i }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText("✓ Saved")).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(screen.queryByText("✓ Saved")).not.toBeInTheDocument();
    });

    it("stays in edit mode without confirming when the server rejects the save", async () => {
      const user = userEvent.setup();
      renderManager();
      await user.click(await screen.findByRole("button", { name: /create new/i }));
      mockAuthedFetch.mockResolvedValueOnce(failResponse());

      await user.click(screen.getByRole("button", { name: /save skill/i }));

      await waitFor(() => expect(screen.getByRole("button", { name: /save skill/i })).toBeEnabled());
      expect(screen.queryByText("✓ Saved")).not.toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: "Skill content" })).toBeInTheDocument();
    });

    it("logs and stays in edit mode when the save request throws", async () => {
      const user = userEvent.setup();
      renderManager();
      await user.click(await screen.findByRole("button", { name: /create new/i }));
      mockAuthedFetch.mockRejectedValueOnce(new Error("boom"));

      await user.click(screen.getByRole("button", { name: /save skill/i }));

      await waitFor(() =>
        expect(consoleError).toHaveBeenCalledWith("Failed to save skill:", expect.any(Error)),
      );
      expect(screen.queryByText("✓ Saved")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /save skill/i })).toBeEnabled();
    });

    it("does not post when there is no auth token", async () => {
      const user = userEvent.setup();
      mockGetToken.mockReturnValue(null);
      renderManager();
      await user.click(await screen.findByRole("button", { name: /create new/i }));

      await user.click(screen.getByRole("button", { name: /save skill/i }));

      expect(mockAuthedFetch).not.toHaveBeenCalled();
      expect(screen.queryByText("✓ Saved")).not.toBeInTheDocument();
    });

    it("does not post when no agent id is provided", async () => {
      const user = userEvent.setup();
      render(<SkillManager isOpen onClose={vi.fn()} />);
      await user.click(await screen.findByRole("button", { name: /create new/i }));

      await user.click(screen.getByRole("button", { name: /save skill/i }));

      expect(mockAuthedFetch).not.toHaveBeenCalled();
    });
  });

  describe("deleting", () => {
    it("asks for confirmation before deleting and does not call the API yet", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill();
      mockAuthedFetch.mockClear();

      await user.click(screen.getByRole("button", { name: /^delete$/i }));

      const dialog = screen.getByRole("dialog", { name: "Delete this agent's saved skill?" });
      expect(dialog).toHaveAttribute("aria-modal", "true");
      expect(mockAuthedFetch).not.toHaveBeenCalled();
    });

    it("keeps the skill when the user chooses Keep skill", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill("# Saved skill");
      mockAuthedFetch.mockClear();
      await user.click(screen.getByRole("button", { name: /^delete$/i }));

      await user.click(screen.getByRole("button", { name: "Keep skill" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.getByText("# Saved skill")).toBeInTheDocument();
      expect(mockAuthedFetch).not.toHaveBeenCalled();
    });

    it("dismisses the confirmation when its backdrop is clicked", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill();
      await user.click(screen.getByRole("button", { name: /^delete$/i }));

      await user.click(screen.getByRole("dialog"));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("keeps the confirmation open when the dialog body is clicked", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill();
      await user.click(screen.getByRole("button", { name: /^delete$/i }));

      await user.click(screen.getByText("Delete this agent's saved skill?"));

      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("sends a DELETE and clears the skill once confirmed", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill("# Saved skill");
      mockAuthedFetch.mockClear();
      mockAuthedFetch.mockResolvedValueOnce(okResponse());
      await user.click(screen.getByRole("button", { name: /^delete$/i }));

      await user.click(confirmDeleteButton());

      expect(await screen.findByText("No skill attached")).toBeInTheDocument();
      expect(mockAuthedFetch).toHaveBeenCalledWith(`${SKILLS_URL}/agent-1`, {
        method: "DELETE",
        headers: { Authorization: "Bearer tok-123" },
      });
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("closes the dialog without calling the API when there is no auth token", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill("# Saved skill");
      mockAuthedFetch.mockClear();
      await user.click(screen.getByRole("button", { name: /^delete$/i }));
      mockGetToken.mockReturnValue(null);

      await user.click(confirmDeleteButton());

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(mockAuthedFetch).not.toHaveBeenCalled();
      expect(screen.getByText("# Saved skill")).toBeInTheDocument();
    });

    it("logs and keeps the skill when the delete request throws", async () => {
      const user = userEvent.setup();
      await renderWithSavedSkill("# Saved skill");
      mockAuthedFetch.mockRejectedValueOnce(new Error("boom"));
      await user.click(screen.getByRole("button", { name: /^delete$/i }));

      await user.click(confirmDeleteButton());

      await waitFor(() =>
        expect(consoleError).toHaveBeenCalledWith("Failed to delete skill:", expect.any(Error)),
      );
      expect(screen.getByText("# Saved skill")).toBeInTheDocument();
    });
  });
});

/** The confirm button inside the delete dialog (the toolbar also has a "Delete"). */
function confirmDeleteButton(): HTMLElement {
  return within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" });
}
