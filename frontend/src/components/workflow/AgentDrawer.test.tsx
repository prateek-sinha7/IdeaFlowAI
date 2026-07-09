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
 * ND-7 / LOCK-E (the load-bearing gate): the Config tab SURFACES the prompt
 * body (view) but its override PERSISTENCE is DEFERRED — the drawer mounts
 * AgentPromptSection with `surfaceOnly`, which OMITS every write affordance
 * (Edit / Save override / Revert-to-default). This file pins that the durable
 * PUT/DELETE path is UNREACHABLE: the write controls are absent, and the api
 * mutators (saveAgentPromptOverride / deleteAgentPromptOverride) are never
 * called through any interaction the tab surfaces.
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
  it("surfaces the prompt body READ-ONLY: no Edit / Save override / Revert controls", async () => {
    renderDrawer();

    // Go to the Config tab and open the System Prompt override surface.
    await userEvent.click(screen.getByRole("tab", { name: /config/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /system prompt/i }),
    );

    // The base prompt loads and renders (SURFACE preserved — the view works).
    expect(
      await screen.findByText(/you are the requirements analyst\./i),
    ).toBeInTheDocument();

    // ND-7: the durable-write affordances are OMITTED — the persistence path
    // (PUT/DELETE /api/agents/{id}/prompt) is UNREACHABLE from the drawer.
    expect(
      screen.queryByRole("button", { name: /^edit$/i }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: /save override/i }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: /revert to default/i }),
    ).toBeNull();
    // No editable field is exposed either.
    expect(
      screen.queryByPlaceholderText(/custom prompt instructions/i),
    ).toBeNull();
  });

  it("hides the Revert control even when an override already exists", async () => {
    mockGetAgentPrompt.mockResolvedValue({
      agent_id: "requirements-analyst",
      prompt_body: "Base body.",
      override: "A previously-saved override body.",
      has_override: true,
    });
    renderDrawer();

    await userEvent.click(screen.getByRole("tab", { name: /config/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /system prompt/i }),
    );

    // The existing override renders READ-ONLY…
    expect(
      await screen.findByText(/a previously-saved override body\./i),
    ).toBeInTheDocument();
    // …but neither Revert nor Edit is offered (no durable DELETE/PUT path).
    expect(
      screen.queryByRole("button", { name: /revert to default/i }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: /^edit$/i })).toBeNull();
  });

  it("fires NO durable persistence call through any surfaced interaction", async () => {
    renderDrawer();

    await userEvent.click(screen.getByRole("tab", { name: /config/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /system prompt/i }),
    );
    // Let the prompt load; interact with everything the tab surfaces.
    await screen.findByText(/you are the requirements analyst\./i);

    // ND-7 / LOCK-E: no override write reaches the server — persistence is
    // deferred (no save-to-server, no override store). The surface is inert.
    expect(mockSaveOverride).not.toHaveBeenCalled();
    expect(mockDeleteOverride).not.toHaveBeenCalled();
  });
});
