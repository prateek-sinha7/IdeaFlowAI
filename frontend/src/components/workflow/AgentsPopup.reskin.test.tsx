/**
 * Phase 37-03 — Composer (AgentsPopup) RESKIN contract test.
 *
 * This is a LOOK change only: the capability palette + AdvancedExpander +
 * HooksTab + AgentLibrary are reskinned onto the Phase-32 `@theme` token
 * layer. The dominant risk is regression-by-face-value-rebuild, so this file
 * PINS the shipped P22 reuse contracts the mock would drop:
 *
 *   1. Retired-palette source gate → 0 (the reskin's RED-first assertion).
 *   2. EMP-04: selecting a validator auto-attaches the COUPLED `validation`
 *      gate (the mock drops the coupling; selections.py enforces it server-side).
 *   3. WIRE-02: the retry lever offers INTS [1,2,3] (the mock models retry as a
 *      bool → the compiler would materialize the wrong type).
 *   4. SC-001: `user_allowed=false` capabilities render locked ("Engineer-only")
 *      from the LIVE registry payload — never a hardcoded per-workflow list.
 *   5. ND-12: no workflow visibility / team-sharing control is built.
 *   6. INV-3: the standalone AgentModelPicker is NOT mounted/imported (the inline
 *      Model lever already satisfies per-agent model selection).
 *   7. Save wires to the owner-scoped `createUserWorkflow` via NameWorkflowModal.
 *
 * `getCapabilities` is mocked so the palette/expander render without a real
 * `/api/capabilities` fetch (same pattern as AdvancedExpander.test.tsx).
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { CapabilitiesPalette } from "@/lib/api";

const mockGetCapabilities = vi.fn();
const mockCreateUserWorkflow = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (token: string) => mockGetCapabilities(token),
  createUserWorkflow: (...args: unknown[]) => mockCreateUserWorkflow(...args),
}));

import {
  AdvancedExpander,
  CapabilityPaletteSection,
  AgentsPopup,
} from "./AgentsPopup";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { AgentDef } from "@/types/index";

// ── The exact Phase-35 token gate (per-file retired palette must be 0) ──────────
const RETIRED_PALETTE = /#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains/g;

const WORKFLOW_DIR = resolve(process.cwd(), "src/components/workflow");
const AGENTS_POPUP_SRC = readFileSync(
  resolve(WORKFLOW_DIR, "AgentsPopup.tsx"),
  "utf8",
);
const AGENT_LIBRARY_SRC = readFileSync(
  resolve(WORKFLOW_DIR, "AgentLibrary.tsx"),
  "utf8",
);

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    {
      kind: "validator",
      name: "code_test",
      user_allowed: true,
      description: "Runs the generated tests.",
      security_gated: false,
      config_schema: {},
    },
    {
      kind: "gate",
      name: "approval",
      user_allowed: true,
      description: "Human approval gate.",
      security_gated: false,
      config_schema: {},
    },
    {
      kind: "gate",
      name: "security",
      user_allowed: false, // Engineer-only — renders LOCKED, never hidden.
      description: "Security review gate.",
      security_gated: true,
      config_schema: {},
    },
  ],
  model_catalog: [
    {
      id: "model-premium",
      label: "Premium Model",
      description: "",
      tier: "enterprise",
      cost_class: "premium",
      provider: "anthropic",
      context_window: 200000,
      user_allowed: true,
    },
  ],
};

const AGENTS = [{ id: "agent-a", name: "Agent A" }];

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

// ── 1. Token gate (RED-first) ───────────────────────────────────────────────────
describe("AgentsPopup reskin — token gate", () => {
  it("AgentsPopup.tsx carries 0 retired-palette hits", () => {
    const hits = AGENTS_POPUP_SRC.match(RETIRED_PALETTE) ?? [];
    expect(hits).toEqual([]);
  });

  it("AgentsPopup.tsx uses the Phase-32 @theme brand token positively", () => {
    // The reskin migrates the retired navy to the `brand` token utilities.
    expect(AGENTS_POPUP_SRC).toMatch(/text-brand\b/);
  });
});

// ── 2 + 3. AdvancedExpander preserved contracts (COUPLED_GATE + retry-int) ───────
describe("AgentsPopup reskin — AdvancedExpander preserved contracts", () => {
  it("EMP-04: selecting a validator auto-attaches the coupled `validation` gate", async () => {
    const onSelectionsChange = vi.fn();
    renderWithProviders(
      <AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /advanced/i }),
    );
    await userEvent.selectOptions(
      screen.getByLabelText(/validator/i),
      "code_test",
    );

    // Inline notice announces the coupling (polite live region).
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/added required validation gate/i);

    // The reported selections carry the auto-attached gate.
    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["agent-a"].gates).toContain("validation");
  });

  it("WIRE-02: the retry lever offers ints [1,2,3] (not a bool toggle)", async () => {
    const onSelectionsChange = vi.fn();
    renderWithProviders(
      <AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /advanced/i }),
    );

    const retry = screen.getByLabelText(/retry/i) as HTMLSelectElement;
    const optionValues = Array.from(retry.options)
      .map((o) => o.value)
      .filter((v) => v !== "");
    expect(optionValues).toEqual(["1", "2", "3"]);

    // Picking one reports the INT (not a boolean).
    await userEvent.selectOptions(retry, "2");
    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["agent-a"].retry).toBe(2);
    expect(typeof last["agent-a"].retry).toBe("number");
  });
});

// ── 4. CapabilityPaletteSection reads the LIVE registry (user_allowed lock) ──────
describe("AgentsPopup reskin — CapabilityPaletteSection live registry", () => {
  it("SC-001: a user_allowed=false capability renders locked (Engineer-only)", async () => {
    renderWithProviders(<CapabilityPaletteSection />);
    // Whole payload rendered from the mocked live registry.
    await screen.findByText("code_test");
    // The locked cap is present AND flagged Engineer-only (never hidden).
    const lockedRow = screen
      .getByText("security")
      .closest("[data-cap-row]") as HTMLElement;
    expect(within(lockedRow).getByText(/engineer-only/i)).toBeInTheDocument();
    expect(lockedRow).toHaveAttribute("aria-disabled", "true");
  });

  it("does not introduce a hardcoded capability list (no CAPDEF)", () => {
    expect(AGENTS_POPUP_SRC).not.toMatch(/CAPDEF/i);
  });
});

// ── 5. AgentLibrary token gate (RED-first for Task 2) ───────────────────────────
describe("AgentsPopup reskin — AgentLibrary token gate", () => {
  it("AgentLibrary.tsx carries 0 retired-palette hits", () => {
    const hits = AGENT_LIBRARY_SRC.match(RETIRED_PALETTE) ?? [];
    expect(hits).toEqual([]);
  });
});

// ── 6. ND-12 + INV-3 source invariants ──────────────────────────────────────────
describe("AgentsPopup reskin — deferred-out + no dual-impl", () => {
  it("ND-12: no workflow visibility / team-sharing control is built", () => {
    expect(AGENTS_POPUP_SRC).not.toMatch(/visibility|just me|team-shar|shared with/i);
  });

  it("INV-3: the standalone AgentModelPicker is neither imported nor mounted", () => {
    // The corrected gate: no JSX mount and no import of the superseded component.
    // (Explanatory comments referencing the pattern are allowed.)
    expect(AGENTS_POPUP_SRC).not.toMatch(/<AgentModelPicker|import.*AgentModelPicker/);
  });

  it("Save is wired to the owner-scoped createUserWorkflow", () => {
    expect(AGENTS_POPUP_SRC).toMatch(/createUserWorkflow/);
  });
});

// ── 7. Save → createUserWorkflow via NameWorkflowModal (behavioral) ─────────────
describe("AgentsPopup reskin — Save wires to createUserWorkflow", () => {
  const SAVE_AGENTS: AgentDef[] = [
    {
      id: "requirements-analyst",
      name: "Requirements Analyst",
      description: "Analyzes requirements.",
      role: "analyst",
      pipeline_type: "prototype",
    } as AgentDef,
  ];

  it("opens NameWorkflowModal and calls createUserWorkflow with the composed payload", async () => {
    mockCreateUserWorkflow.mockResolvedValue({
      id: "wf-1",
      name: "My workflow",
      base_pipeline_type: "prototype",
      agent_ids: ["requirements-analyst"],
    });

    renderWithProviders(
      <SkillsHooksProvider>
        <AgentsPopup
          isOpen
          onClose={vi.fn()}
          agents={SAVE_AGENTS}
          pipelineType="prototype"
        />
      </SkillsHooksProvider>,
    );

    // Open the Save modal from the footer.
    await userEvent.click(
      screen.getByRole("button", { name: /save workflow/i }),
    );

    // Name it, then confirm.
    const nameInput = await screen.findByPlaceholderText(/competitive research/i);
    await userEvent.type(nameInput, "My workflow");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(mockCreateUserWorkflow).toHaveBeenCalledTimes(1));
    const [, body] = mockCreateUserWorkflow.mock.calls[0];
    expect(body).toMatchObject({
      name: "My workflow",
      base_pipeline_type: "prototype",
      agent_ids: ["requirements-analyst"],
    });
  });

  it("WR-03: does NOT persist a stale model_overrides seed (model lives in selections)", async () => {
    mockCreateUserWorkflow.mockResolvedValue({
      id: "wf-2",
      name: "No stale overrides",
      base_pipeline_type: "prototype",
      agent_ids: ["requirements-analyst"],
    });

    renderWithProviders(
      <SkillsHooksProvider>
        <AgentsPopup
          isOpen
          onClose={vi.fn()}
          agents={SAVE_AGENTS}
          pipelineType="prototype"
          // A stale seed the OLD Save composer emitted verbatim → divergent model
          // on reload. Per WR-03 the seed is dead: per-agent model is the inline
          // Model lever's `selections[id].model` (the single source of truth).
          initialModelOverrides={{ "requirements-analyst": "stale-model" }}
        />
      </SkillsHooksProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: /save workflow/i }));
    const nameInput = await screen.findByPlaceholderText(/competitive research/i);
    await userEvent.type(nameInput, "No stale overrides");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(mockCreateUserWorkflow).toHaveBeenCalledTimes(1));
    const [, body] = mockCreateUserWorkflow.mock.calls[0];
    expect(body).not.toHaveProperty("model_overrides");
  });

  it("51-06: threads a composed FAN-OUT selection into the createUserWorkflow SAVE payload", async () => {
    mockCreateUserWorkflow.mockResolvedValue({
      id: "wf-3",
      name: "Fanned workflow",
      base_pipeline_type: "prototype",
      agent_ids: ["requirements-analyst"],
    });

    // A composed fan-out selection (the exact shape the AdvancedExpander toggle
    // persists) seeds the live selections; Save must forward it verbatim under
    // `selections` so the backend `trust="user"` re-compile honors it.
    const FANOUT_SELECTION = {
      "requirements-analyst": {
        strategy: "fanout_batch" as const,
        task_source: {
          kind: "parsed" as const,
          parser: "heading_tasks" as const,
          source_step: "prototype-plan",
        },
      },
    };

    renderWithProviders(
      <SkillsHooksProvider>
        <AgentsPopup
          isOpen
          onClose={vi.fn()}
          agents={SAVE_AGENTS}
          pipelineType="prototype"
          initialSelections={FANOUT_SELECTION}
        />
      </SkillsHooksProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: /save workflow/i }));
    const nameInput = await screen.findByPlaceholderText(/competitive research/i);
    await userEvent.type(nameInput, "Fanned workflow");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(mockCreateUserWorkflow).toHaveBeenCalledTimes(1));
    const [, body] = mockCreateUserWorkflow.mock.calls[0];
    expect(body.selections).toEqual(FANOUT_SELECTION);
  });

  it("51-06: omits selections from the SAVE payload when no lever is set (INV-3)", async () => {
    mockCreateUserWorkflow.mockResolvedValue({
      id: "wf-4",
      name: "Bare workflow",
      base_pipeline_type: "prototype",
      agent_ids: ["requirements-analyst"],
    });

    renderWithProviders(
      <SkillsHooksProvider>
        <AgentsPopup
          isOpen
          onClose={vi.fn()}
          agents={SAVE_AGENTS}
          pipelineType="prototype"
        />
      </SkillsHooksProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: /save workflow/i }));
    const nameInput = await screen.findByPlaceholderText(/competitive research/i);
    await userEvent.type(nameInput, "Bare workflow");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(mockCreateUserWorkflow).toHaveBeenCalledTimes(1));
    const [, body] = mockCreateUserWorkflow.mock.calls[0];
    expect(body).not.toHaveProperty("selections");
  });
});
