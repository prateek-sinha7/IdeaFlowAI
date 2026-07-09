/**
 * Phase 37-06 Task 2 — Workflow dialog (declared capabilities/context/compaction).
 *
 * The dialog surfaces the COMPILED workflow's DECLARED data from
 * `getWorkflowDetail` (+ the `/api/capabilities` registry for capability
 * metadata). The load-bearing invariant (SC-001 / INV-5): the "Engineer-only"
 * lock is a REFLECTION of the declared `user_allowed` flag — never a
 * workflow-name / pipelineType code branch, and never mock "8 agents / Single-shot"
 * fiction.
 *
 * This file pins:
 *   1. declared context_providers render from the mocked WorkflowDetail
 *   2. declared capabilities (gates + validators) render from the compiled steps
 *   3. a `user_allowed=false` capability renders locked (Engineer-only)
 *   4. a `user_allowed=true` capability does NOT render locked
 *   5. declared compaction surfaces
 *   6. source invariants: `user_allowed` gating present; no name-branch / fiction
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { CapabilitiesPalette, WorkflowDetail } from "@/lib/api";

const mockGetWorkflowDetail = vi.fn();
const mockGetCapabilities = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflowDetail: (...a: unknown[]) => mockGetWorkflowDetail(...a),
  getCapabilities: (...a: unknown[]) => mockGetCapabilities(...a),
}));

import { WorkflowDialog } from "./WorkflowDialog";

const WORKFLOW_SRC = readFileSync(
  resolve(process.cwd(), "src/components/workflow/WorkflowDialog.tsx"),
  "utf8",
);

const DETAIL: WorkflowDetail = {
  id: "prototype",
  name: "Prototype",
  description: "Build an interactive HTML prototype.",
  planner: "prototype-planner",
  clarify_mode: "auto",
  clarify_defaults: [],
  context_providers: ["template", "design_system"],
  deliverable: { strategy: "html", name: "Prototype" },
  steps: [
    {
      agent_id: "spec",
      name: "Specify",
      role: "analyst",
      order: 1,
      strategy: "single",
      gates: ["approval"],
      validators: ["code_test"],
      compaction: "summarize_history",
    },
    {
      agent_id: "build",
      name: "Build",
      role: "builder",
      order: 2,
      strategy: "loop",
      gates: ["security"],
      validators: [],
      compaction: null,
    },
  ],
};

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
  model_catalog: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetWorkflowDetail.mockResolvedValue(DETAIL);
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

function renderDialog() {
  return render(<WorkflowDialog workflowId="prototype" onClose={vi.fn()} />);
}

describe("WorkflowDialog — declared data surfacing", () => {
  it("renders the declared context_providers from WorkflowDetail", async () => {
    renderDialog();
    expect(await screen.findByText("template")).toBeInTheDocument();
    expect(screen.getByText("design_system")).toBeInTheDocument();
  });

  it("renders the declared capabilities (gates + validators) from the compiled steps", async () => {
    renderDialog();
    expect(await screen.findByText("code_test")).toBeInTheDocument();
    expect(screen.getByText("approval")).toBeInTheDocument();
    expect(screen.getByText("security")).toBeInTheDocument();
  });

  it("surfaces the declared compaction strategy", async () => {
    renderDialog();
    expect(await screen.findByText(/summarize_history/i)).toBeInTheDocument();
  });
});

describe("WorkflowDialog — user_allowed gating (SC-001/INV-5)", () => {
  it("renders a user_allowed=false capability as Engineer-only (locked)", async () => {
    renderDialog();
    const lockedRow = (await screen.findByText("security")).closest(
      "[data-cap-row]",
    ) as HTMLElement;
    expect(within(lockedRow).getByText(/engineer-only/i)).toBeInTheDocument();
    expect(lockedRow).toHaveAttribute("aria-disabled", "true");
  });

  it("does NOT lock a user_allowed=true capability", async () => {
    renderDialog();
    const openRow = (await screen.findByText("approval")).closest(
      "[data-cap-row]",
    ) as HTMLElement;
    expect(within(openRow).queryByText(/engineer-only/i)).toBeNull();
    expect(openRow).not.toHaveAttribute("aria-disabled", "true");
  });
});

describe("WorkflowDialog — source invariants (no name-branch, no fiction)", () => {
  it("gates on the declared user_allowed flag, never a workflow-name branch", () => {
    expect(WORKFLOW_SRC).toMatch(/user_allowed/);
    expect(WORKFLOW_SRC).not.toMatch(/od_prototype|od_ppt|pipelineType ===/);
  });

  it("surfaces declared context_providers, not hardcoded agent-count fiction", () => {
    expect(WORKFLOW_SRC).toMatch(/context_providers/);
    expect(WORKFLOW_SRC).not.toMatch(/8 agents|Single-shot/i);
  });

  it("carries 0 retired-palette hits (Phase-35 token gate)", () => {
    const hits =
      WORKFLOW_SRC.match(/#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains/g) ??
      [];
    expect(hits).toEqual([]);
  });
});
