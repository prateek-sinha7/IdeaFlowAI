/**
 * ISS-686 (QA-KB-025) — switching the "Task source type" to a parser outside
 * PARSER_TARGET (heading_tasks, or any newly registered parser) must not carry
 * the PREVIOUS parser's `target` file along. Guards FIX-706 (markers dropped at verification).
 *
 * ISS-918 (INFERRED sibling) — the Simple view seeds the literal "tasks.json",
 * disagreeing with the rail's PARSER_TARGET.json_tasks ("build/tasks.json").
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef } from "@/types/index";
import type { StepSelection } from "../AgentsPopup";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));
vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: [], categories: [] }),
}));

import { CanvasConfigRail } from "./CanvasConfigRail";

const tp = (name: string) => ({
  kind: "task_parser" as const, name, user_allowed: true, description: name, security_gated: false, config_schema: {},
});
const PALETTE: CapabilitiesPalette = {
  capabilities: [tp("heading_tasks"), tp("json_tasks"), tp("screen_plan")],
  model_catalog: [],
};
const mk = (id: string, name: string) =>
  ({ id, name, role: "r", description: "d", pipeline_type: "custom", order: 1, icon: "", estimated_duration: 1, has_skill: false }) as AgentDef;

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("ISS-686 task-source parser switch keeps the previous parser's file", () => {
  it("json_tasks -> heading_tasks does not save target build/tasks.json", async () => {
    const onSelection = vi.fn();
    renderWithProviders(
      <CanvasConfigRail
        agent={mk("writer", "Writer")}
        index={2}
        total={3}
        selection={{
          strategy: "wave_scheduler",
          task_source: { kind: "parsed", parser: "json_tasks", target: "build/tasks.json", source_step: "prototype-plan" },
        }}
        onSelection={onSelection}
        priorAgents={[mk("prototype-plan", "Plan"), mk("researcher", "Researcher")]}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: /config/i }));
    const select = await screen.findByLabelText(/^task source type$/i);
    await userEvent.selectOptions(select, "heading_tasks");
    const [, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(sel?.task_source?.parser).toBe("heading_tasks");
    expect(sel?.task_source?.target).not.toBe("build/tasks.json");
  });
});

describe("ISS-918 Simple view seeds a tasks.json that disagrees with the rail", () => {
  it("AgentsPopup does not seed the bare literal target: \"tasks.json\"", () => {
    const src = readFileSync(path.join(__dirname, "..", "AgentsPopup.tsx"), "utf8");
    expect(src).not.toContain('target: "tasks.json"');
  });
});
