import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentDetailPanel } from "../results/AgentDetailPanel";
import type { AgentRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// FR-044 / GAPS §0.4 — AgentDetailPanel system prompt and task message rendering
//
// When an agent carries `systemPrompt` (from the new SSE event) alongside a task
// message, the detail panel renders both sections verbatim:
// - "System prompt" section with the exact composed factory output
// - "Task message" section with the targeted control payload
// No deepagents wrapper text (base prompt, tool instructions, SKILLS_SYSTEM_PROMPT,
// todo/subagent sections) ever appears — these are stripped by the deepagents
// harness, not by the viewer.
// ─────────────────────────────────────────────────────────────────────────────

function agent(over: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id: "test-agent",
    name: "Test Agent",
    role: "worker",
    icon: "",
    status: "done",
    output: "Agent output",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    contextSources: [],
    toolCalls: [],
    ...over,
  };
}

describe("AgentDetailPanel — systemPrompt and task message rendering", () => {
  it("renders both system prompt and task message sections verbatim when expanded", () => {
    const systemPromptText = "You are a helpful assistant.\n\nRespond with clear, accurate information.";
    const taskMessageText = "Brief: Write a summary of the uploaded document.";

    const { container } = render(
      <AgentDetailPanel
        agent={agent({
          systemPrompt: systemPromptText,
          inputPrompt: taskMessageText,
        })}
        onBack={() => {}}
      />,
    );

    // Verify the "System prompt" header is present (button with label)
    const systemPromptButton = screen.getByRole("button", { name: /System prompt/i });
    expect(systemPromptButton).toBeInTheDocument();

    // Expand the system prompt section
    fireEvent.click(systemPromptButton);

    // Verify the exact system prompt text is rendered in a pre element
    const systemPromptPre = Array.from(container.querySelectorAll("pre")).find(
      (el) => el.textContent === systemPromptText,
    );
    expect(systemPromptPre).toBeDefined();
    expect(systemPromptPre?.textContent).toBe(systemPromptText);

    // Verify the "Task message" header is present
    const taskMessageButton = screen.getByRole("button", { name: /Task message/i });
    expect(taskMessageButton).toBeInTheDocument();

    // Expand the task message section
    fireEvent.click(taskMessageButton);

    // Verify the exact task message text is rendered in a pre element
    const taskMessagePre = Array.from(container.querySelectorAll("pre")).find(
      (el) => el.textContent === taskMessageText,
    );
    expect(taskMessagePre).toBeDefined();
    expect(taskMessagePre?.textContent).toBe(taskMessageText);
  });

  it("renders system prompt and task message with independent expand state", () => {
    const systemPromptText = "System instruction.";
    const taskMessageText = "Task instruction.";

    const { container } = render(
      <AgentDetailPanel
        agent={agent({
          systemPrompt: systemPromptText,
          inputPrompt: taskMessageText,
        })}
        onBack={() => {}}
      />,
    );

    // Helper to find pre elements by their content
    const findPre = (text: string) =>
      Array.from(container.querySelectorAll("pre")).find((el) => el.textContent === text);

    // Both sections start collapsed — text not visible in pre elements
    expect(findPre(systemPromptText)).not.toBeDefined();
    expect(findPre(taskMessageText)).not.toBeDefined();

    // Expand only the system prompt
    const systemPromptButton = screen.getByRole("button", { name: /System prompt/i });
    fireEvent.click(systemPromptButton);

    // System prompt visible, task message still hidden
    expect(findPre(systemPromptText)).toBeDefined();
    expect(findPre(taskMessageText)).not.toBeDefined();

    // Expand the task message
    const taskMessageButton = screen.getByRole("button", { name: /Task message/i });
    fireEvent.click(taskMessageButton);

    // Both now visible
    expect(findPre(systemPromptText)).toBeDefined();
    expect(findPre(taskMessageText)).toBeDefined();

    // Collapse the system prompt
    fireEvent.click(systemPromptButton);

    // System prompt hidden, task message still visible
    expect(findPre(systemPromptText)).not.toBeDefined();
    expect(findPre(taskMessageText)).toBeDefined();
  });

  it("preserves exact whitespace and formatting in both sections", () => {
    const systemPromptText = "You are an expert.\n\nCore instruction:\n- Point 1\n- Point 2";
    const taskMessageText = "Task: Do something\nDetails:\n  • Requirement A\n  • Requirement B";

    const { container } = render(
      <AgentDetailPanel
        agent={agent({
          systemPrompt: systemPromptText,
          inputPrompt: taskMessageText,
        })}
        onBack={() => {}}
      />,
    );

    // Expand both sections
    fireEvent.click(screen.getByRole("button", { name: /System prompt/i }));
    fireEvent.click(screen.getByRole("button", { name: /Task message/i }));

    // Find all pre elements and verify their content matches exactly
    const preElements = container.querySelectorAll("pre");
    expect(preElements.length).toBeGreaterThanOrEqual(2);

    // The first expanded pre should contain the system prompt
    const systemPromptPre = Array.from(preElements).find(
      (el) => el.textContent === systemPromptText,
    );
    expect(systemPromptPre).toBeDefined();
    expect(systemPromptPre?.textContent).toBe(systemPromptText);

    // The second expanded pre should contain the task message
    const taskMessagePre = Array.from(preElements).find(
      (el) => el.textContent === taskMessageText,
    );
    expect(taskMessagePre).toBeDefined();
    expect(taskMessagePre?.textContent).toBe(taskMessageText);
  });
});
