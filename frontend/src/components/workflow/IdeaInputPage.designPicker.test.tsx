/**
 * The "pick a design" wiring for a file-backed workflow that declares
 * `context_providers: [opendesign]` (e.g. `prototype_v2`) — the same
 * DesignPickerModal ComposerPage already mounts, offered on IdeaInputPage
 * (the launch surface a catalog card with no dedicated wizard falls to,
 * see HomeLaunchGrid.handleClick -> selectWorkflowWizardPath), driven off
 * the LIVE catalog row's declared `context_providers`/`design_mode` rather
 * than a hardcoded workflow-name list.
 *
 * Strategy mirrors IdeaInputPage.selections.test.tsx: real IdeaInputPage,
 * a tiny AgentsPopup double, DesignPickerModal stubbed to a button so the
 * test can drive a selection deterministically without hitting the
 * template/design-system catalog endpoints.
 */

import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { AgentDef, WorkflowType } from "@/types/index";

// `prototype_v2` is a real, entitled, user_launchable workflow that declares
// `context_providers: [opendesign]`, but is not in the FE `WorkflowType`
// string-literal union — HomeLaunchGrid already works around this the same
// way (`row.id as WorkflowType`) rather than widening the exhaustive union
// (Sidebar.tsx, etc. `Record<WorkflowType, ...>` maps would all need a new
// case). Out of scope here; cast at the one call site that needs it.
const PDF_TO_PROTOTYPE = "prototype_v2" as WorkflowType;

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

// Stand in for the real picker (which fetches /api/prototype/templates +
// /api/design-systems on open) — exposes onChange as a button so a selection
// can be driven deterministically.
vi.mock("./composer/DesignPickerModal", () => ({
  DesignPickerModal: ({
    open,
    onChange,
  }: {
    open: boolean;
    onChange: (update: (prev: { templateId: string | null; designSystemId: string | null }) => { templateId: string | null; designSystemId: string | null }) => void;
  }) =>
    open ? (
      <button
        type="button"
        data-testid="pick-design"
        onClick={() =>
          onChange(() => ({ templateId: "tmpl-1", designSystemId: "ds-1" }))
        }
      >
        pick design
      </button>
    ) : null,
}));

const mockAgents: AgentDef[] = [
  {
    id: "reading-planner",
    name: "Reading Planner",
    role: "Plans reading",
    description: "Assigns documents to readers",
    pipeline_type: "prototype_v2",
    order: 1,
    icon: "search",
    estimated_duration: 60,
    has_skill: false,
  },
];

function renderPage(
  onRun = vi.fn(),
  contextProviders: string[] = ["opendesign"],
) {
  renderWithProviders(
    <SkillsHooksProvider>
      <IdeaInputPage workflowType={PDF_TO_PROTOTYPE} onBack={vi.fn()} onRun={onRun} />
    </SkillsHooksProvider>,
    {
      preloadedState: {
        agents: {
          agents: mockAgents,
          totalCount: mockAgents.length,
          pipelines: {},
          status: "succeeded",
          error: null,
        },
        global: {
          workflows: [
            {
              id: "prototype_v2",
              name: "PDF to Prototype",
              description: "Build a prototype from uploaded PDFs.",
              step_count: 1,
              steps: [],
              user_launchable: true,
              context_providers: contextProviders,
              design_mode: "web",
            },
          ],
        } as never,
      },
    },
  );
  return { onRun };
}

describe("IdeaInputPage — opendesign design-picker wiring", () => {
  it("offers the picker for a workflow that declares opendesign, and threads the selection into onRun", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    expect(screen.getByRole("button", { name: /attach design/i })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox"), "Build the prototype.");
    // Web mode requires a design system — Run opens the picker instead of running.
    await user.click(screen.getByRole("button", { name: /run workflow/i }));
    expect(onRun).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("pick-design"));
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [, , , extraParams] = onRun.mock.calls[0];
    expect(extraParams).toMatchObject({
      template_id: "tmpl-1",
      design_system_id: "ds-1",
    });
  });

  it("does not offer the picker for a workflow that never declares opendesign", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage(vi.fn(), []);

    expect(screen.queryByRole("button", { name: /attach design/i })).not.toBeInTheDocument();

    await user.type(screen.getByRole("textbox"), "Build the prototype.");
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [, , , extraParams] = onRun.mock.calls[0];
    // FIX-323 — the launch surface ALWAYS sends `gate_agent_ids` (gate selection
    // starts `touched: true`, IdeaInputPage.tsx:1001), so an empty selection
    // reaches the backend as an explicit "no gates". Same rule the sibling
    // IdeaInputPage.selections/imageInput/modelOverrides tests pin. (Note: the
    // card store's FIX-323 file is an unrelated /login fix — an ID collision per
    // ADR-0051; the rule's rationale lives at LaunchWizard.tsx:344 and
    // ReviewGatesSection.tsx:74.) What THIS test guards is unchanged: no design
    // params ride along when the workflow never declares opendesign.
    expect(extraParams).toEqual({ gate_agent_ids: [] });
    expect(extraParams).not.toHaveProperty("template_id");
    expect(extraParams).not.toHaveProperty("design_system_id");
  });
});
