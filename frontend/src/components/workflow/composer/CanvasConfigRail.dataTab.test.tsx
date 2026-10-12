import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { AgentDef } from "@/types/index";

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: vi.fn().mockResolvedValue({
    capabilities: [
      { kind: "mechanical", name: "assemble_backlog", user_allowed: true, description: "Long blurb.", security_gated: false, config_schema: {},
        process: "Checks every story and writes the backlog.", reads: ["stories/"], writes: ["backlog.md"] },
    ],
    model_catalog: [],
  }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));
vi.mock("@/hooks/useSkillsCatalog", () => ({ useSkillsCatalog: () => ({ skills: [], categories: [] }) }));

import { CanvasConfigRail } from "./CanvasConfigRail";

const mk = (o: Partial<AgentDef> & { id: string; name: string }) =>
  ({ role: "r", description: "", pipeline_type: "custom", order: 1, icon: "", estimated_duration: 0, has_skill: false, ...o }) as AgentDef;

const SPEC = mk({ id: "spec", name: "Spec Writer", extra: { produces: ["spec.md"] } });
const PLAN = mk({ id: "plan", name: "Planner", extra: { produces: ["spec.md", "build/screens.json"] } });
const BUILDER = mk({ id: "builder", name: "Builder", isCustom: true, prompt: "# Role\n\n**Build** the screens.", extra: { consumes: ["spec.md", "gone.md"] } });

function renderRail(agent = BUILDER) {
  const onDataFlowChange = vi.fn();
  const onPromptChange = vi.fn();
  renderWithProviders(
    <CanvasConfigRail agent={agent} index={2} total={3} selection={undefined} onSelection={vi.fn()}
      priorAgents={[SPEC, PLAN]} onDataFlowChange={onDataFlowChange} onPromptChange={onPromptChange} />,
  );
  return { onDataFlowChange, onPromptChange };
}

beforeEach(() => vi.clearAllMocks());

describe("CanvasConfigRail — Data tab (produces / consumes)", () => {
  it("replaces the Hooks tab", () => {
    renderRail();
    expect(screen.getByRole("tab", { name: "Data" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Hooks" })).toBeNull();
  });

  it("produces is a list: Enter adds a label, never a duplicate", async () => {
    const { onDataFlowChange } = renderRail();
    await userEvent.click(screen.getByRole("tab", { name: "Data" }));
    const input = screen.getByLabelText("Add produced file");
    await userEvent.type(input, "parts/{Enter}");
    expect(onDataFlowChange).toHaveBeenLastCalledWith("builder", { produces: ["parts/"], consumes: ["spec.md", "gone.md"] });
  });

  it("consumes is a checklist grouped by the step that writes each file; unmatched paths are flagged", async () => {
    const { onDataFlowChange } = renderRail();
    await userEvent.click(screen.getByRole("tab", { name: "Data" }));
    const specBoxes = screen.getAllByRole("checkbox", { name: "spec.md" });
    expect(specBoxes).toHaveLength(2); // written by both earlier steps
    specBoxes.forEach((b) => expect(b).toBeChecked());
    expect(screen.getByText("No earlier step writes these — the run will refuse to start")).toBeInTheDocument();
    expect(screen.getByText("gone.md")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "build/screens.json" }));
    expect(onDataFlowChange).toHaveBeenLastCalledWith("builder", {
      produces: [],
      consumes: ["spec.md", "gone.md", "build/screens.json"],
    });
  });
});

describe("CanvasConfigRail — custom prompt renders as markdown", () => {
  it("shows the prompt rendered; Edit swaps in the raw text", async () => {
    renderRail();
    const rendered = screen.getByTestId("agent-prompt-rendered");
    expect(rendered.querySelector("h1")?.textContent).toBe("Role");
    expect(rendered.querySelector("strong")?.textContent).toBe("Build");
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Custom agent prompt")).toHaveValue("# Role\n\n**Build** the screens.");
  });

  it("Expand opens a wide dialog with source and live preview; typing writes through", async () => {
    const { onPromptChange } = renderRail();
    await userEvent.click(screen.getByRole("button", { name: "Expand prompt" }));
    const dialog = screen.getByRole("dialog", { name: "Builder — prompt" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByTestId("prompt-dialog-preview").querySelector("h1")?.textContent).toBe("Role");
    await userEvent.type(screen.getByLabelText("Prompt source"), "!");
    expect(onPromptChange).toHaveBeenLastCalledWith("builder", "# Role\n\n**Build** the screens.!");
    await userEvent.click(screen.getAllByRole("button", { name: "Done" }).at(-1)!);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("CanvasConfigRail — header follows how the step runs", () => {
  it.each([
    [{}, undefined, "AI agent"],
    [{}, { strategy: "wave_scheduler" as const }, "Wave agent"],
    [{}, { strategy: "fanout_batch" as const }, "Fan-out agent"],
    [{ mechanical: "assemble_backlog" }, undefined, "Code step"],
  ])("%o + %o → %s", (over, selection, label) => {
    renderWithProviders(
      <CanvasConfigRail agent={{ ...BUILDER, ...over }} index={0} total={1} selection={selection} onSelection={vi.fn()} />,
    );
    expect(screen.getByText(new RegExp(`^${label} · step 1 of 1`))).toBeInTheDocument();
    expect(screen.getAllByLabelText(label).length).toBeGreaterThan(0);
  });
});

describe("CanvasConfigRail — code step reads / process / writes", () => {
  const code = (extra?: Record<string, unknown>) => ({ ...BUILDER, mechanical: "assemble_backlog", extra });

  it("reads / writes are the code's own declared files — the step's consumes/produces never change them", async () => {
    renderWithProviders(
      <CanvasConfigRail agent={code({ consumes: ["build/plan.json"], produces: ["other.csv"] })}
        index={0} total={1} selection={undefined} onSelection={vi.fn()} />,
    );
    const card = await screen.findByTestId("code-step-card");
    expect(card.textContent).toContain("stories/");
    expect(card.textContent).toContain("Checks every story and writes the backlog.");
    expect(card.textContent).toContain("backlog.md");
    expect(card.textContent).not.toContain("build/plan.json");
    expect(card.textContent).not.toContain("other.csv");
  });

  it("shows the declared files for a step with no consumes/produces", async () => {
    renderWithProviders(
      <CanvasConfigRail agent={code()} index={0} total={1} selection={undefined} onSelection={vi.fn()} />,
    );
    const card = await screen.findByTestId("code-step-card");
    expect(card.textContent).toContain("stories/");
    expect(card.textContent).toContain("backlog.md");
  });
});

it("Data tab: consumed run inputs (.uploads/, .context/) get their own group, not the amber warning", async () => {
  renderWithProviders(
    <CanvasConfigRail agent={{ ...BUILDER, extra: { consumes: [".context/prototype.html", "nowhere.md"] } }}
      index={0} total={1} selection={undefined} onSelection={vi.fn()} onDataFlowChange={vi.fn()} />,
  );
  await userEvent.click(screen.getByRole("tab", { name: "Data" }));
  expect(screen.getByText(/^Run inputs/)).toBeInTheDocument();
  expect(screen.getByText(".context/prototype.html")).toBeInTheDocument();
  const warn = screen.getByText("No earlier step writes these — the run will refuse to start").parentElement!;
  expect(warn.textContent).toContain("nowhere.md");
  expect(warn.textContent).not.toContain("prototype.html");
});

describe("CanvasConfigRail — code steps and the Data tab", () => {
  const CODE = mk({ id: "assemble", name: "Assemble", mechanical: "assemble_backlog" });

  it("an earlier code step offers its declared writes to a model step's Consumes", async () => {
    renderWithProviders(
      <CanvasConfigRail agent={{ ...BUILDER, extra: { consumes: ["backlog.md"] } }} index={1} total={2}
        selection={undefined} onSelection={vi.fn()} priorAgents={[CODE]} onDataFlowChange={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Data" }));
    expect(await screen.findByRole("checkbox", { name: "backlog.md" })).toBeChecked();
    expect(screen.queryByText(/run will refuse to start/)).toBeNull();
  });

  it("a code step's Data tab is read-only: its own files from the code, no editors", async () => {
    renderWithProviders(
      <CanvasConfigRail agent={CODE} index={0} total={1} selection={undefined} onSelection={vi.fn()} onDataFlowChange={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Data" }));
    const card = await screen.findByTestId("code-step-card");
    expect(card.textContent).toContain("stories/");
    expect(screen.queryByLabelText("Add produced file")).toBeNull();
  });
});
