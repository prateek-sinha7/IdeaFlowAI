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
 *  6. Known Bedrock IDs resolve to their human-readable catalog labels.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

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
  it("shows the model chip while the agent is running (agent_start now carries model_id)", () => {
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
    expect(screen.getByText("Claude Sonnet 4.5")).toBeInTheDocument();
  });

  // ── 2. Done agent chip persists ──────────────────────────────────────────

  it("keeps the model chip visible after the agent completes (chip persists with Done status)", () => {
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
    expect(screen.getByText("Claude Sonnet 4.5")).toBeInTheDocument();
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

  it.each([
    ["eu.anthropic.claude-haiku-4-5-20251001-v1:0",    "Claude Haiku 4.5"],
    ["us.anthropic.claude-3-5-haiku-20241022-v1:0",    "Claude Haiku 3.5"],
    ["eu.anthropic.claude-sonnet-4-5-20250929-v1:0",   "Claude Sonnet 4.5"],
    ["eu.anthropic.claude-sonnet-4-6",                 "Claude Sonnet 4.6"],
    ["us.anthropic.claude-sonnet-5",                   "Claude Sonnet 5"],
    ["eu.anthropic.claude-sonnet-5",                   "Claude Sonnet 5"],
    ["eu.anthropic.claude-sonnet-4-20250514-v1:0",     "Claude Sonnet 4"],
    ["eu.anthropic.claude-opus-4-5-20251101-v1:0",     "Claude Opus 4.5"],
    ["eu.anthropic.claude-opus-4-6-v1",               "Claude Opus 4.6"],
  ] as [string, string][])(
    "resolves %s → '%s'",
    (modelId, expectedLabel) => {
      render(
        <AgentDetailPanel
          agent={makeAgent({ status: "done", output: "x", modelId })}
          onBack={() => {}}
        />,
      );
      expect(screen.getByText(expectedLabel)).toBeInTheDocument();
    },
  );

  // ── 7. Live badge and model chip coexist for a running agent ─────────────

  it("shows both the Live badge and the model chip simultaneously while running", () => {
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
    expect(screen.getByText("Claude Haiku 4.5")).toBeInTheDocument();
  });
});
