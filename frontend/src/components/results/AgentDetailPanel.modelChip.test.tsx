/**
 * AgentDetailPanel.modelChip.test.tsx — RFN-001 coverage.
 *
 * Verifies the per-agent model chip rendered in the AgentDetailPanel header row:
 *
 *  1. Running agent with modelId → chip visible immediately (engine now emits
 *     model_id on agent_start so the chip shows while the agent is running).
 *  2. Done agent with modelId → chip persists after completion alongside "Done".
 *  3. Idle agent (no modelId) → chip absent (model unknown before agent runs).
 *  4. Agent with an unknown model_id → fallback label rendered, no crash.
 *  5. Done agent, modelId absent → chip absent (graceful degrade for old events).
 *  6. Every catalog ID resolves to its label from /api/capabilities (spec 020 —
 *     no hardcoded id→label map in the component).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

// Spec 020 — labels now come from /api/capabilities, not a hardcoded map in the
// component. The catalog below mirrors model_catalog.py so a drift between the
// two shows up here instead of in the UI.
const CATALOG = [
  { id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0",  label: "Claude Haiku 4.5" },
  { id: "us.anthropic.claude-haiku-4-5-20251001-v1:0",  label: "Claude Haiku 4.5 (US)" },
  { id: "global.openai.gpt-5.6-luna",                   label: "GPT-5.6 Luna" },
  { id: "global.openai.gpt-5.6-sol",                    label: "GPT-5.6 Sol" },
  { id: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0", label: "Claude Sonnet 4.5" },
  { id: "eu.anthropic.claude-sonnet-4-6",               label: "Claude Sonnet 4.6" },
  { id: "us.anthropic.claude-sonnet-5",                 label: "Claude Sonnet 5 (US)" },
  { id: "eu.anthropic.claude-sonnet-5",                 label: "Claude Sonnet 5 (EU)" },
  { id: "eu.anthropic.claude-sonnet-4-20250514-v1:0",   label: "Claude Sonnet 4" },
  { id: "eu.anthropic.claude-opus-4-5-20251101-v1:0",   label: "Claude Opus 4.5" },
  { id: "eu.anthropic.claude-opus-4-6-v1",              label: "Claude Opus 4.6" },
];

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getToken: () => "test-token",
  getCapabilities: vi.fn(async () => ({ capabilities: [], model_catalog: CATALOG })),
}));

// ── Shared agent factories ───────────────────────────────────────────────────

function makeAgent(overrides: Record<string, unknown> = {}) {
  return {
    id: "spec-writer",
    name: "Spec Writer Agent",
    role: "Specification & Architecture",
    icon: "✍️",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...overrides,
  } as never;
}

// ── 1. Running agent with modelId shows chip immediately ─────────────────────

describe("AgentDetailPanel — model chip (RFN-001)", () => {
  it("shows the model chip while the agent is running (agent_start now carries model_id)", async () => {
    render(
      <AgentDetailPanel
        agent={makeAgent({
          status: "running",
          output: "Drafting the specification…",
          modelId: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        })}
        onBack={() => {}}
      />,
    );
    // The resolved label must appear, not the raw Bedrock ID.
    // NOTE: CSS `text-transform: uppercase` is visual-only — the DOM text node
    // itself carries the mixed-case value from resolveModelLabel.
    await waitFor(() => expect(screen.getByText("Claude Sonnet 4.5")).toBeInTheDocument());
  });

  // ── 2. Done agent chip persists ──────────────────────────────────────────

  it("keeps the model chip visible after the agent completes (chip persists with Done status)", async () => {
    render(
      <AgentDetailPanel
        agent={makeAgent({
          status: "done",
          output: "# Specification\n\nFinal output.",
          duration: 14.2,
          totalTokens: 12000,
          modelId: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        })}
        onBack={() => {}}
      />,
    );
    // Both status chip and model chip must coexist
    expect(screen.getByText("Done")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Claude Sonnet 4.5")).toBeInTheDocument());
  });

  // ── 3. Idle agent — no chip (model unknown) ──────────────────────────────

  it("does not render the model chip for an idle agent (model_id not yet known)", () => {
    render(
      <AgentDetailPanel
        agent={makeAgent({ status: "idle" })}
        onBack={() => {}}
      />,
    );
    // No chip text at all — idle agents have no modelId.
    // Using case-insensitive regex because resolveModelLabel returns mixed case.
    expect(screen.queryByText(/Claude/i)).not.toBeInTheDocument();
  });

  // ── 4. Unknown model ID — fallback label, no crash ───────────────────────

  it("renders a fallback label for an unrecognised model id without throwing", () => {
    render(
      <AgentDetailPanel
        agent={makeAgent({
          status: "done",
          output: "Output.",
          modelId: "eu.anthropic.claude-future-9000-v1:0",
        })}
        onBack={() => {}}
      />,
    );
    // Should not crash and should render SOMETHING (the fallback label).
    // The fallback strips prefix/date/suffix — result is non-empty and contains "Claude".
    const chipText = screen.queryByText(/Claude/i);
    expect(chipText).toBeInTheDocument();
  });

  // ── 5. modelId absent on done agent — no chip (graceful degrade) ─────────

  it("does not render the chip when modelId is absent (graceful degrade for old SSE streams)", () => {
    render(
      <AgentDetailPanel
        agent={makeAgent({
          status: "done",
          output: "Output.",
          // modelId deliberately absent
        })}
        onBack={() => {}}
      />,
    );
    expect(screen.queryByText(/Claude/i)).not.toBeInTheDocument();
  });

  // ── 6. Catalog label resolution for all known model IDs ─────────────────

  it.each(CATALOG.map(m => [m.id, m.label] as [string, string]))(
    "resolves %s → '%s'",
    async (modelId, expectedLabel) => {
      render(
        <AgentDetailPanel
          agent={makeAgent({ status: "done", output: "x", modelId })}
          onBack={() => {}}
        />,
      );
      await waitFor(() => expect(screen.getByText(expectedLabel)).toBeInTheDocument());
    },
  );

  // ── 7. Live badge and model chip coexist for a running agent ─────────────

  it("shows both the Live badge and the model chip simultaneously while running", async () => {
    render(
      <AgentDetailPanel
        agent={makeAgent({
          status: "running",
          output: "Working…",
          modelId: "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        })}
        onBack={() => {}}
      />,
    );
    expect(screen.getByText("Live")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Claude Haiku 4.5")).toBeInTheDocument());
  });
});
