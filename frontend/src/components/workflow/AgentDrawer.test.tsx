/**
 * Phase 37-06 Task 1 — Agent drawer 4-tab inspector + ND-7 (LOCK-E) gate.
 *
 * The Agent drawer (AgentCapabilitiesModal) is a 4-tab inspector
 * (Overview / Skills / Hooks / Config) that REUSES the shipped sections:
 *   - Config  → AgentPromptSection (the per-agent prompt-override SURFACE)
 *   - Skills  → the per-agent Suggested Skills + Custom-skill surfaces
 *   - Hooks   → the per-agent Suggested Hooks surface
 *   - Overview→ the existing "What this agent does" + Pipeline surface
 *
 * ND-7 / LOCK-E (the load-bearing gate): the Config tab SURFACES the override
 * field but its PERSISTENCE is DEFERRED — editing the override MUST NOT fire a
 * durable save. This file pins that behaviorally: it spies on the api client
 * (saveAgentPromptOverride / deleteAgentPromptOverride) and asserts NEITHER is
 * called while the user edits the override.
 *
 * `@/lib/api` is mocked so the drawer renders without a real fetch, mirroring
 * AgentsPopup.reskin.test.tsx.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockGetAgentPrompt = vi.fn();
const mockSaveOverride = vi.fn();
const mockDeleteOverride = vi.fn();
const mockGetCapabilities = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getAgentPrompt: (...a: unknown[]) => mockGetAgentPrompt(...a),
  saveAgentPromptOverride: (...a: unknown[]) => mockSaveOverride(...a),
  deleteAgentPromptOverride: (...a: unknown[]) => mockDeleteOverride(...a),
  getCapabilities: (...a: unknown[]) => mockGetCapabilities(...a),
}));

import { AgentCapabilitiesModal } from "./AgentsPopup";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { AgentDef } from "@/types/index";

const AGENT: AgentDef = {
  id: "requirements-analyst",
  name: "Requirements Analyst",
  description:
    "Analyzes requirements and produces a spec, drafts acceptance criteria.",
  role: "analyst",
  pipeline_type: "prototype",
  estimated_duration: 30,
  order: 1,
  has_skill: true,
} as AgentDef;

beforeEach(() => {
  vi.clearAllMocks();
  mockGetAgentPrompt.mockResolvedValue({
    agent_id: "requirements-analyst",
    prompt_body: "You are the requirements analyst.",
    override: null,
    has_override: false,
  });
  mockGetCapabilities.mockResolvedValue({ capabilities: [], model_catalog: [] });
});

function renderDrawer() {
  return render(
    <SkillsHooksProvider>
      <AgentCapabilitiesModal agent={AGENT} agentIndex={0} onClose={vi.fn()} />
    </SkillsHooksProvider>,
  );
}

describe("Agent drawer — 4-tab inspector", () => {
  it("presents exactly four tabs: Overview / Skills / Hooks / Config", () => {
    renderDrawer();
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /skills/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /hooks/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /config/i })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(4);
  });

  it("Overview tab is the default surface (what this agent does)", () => {
    renderDrawer();
    expect(
      screen.getByRole("tab", { name: /overview/i }),
    ).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/what this agent does/i)).toBeInTheDocument();
  });

  it("Config tab surfaces the per-agent prompt-override (System Prompt)", async () => {
    renderDrawer();
    await userEvent.click(screen.getByRole("tab", { name: /config/i }));
    expect(
      screen.getByRole("button", { name: /system prompt/i }),
    ).toBeInTheDocument();
  });
});

describe("Agent drawer — ND-7 (LOCK-E): Config tab is SURFACE-ONLY", () => {
  it("editing the override fires NO durable persistence call", async () => {
    renderDrawer();

    // Go to the Config tab and open the System Prompt override surface.
    await userEvent.click(screen.getByRole("tab", { name: /config/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /system prompt/i }),
    );

    // The base prompt loads (getAgentPrompt), then enter edit mode.
    const editBtn = await screen.findByRole("button", { name: /edit/i });
    await userEvent.click(editBtn);

    // Edit the override text.
    const textarea = await screen.findByPlaceholderText(
      /custom prompt instructions/i,
    );
    await userEvent.type(textarea, "A per-agent override the user is typing");

    // ND-7 / LOCK-E: no durable override write occurs on edit — persistence is
    // deferred (no save-to-server, no override store). The surface is inert.
    expect(mockSaveOverride).not.toHaveBeenCalled();
    expect(mockDeleteOverride).not.toHaveBeenCalled();
  });
});
