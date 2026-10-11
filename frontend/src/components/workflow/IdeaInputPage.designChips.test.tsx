/**
 * IdeaInputPage — the attach-design chips for a workflow whose catalog row
 * declares `context_providers: [opendesign]`: opening the picker, name/id chips,
 * removal, the per-mode "required" prompts, custom bodies, and which design
 * fields reach `onRun`. Complements IdeaInputPage.designPicker.test.tsx, which
 * proves the declare-then-pick-then-run happy path.
 *
 * Boundary: DesignPickerModal is a double (the real one fetches template and
 * design-system catalogs on open) exposing `onChange`/`onClose` as buttons.
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IdeaInputPage } from "./IdeaInputPage";
import renderWithProviders from "@/test/renderWithProviders";
import type { AgentDef, WorkflowType } from "@/types/index";

const WF = "prototype_v2" as WorkflowType;

interface Selection {
  templateId: string | null;
  designSystemId: string | null;
  templateName?: string | null;
  designSystemName?: string | null;
  customTemplateBody?: string | null;
  customDsBody?: string | null;
}

interface PickerHandle {
  open: boolean;
  designMode: string;
  onClose: () => void;
  onChange: (update: () => Selection) => void;
}

vi.mock("./composer/DesignPickerModal", () => ({
  DesignPickerModal: ({ open, designMode, onClose, onChange }: PickerHandle) =>
    open ? (
      <div role="dialog" aria-label={`Design picker (${designMode})`}>
        <button type="button" onClick={() => onChange(() => ({ templateId: "tmpl-1", templateName: "Dashboard Kit", designSystemId: "ds-1", designSystemName: "Material" }))}>pick named</button>
        <button type="button" onClick={() => onChange(() => ({ templateId: "tmpl-1", designSystemId: "ds-1" }))}>pick ids</button>
        <button type="button" onClick={() => onChange(() => ({ templateId: "tmpl-1", designSystemId: null }))}>pick template only</button>
        <button type="button" onClick={() => onChange(() => ({ templateId: "tmpl-c", designSystemId: "ds-c", customTemplateBody: "<tpl/>", customDsBody: "# ds" }))}>pick custom</button>
        <button type="button" onClick={onClose}>close picker</button>
      </div>
    ) : null,
}));

vi.mock("./AgentsPopup", () => ({ AgentsPopup: () => null }));
vi.mock("./ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));
vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

const AGENT: AgentDef = {
  id: "reading-planner",
  name: "Reading Planner",
  role: "r",
  description: "d",
  pipeline_type: "prototype_v2",
  order: 1,
  icon: "x",
  estimated_duration: 0,
  has_skill: false,
};

function renderPage(designMode: "web" | "deck") {
  const onRun = vi.fn();
  renderWithProviders(<IdeaInputPage workflowType={WF} onBack={vi.fn()} onRun={onRun} />, {
    preloadedState: {
      agents: { agents: [AGENT], totalCount: 1, pipelines: {}, status: "succeeded", error: null },
      global: {
        workflows: [
          {
            id: "prototype_v2",
            name: "PDF to Prototype",
            description: "d",
            step_count: 1,
            steps: [],
            user_launchable: true,
            context_providers: ["opendesign"],
            design_mode: designMode,
          },
        ],
      } as never,
    },
  });
  return { onRun };
}

const brief = () => screen.getByRole("textbox", { name: "Brief description" });

async function openPickerAndPick(user: ReturnType<typeof userEvent.setup>, pick: string) {
  await user.click(screen.getByRole("button", { name: /attach design/i }));
  await user.click(screen.getByRole("button", { name: pick }));
}

describe("IdeaInputPage design chips", () => {
  it("opens the picker in the workflow's design mode from Attach design and closes it again", async () => {
    const user = userEvent.setup();
    renderPage("deck");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /attach design/i }));
    expect(screen.getByRole("dialog", { name: "Design picker (deck)" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close picker" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the picked template and design-system names as chips", async () => {
    const user = userEvent.setup();
    renderPage("web");

    await openPickerAndPick(user, "pick named");

    expect(screen.getByText("Dashboard Kit")).toBeInTheDocument();
    expect(screen.getByText("Material")).toBeInTheDocument();
    expect(screen.queryByText("tmpl-1")).not.toBeInTheDocument();
  });

  it("falls back to the ids as chip labels when the picker supplies no names", async () => {
    const user = userEvent.setup();
    renderPage("web");

    await openPickerAndPick(user, "pick ids");

    expect(screen.getByText("tmpl-1")).toBeInTheDocument();
    expect(screen.getByText("ds-1")).toBeInTheDocument();
  });

  it("removes the template chip and drops the template from the launch payload", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("web");
    await user.type(brief(), "Build it");
    await openPickerAndPick(user, "pick custom");
    await user.click(screen.getByRole("button", { name: "close picker" }));

    await user.click(screen.getByRole("button", { name: "Remove template" }));
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(screen.queryByText("tmpl-c")).not.toBeInTheDocument();
    expect(onRun.mock.calls[0][3]).toEqual({
      gate_agent_ids: [],
      design_system_id: "ds-c",
      custom_ds_body: "# ds",
    });
  });

  it("removes the design-system chip, asks for a design system again and refuses to run", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("web");
    await user.type(brief(), "Build it");
    await openPickerAndPick(user, "pick ids");
    await user.click(screen.getByRole("button", { name: "close picker" }));

    await user.click(screen.getByRole("button", { name: "Remove design system" }));

    expect(screen.queryByText("ds-1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Design system required" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run workflow" }));
    expect(onRun).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Design picker (web)" })).toBeInTheDocument();
  });

  it("reopens the picker from the Design system required prompt", async () => {
    const user = userEvent.setup();
    renderPage("web");

    await user.click(screen.getByRole("button", { name: "Design system required" }));

    expect(screen.getByRole("dialog", { name: "Design picker (web)" })).toBeInTheDocument();
  });

  it("asks for a template in deck mode and runs with only the template once one is picked", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("deck");
    await user.type(brief(), "Make slides");
    expect(screen.getByRole("button", { name: "Template required" })).toBeInTheDocument();

    await openPickerAndPick(user, "pick template only");
    await user.click(screen.getByRole("button", { name: "close picker" }));
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(screen.queryByRole("button", { name: "Template required" })).not.toBeInTheDocument();
    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: [], template_id: "tmpl-1" });
  });

  it("sends custom template and design-system bodies along with their ids", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("web");
    await user.type(brief(), "Build it");
    await openPickerAndPick(user, "pick custom");
    await user.click(screen.getByRole("button", { name: "close picker" }));

    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({
      gate_agent_ids: [],
      template_id: "tmpl-c",
      design_system_id: "ds-c",
      custom_template_body: "<tpl/>",
      custom_ds_body: "# ds",
    });
  });
});
