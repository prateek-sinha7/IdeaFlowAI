/**
 * ISS-065 — the agent detail panel must let you read an older version of the
 * artifact this agent produced.
 *
 * `AgentDetailPanel` rendered `agent.output` unconditionally, and `useWorkflow.ts`
 * clears that field on every `agent_start` (FIX-039), so after an update_specs cycle
 * the only in-memory copy of spec v1 is gone. The durable rows survive; the screen
 * did not show them.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

const getRunArtifacts = vi.fn();

vi.mock("@/lib/api", () => ({
  getRunArtifacts: (...args: unknown[]) => getRunArtifacts(...args),
  getToken: () => "test-token",
}));

function specNode(over: Record<string, unknown>): Record<string, unknown> {
  return {
    id: "n",
    kind: "spec",
    producer_step: "prototype-specify",
    producer_agent: "prototype-specify",
    task_id: null,
    version: 1,
    visibility: "private",
    retention: "run_ttl",
    location: "artifact_refs/prototype-specify",
    parents: [],
    derived_from: null,
    children: [],
    ...over,
  };
}

const NODES = [
  specNode({ id: "a1", version: 1, content_hash: "h1", content: "SPEC VERSION ONE BODY" }),
  specNode({ id: "a1b", kind: "prototype-specify", version: 1, content_hash: "h1", content: "SPEC VERSION ONE BODY" }),
  specNode({ id: "a2", version: 2, content_hash: "h2", content: "SPEC VERSION TWO BODY" }),
  specNode({ id: "a2b", kind: "prototype-specify", version: 2, content_hash: "h2", content: "SPEC VERSION TWO BODY" }),
];

function doneAgent(overrides: Record<string, unknown> = {}) {
  return {
    id: "prototype-specify",
    name: "Spec Writer Agent",
    role: "Specification & Architecture",
    status: "done",
    output: "SPEC VERSION TWO BODY",
    thinkingText: "",
    thinking: "",
    contextSources: [],
    toolCalls: [],
    ...overrides,
  } as never;
}

beforeEach(() => {
  getRunArtifacts.mockReset();
  getRunArtifacts.mockImplementation((_t: string, _r: string, opts?: { includeContent?: boolean }) =>
    Promise.resolve({
      workflow_id: "r1",
      artifacts: opts?.includeContent ? NODES : NODES.map(({ content: _c, ...n }) => n),
    }),
  );
});

describe("AgentDetailPanel — per-artifact version viewing", () => {
  it("selecting v1 renders v1's content instead of agent.output", async () => {
    // FAIL-BEFORE: the panel renders `agent.output` unconditionally — RED.
    render(<AgentDetailPanel agent={doneAgent()} onBack={() => {}} runId="r1" />);

    const trigger = await screen.findByTestId("artifact-version-picker");
    fireEvent.click(trigger);
    fireEvent.click((await screen.findAllByRole("option"))[0]);

    await waitFor(() => expect(screen.getByText(/SPEC VERSION ONE BODY/)).toBeInTheDocument());
    expect(screen.queryByText(/SPEC VERSION TWO BODY/)).not.toBeInTheDocument();
  });

  it("shows the read-only banner while an older version is on screen, and Back to latest restores agent.output", async () => {
    // Reuses the existing ReadOnlyVersionBanner — no second banner (INV-12).
    render(<AgentDetailPanel agent={doneAgent()} onBack={() => {}} runId="r1" />);

    fireEvent.click(await screen.findByTestId("artifact-version-picker"));
    fireEvent.click((await screen.findAllByRole("option"))[0]);

    await waitFor(() => expect(screen.getByText(/Viewing v1 \(read-only\)/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Back to latest/i }));
    await waitFor(() => expect(screen.getByText(/SPEC VERSION TWO BODY/)).toBeInTheDocument());
    expect(screen.queryByText(/Viewing v1 \(read-only\)/i)).not.toBeInTheDocument();
  });

  it("renders no picker and behaves exactly as before without a runId", async () => {
    const { container } = render(<AgentDetailPanel agent={doneAgent()} onBack={() => {}} />);
    expect(container.querySelector('[data-testid="artifact-version-picker"]')).toBeNull();
    expect(getRunArtifacts).not.toHaveBeenCalled();
    expect(screen.getByText(/SPEC VERSION TWO BODY/)).toBeInTheDocument();
  });

  it("keeps an older version readable while the agent is re-running", async () => {
    // The whole point: during an update_specs cycle the agent goes back to "running"
    // and `agent.output` is reset to "" — the older version must still render.
    render(
      <AgentDetailPanel agent={doneAgent({ status: "running", output: "" })} onBack={() => {}} runId="r1" />,
    );

    fireEvent.click(await screen.findByTestId("artifact-version-picker"));
    fireEvent.click((await screen.findAllByRole("option"))[0]);

    await waitFor(() => expect(screen.getByText(/SPEC VERSION ONE BODY/)).toBeInTheDocument());
  });
});
