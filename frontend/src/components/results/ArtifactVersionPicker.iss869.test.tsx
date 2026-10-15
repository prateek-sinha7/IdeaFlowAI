/**
 * ISS-869 — the picker must walk nested `children` (derived_from versions from gate
 * Redo/Edit nest under their parent on the wire). Fails today: top-level only, so
 * the picker sees 1 version and renders nothing.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ArtifactVersionPicker } from "./ArtifactVersionPicker";

const getRunArtifacts = vi.fn();
vi.mock("@/lib/api", () => ({
  getRunArtifacts: (...args: unknown[]) => getRunArtifacts(...args),
  getToken: () => "test-token",
}));

function node(over: Record<string, unknown> = {}) {
  return {
    id: "id-1", kind: "spec", producer_step: "agent-x", producer_agent: "agent-x",
    task_id: null, content_hash: "h1", version: 1, visibility: "private",
    retention: "run_ttl", location: "artifact_refs/agent-x", parents: [],
    derived_from: null, children: [], ...over,
  };
}

beforeEach(() => getRunArtifacts.mockReset());

describe("ISS-869 nested artifact tree", () => {
  it("counts a derived version nested under children (v2 of 2)", async () => {
    getRunArtifacts.mockResolvedValue({
      workflow_id: "r1",
      artifacts: [
        node({
          id: "a1", content_hash: "h1",
          children: [node({ id: "a2", version: 2, content_hash: "h2", derived_from: "a1" })],
        }),
      ],
    });
    render(<ArtifactVersionPicker runId="r1" agentId="agent-x" onSelect={() => {}} />);
    const trigger = await screen.findByTestId("artifact-version-picker", {}, { timeout: 1000 });
    expect(trigger).toHaveTextContent("v2 of 2");
  });
});
