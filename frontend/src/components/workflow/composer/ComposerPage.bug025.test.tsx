/**
 * QA-KB-050 / BUG-025 — the composer decides what is core from DashboardLayout's shared
 * workflowType, which is "user_stories" on /workflows/new, /edit and /run. Every case mounts
 * ComposerPage the way those routes do (workflowType "user_stories", no builtinCanvasType) and
 * asserts the CORRECT behaviour for a custom composition. Red until the composer derives its own
 * pipeline type. Cards: BUG-025, ISS-961..965. Strict xfail markers removed at verification.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { render } from "@testing-library/react";
import type { AgentDef, WorkflowType } from "@/types/index";

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
  saveUserWorkflow: vi.fn(),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

import { ComposerPage } from "./ComposerPage";
import { CanvasNode } from "./CanvasNode";
import { AgentRow } from "./AgentRow";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

const mk = (id: string, name: string, pipeline_type: string, order = 1): AgentDef =>
  ({ id, name, role: `${name} role`, description: "d", pipeline_type, order, icon: "", estimated_duration: 60, has_skill: false }) as AgentDef;

const US = [
  mk("domain-analyst", "Domain Discovery Agent", "user_stories", 1),
  mk("epic-architect", "Backlog Architecture Agent", "user_stories", 2),
  mk("story-estimator", "Estimation Agent", "user_stories", 3),
  mk("nfr-specialist", "NFR Agent", "user_stories", 4),
  mk("backlog-reviewer", "Backlog Reviewer", "user_stories", 5),
  mk("backlog-compiler", "Backlog Compiler Agent", "user_stories", 6),
];

function renderComposer(props: Record<string, unknown> = {}, agents: AgentDef[] = US) {
  return renderWithProviders(
    <SkillsHooksProvider>
      <ComposerPage workflowType={"user_stories" as WorkflowType} onBack={() => {}} {...props} />
    </SkillsHooksProvider>,
    { preloadedState: { agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded", error: null } } },
  );
}

beforeEach(() => vi.clearAllMocks());

describe("BUG-025 — composer on a custom route (stale user_stories workflowType)", () => {
  it("BUG-025: library-added agents are removable on /workflows/new", () => {
    renderComposer({ initialAgentIds: ["epic-architect", "story-estimator", "domain-analyst"] });
    for (const n of ["Backlog Architecture Agent", "Estimation Agent", "Domain Discovery Agent"]) {
      expect(screen.getByRole("button", { name: `Remove ${n}` })).toBeEnabled();
    }
  });

  it("ISS-961: a saved custom workflow reopened via Edit has removable agents and no Core badge", () => {
    renderComposer({ initialAgentIds: ["epic-architect", "story-estimator"], initialUserWorkflowId: "wf-1" });
    expect(screen.getByRole("button", { name: "Remove Backlog Architecture Agent" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Remove Estimation Agent" })).toBeEnabled();
    expect(screen.queryByText(/^Core$/)).not.toBeInTheDocument();
  });

  it("ISS-962: the Add-agent library does not offer core agents to a custom workflow", async () => {
    renderComposer({ initialAgentIds: [] });
    await userEvent.click(screen.getByRole("button", { name: /Add agent at end/i }));
    expect(screen.queryByText("Domain Discovery Agent")).not.toBeInTheDocument();
  });

  it("ISS-964: Simple view shows brief recommendations for a matching brief", async () => {
    renderComposer({ initialAgentIds: [] });
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
    const brief = screen.getByLabelText(/brief/i);
    await userEvent.type(brief, "estimate story points and effort for the backlog items");
    expect(await screen.findByText(/Suggested agents for your brief/i)).toBeInTheDocument();
  });

  it("ISS-965: the root-agent cap counts every root agent of a custom composition", () => {
    const extra = Array.from({ length: 10 }, (_, i) => mk(`cust-${i}`, `Custom ${i}`, "custom", 10 + i));
    renderComposer(
      { initialAgentIds: [...US.map((a) => a.id), ...extra.map((a) => a.id)] },
      [...US, ...extra],
    );
    for (const b of screen.getAllByRole("button", { name: /Insert agent before step/i })) expect(b).toBeDisabled();
  });
});

describe("ISS-963 — Core badge and Remove lock must agree, and a lock must be visible", () => {
  const epic = US[1];
  const nodeProps = {
    agent: epic, pipelineType: "user_stories" as never, selected: false, modelOptions: [], isChild: false,
    hasChildren: false, cardWidth: 280, left: 0, top: 0, onSelect: vi.fn(), onRemove: vi.fn(),
  };

  it("ISS-963: CanvasNode shows a Core badge iff Remove is disabled", () => {
    render(<CanvasNode {...nodeProps} />);
    const disabled = (screen.getByTitle(/Core agents can't be removed|Remove agent/) as HTMLButtonElement).disabled;
    expect(!!screen.queryByText(/^Core$/)).toBe(disabled);
  });

  it("ISS-963: a disabled CanvasNode Remove is greyed, not invisible", () => {
    render(<CanvasNode {...nodeProps} />);
    const btn = screen.getByTitle(/Core agents can't be removed|Remove agent/);
    expect(btn).toBeDisabled();
    expect(btn.className).not.toContain("disabled:opacity-0");
  });

  it("ISS-963: AgentRow shows a Core badge iff Remove is disabled", () => {
    render(
      <AgentRow agent={epic} index={0} total={1} pipelineType={"user_stories" as WorkflowType} selection={undefined}
        onSelection={() => {}} onMoveUp={() => {}} onMoveDown={() => {}} onRemove={() => {}} />,
    );
    const row = screen.getByTestId("agent-row-epic-architect");
    const disabled = (within(row).getByRole("button", { name: `Remove ${epic.name}` }) as HTMLButtonElement).disabled;
    expect(!!within(row).queryByText(/^Core$/)).toBe(disabled);
  });
});
