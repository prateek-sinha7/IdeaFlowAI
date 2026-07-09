/**
 * SC-001 / INV-1 — the Configure screen is a GENERIC per-run setup surface. The
 * Templates + Design System accordions render ONLY when the selected deliverable
 * DECLARES `context_providers:[opendesign]` — the SAME declared signal the Wave-1
 * backend seam keys on — NEVER a prototype-name branch. Any deliverable that
 * declares the opendesign context provider GAINS the accordions with zero
 * per-deliverable code; one that does not shows only Describe + Review Gates +
 * Workflow Settings.
 *
 * The screen also lands the ND-1 consumer: Save-draft persists the composed
 * run-draft CLIENT-SIDE (sessionStorage), hydrated on mount and cleared once at
 * launch; launch composes the GENERIC launch inputs (template_id/design_system_id/
 * agent_ids/selections) — never a prototype-specific path.
 *
 * These tests render the REAL ConfigureScreen and mock only the seams: the network
 * read (`getWorkflowDetail`) and the heavy child surfaces (which fetch live
 * registries) so the gating + composition is what's under test.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ConfigureScreen } from "./ConfigureScreen";
import type { WorkflowDetail } from "@/lib/api";
import { readDraft, clearDraft, saveDraft } from "@/lib/draft";

const mockGetWorkflowDetail = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflowDetail: (token: string, id: string) => mockGetWorkflowDetail(token, id),
}));

// The Template/DS pickers + Advanced levers fetch live registries — stub them to
// observable markers so the gating + composition is what's under test.
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([]),
  listDesignSystems: vi.fn().mockResolvedValue([]),
}));
vi.mock("./prototype/TemplateGallery", () => ({
  TemplateGallery: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button data-testid="stub-template-gallery" onClick={() => onSelect("kanban")}>
      pick-template
    </button>
  ),
}));
vi.mock("./prototype/DesignSystemPicker", () => ({
  DesignSystemPicker: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button data-testid="stub-ds-picker" onClick={() => onSelect("midnight")}>
      pick-ds
    </button>
  ),
}));
vi.mock("./AgentsPopup", () => ({
  AdvancedExpander: () => <div data-testid="stub-advanced-expander" />,
}));
vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: () => <div data-testid="stub-review-gates" />,
}));

function detail(contextProviders: string[]): WorkflowDetail {
  return {
    id: "any-deliverable",
    name: "Any Deliverable",
    description: "",
    planner: "deep_planner",
    clarify_mode: "auto",
    clarify_defaults: [],
    context_providers: contextProviders,
    deliverable: { strategy: "x", name: "y" },
    steps: [
      { agent_id: "a1", name: "Agent One", role: "r", order: 1, strategy: "s", gates: [], validators: [], compaction: null, task_source: null, declared_gate: null },
    ],
  };
}

/** Open an accordion by clicking its header (needed to reach the picker stub). */
async function openAccordion(user: ReturnType<typeof userEvent.setup>, testId: string) {
  const section = screen.getByTestId(testId);
  const header = section.querySelector("button");
  if (header) await user.click(header);
}

describe("ConfigureScreen — declared-signal accordion gating (SC-001)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("renders the Templates + Design System accordions when context_providers includes 'opendesign'", async () => {
    mockGetWorkflowDetail.mockResolvedValue(detail(["opendesign"]));
    render(<ConfigureScreen workflowId="any-deliverable" />);

    await waitFor(() =>
      expect(mockGetWorkflowDetail).toHaveBeenCalledWith("test-token", "any-deliverable"),
    );

    expect(await screen.findByTestId("accordion-describe")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-gates")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-settings")).toBeInTheDocument();

    expect(screen.getByTestId("accordion-templates")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-designsystem")).toBeInTheDocument();
  });

  it("HIDES the Templates + Design System accordions when 'opendesign' is NOT declared", async () => {
    mockGetWorkflowDetail.mockResolvedValue(detail([]));
    render(<ConfigureScreen workflowId="any-deliverable" />);

    expect(await screen.findByTestId("accordion-describe")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-gates")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-settings")).toBeInTheDocument();

    expect(screen.queryByTestId("accordion-templates")).not.toBeInTheDocument();
    expect(screen.queryByTestId("accordion-designsystem")).not.toBeInTheDocument();
  });

  it("hydrates the brief from a saved draft on mount (ND-1)", async () => {
    mockGetWorkflowDetail.mockResolvedValue(detail(["opendesign"]));
    saveDraft({ brief: "restored brief" });

    render(<ConfigureScreen workflowId="any-deliverable" />);

    const briefField = (await screen.findByTestId("configure-brief")) as HTMLTextAreaElement;
    await waitFor(() => expect(briefField.value).toBe("restored brief"));
  });

  it("Save-draft writes the composed payload client-side (round-trip)", async () => {
    mockGetWorkflowDetail.mockResolvedValue(detail(["opendesign"]));
    clearDraft();
    const user = userEvent.setup();

    render(<ConfigureScreen workflowId="any-deliverable" />);

    const briefField = await screen.findByTestId("configure-brief");
    await user.type(briefField, "hello");
    await openAccordion(user, "accordion-templates");
    await user.click(screen.getByTestId("stub-template-gallery")); // sets templateId
    await openAccordion(user, "accordion-designsystem");
    await user.click(screen.getByTestId("stub-ds-picker")); // sets designSystemId
    await user.click(screen.getByTestId("configure-save-draft"));

    const saved = readDraft();
    expect(saved).not.toBeNull();
    expect(saved?.brief).toBe("hello");
    expect(saved?.templateId).toBe("kanban");
    expect(saved?.designSystemId).toBe("midnight");
    expect(saved?.agentIds).toEqual(["a1"]);
  });

  it("launch composes the GENERIC launch inputs and clears the draft once", async () => {
    mockGetWorkflowDetail.mockResolvedValue(detail(["opendesign"]));
    const onLaunch = vi.fn();
    const user = userEvent.setup();

    render(<ConfigureScreen workflowId="any-deliverable" onLaunch={onLaunch} />);

    await screen.findByTestId("configure-brief");
    await openAccordion(user, "accordion-templates");
    await user.click(screen.getByTestId("stub-template-gallery"));
    await openAccordion(user, "accordion-designsystem");
    await user.click(screen.getByTestId("stub-ds-picker"));
    await user.click(screen.getByTestId("configure-launch"));

    // Generic LaunchCommand fields — never a prototype-specific path.
    expect(onLaunch).toHaveBeenCalledTimes(1);
    const cmd = onLaunch.mock.calls[0][0];
    expect(cmd.template_id).toBe("kanban");
    expect(cmd.design_system_id).toBe("midnight");
    expect(cmd.agent_ids).toEqual(["a1"]);

    // Draft cleared once at launch (ND-1 read-and-clear).
    expect(readDraft()).toBeNull();
  });
});
