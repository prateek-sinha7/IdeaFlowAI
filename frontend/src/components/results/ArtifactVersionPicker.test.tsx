/**
 * ISS-065 — per-artifact versions must be visible and inspectable inside a run.
 *
 * `artifact_refs` durably versions every artifact per run and the REST route already
 * returns each version (with its body under `?include=content`), but nothing on the
 * run screen showed it: `useWorkflow.ts` resets an agent's `output` to "" on every
 * `agent_start`, so when the spec agent re-runs during an update_specs cycle, v1's
 * text is gone from memory and the panel silently shows v3 with no way back.
 *
 * Two traps these tests pin down:
 *   - Each artifact is written TWICE — once under the typed kind ("spec") and once
 *     under a `produces` alias equal to the agent id ("prototype-specify"). Those
 *     series do NOT stay in lockstep for the build agent (html_file reaches v23 while
 *     prototype-build reaches v11), so dedupe must key on `content_hash`, not version.
 *   - The mocked Playwright fixture returns `json({})` for any unmatched `/api/**`
 *     (mockApi.ts:708), so `resp.artifacts` is `undefined` there.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ArtifactVersionPicker } from "./ArtifactVersionPicker";

const getRunArtifacts = vi.fn();

vi.mock("@/lib/api", () => ({
  getRunArtifacts: (...args: unknown[]) => getRunArtifacts(...args),
  getToken: () => "test-token",
}));

/** A node in the shape `_node()` returns (runs.py:907-925) — no created_at. */
function node(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: "id-1",
    kind: "spec",
    producer_step: "prototype-specify",
    producer_agent: "prototype-specify",
    task_id: null,
    content_hash: "hash-1",
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

/** The real d5dbc9f2 shape: spec v1-3 plus the prototype-specify alias rows. */
const SPEC_NODES = [
  node({ id: "a1", kind: "spec", version: 1, content_hash: "h1" }),
  node({ id: "a1b", kind: "prototype-specify", version: 1, content_hash: "h1" }),
  node({ id: "a2", kind: "spec", version: 2, content_hash: "h2" }),
  node({ id: "a2b", kind: "prototype-specify", version: 2, content_hash: "h2" }),
  node({ id: "a3", kind: "spec", version: 3, content_hash: "h3" }),
  node({ id: "a3b", kind: "prototype-specify", version: 3, content_hash: "h3" }),
];

beforeEach(() => {
  getRunArtifacts.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("ArtifactVersionPicker", () => {
  it("renders nothing for a single-version agent (zero blast radius)", async () => {
    getRunArtifacts.mockResolvedValue({
      workflow_id: "r1",
      artifacts: [node({ id: "a1", content_hash: "h1" }), node({ id: "a1b", kind: "prototype-specify", content_hash: "h1" })],
    });
    const { container } = render(
      <ArtifactVersionPicker runId="r1" agentId="prototype-specify" onSelect={() => {}} />,
    );
    await waitFor(() => expect(getRunArtifacts).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("groups by producer_agent and dedupes by content_hash", async () => {
    getRunArtifacts.mockResolvedValue({
      workflow_id: "r1",
      artifacts: [
        ...SPEC_NODES,
        // another agent's artifacts must not leak into this picker
        node({ id: "b1", kind: "task_list", producer_agent: "prototype-plan", content_hash: "p1" }),
        node({ id: "b2", kind: "task_list", producer_agent: "prototype-plan", version: 2, content_hash: "p2" }),
      ],
    });
    render(<ArtifactVersionPicker runId="r1" agentId="prototype-specify" onSelect={() => {}} />);

    const trigger = await screen.findByTestId("artifact-version-picker");
    // 6 nodes → 3 distinct hashes, labelled with the typed kind, not the alias.
    expect(trigger).toHaveTextContent("spec");
    expect(trigger).toHaveTextContent("v3 of 3");

    fireEvent.click(trigger);
    expect(await screen.findAllByRole("option")).toHaveLength(3);
  });

  it("handles the build-agent subset shape (html_file v23 vs prototype-build v11)", async () => {
    // The build task-loop writes an html_file per task iteration, so the alias series
    // is a strict SUBSET of the typed series. Deduping by (kind, version) would produce
    // the wrong count here; deduping by content_hash yields one entry per real output.
    getRunArtifacts.mockResolvedValue({
      workflow_id: "r1",
      artifacts: [
        node({ id: "h1", kind: "html_file", producer_agent: "prototype-build", version: 1, content_hash: "x1" }),
        node({ id: "h2", kind: "html_file", producer_agent: "prototype-build", version: 2, content_hash: "x2" }),
        node({ id: "h3", kind: "html_file", producer_agent: "prototype-build", version: 3, content_hash: "x3" }),
        // the alias rows carry their own, lower version numbers for the same bytes
        node({ id: "p1", kind: "prototype-build", producer_agent: "prototype-build", version: 1, content_hash: "x1" }),
        node({ id: "p2", kind: "prototype-build", producer_agent: "prototype-build", version: 2, content_hash: "x3" }),
      ],
    });
    render(<ArtifactVersionPicker runId="r1" agentId="prototype-build" onSelect={() => {}} />);

    const trigger = await screen.findByTestId("artifact-version-picker");
    expect(trigger).toHaveTextContent("html_file");
    expect(trigger).toHaveTextContent("v3 of 3");
  });

  it("does not request content until a version is chosen, then memoises it", async () => {
    // `?kind=html_file&include=content` was measured at 2.89 MB — never on mount.
    getRunArtifacts.mockImplementation((_t: string, _r: string, opts?: { includeContent?: boolean }) =>
      Promise.resolve({
        workflow_id: "r1",
        artifacts: opts?.includeContent
          ? SPEC_NODES.map((n) => ({ ...n, content: `body of ${n.content_hash}` }))
          : SPEC_NODES,
      }),
    );
    const onSelect = vi.fn();
    render(<ArtifactVersionPicker runId="r1" agentId="prototype-specify" onSelect={onSelect} />);

    const trigger = await screen.findByTestId("artifact-version-picker");
    expect(getRunArtifacts).toHaveBeenCalledTimes(1);
    expect(getRunArtifacts.mock.calls[0][2]?.includeContent).toBeFalsy();

    fireEvent.click(trigger);
    fireEvent.click((await screen.findAllByRole("option"))[0]);
    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledWith({ index: 1, content: "body of h1" }),
    );
    expect(getRunArtifacts).toHaveBeenCalledTimes(2);
    expect(getRunArtifacts.mock.calls[1][2]).toMatchObject({ kind: "spec", includeContent: true });

    // Re-selecting must reuse the memoised bodies rather than re-fetch 2.89 MB.
    fireEvent.click(screen.getByTestId("artifact-version-picker"));
    fireEvent.click((await screen.findAllByRole("option"))[1]);
    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledWith({ index: 2, content: "body of h2" }),
    );
    expect(getRunArtifacts).toHaveBeenCalledTimes(2);
  });

  it("selecting the newest version returns to live output", async () => {
    getRunArtifacts.mockResolvedValue({ workflow_id: "r1", artifacts: SPEC_NODES });
    const onSelect = vi.fn();
    render(<ArtifactVersionPicker runId="r1" agentId="prototype-specify" selectedIndex={1} onSelect={onSelect} />);

    fireEvent.click(await screen.findByTestId("artifact-version-picker"));
    fireEvent.click((await screen.findAllByRole("option"))[2]);
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(null));
  });

  it("renders nothing when the API returns {} (the mocked-e2e fallback)", async () => {
    // mockApi.ts:708 answers every unmatched /api/** with json({}) — without the
    // `resp.artifacts ?? []` guard this throws a TypeError and reds the whole suite.
    getRunArtifacts.mockResolvedValue({});
    const { container } = render(
      <ArtifactVersionPicker runId="r1" agentId="prototype-specify" onSelect={() => {}} />,
    );
    await waitFor(() => expect(getRunArtifacts).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the fetch rejects, and never throws into the panel", async () => {
    getRunArtifacts.mockRejectedValue(new Error("boom"));
    const { container } = render(
      <ArtifactVersionPicker runId="r1" agentId="prototype-specify" onSelect={() => {}} />,
    );
    await waitFor(() => expect(getRunArtifacts).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing and does not fetch without a run id", () => {
    const { container } = render(
      <ArtifactVersionPicker runId={null} agentId="prototype-specify" onSelect={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(getRunArtifacts).not.toHaveBeenCalled();
  });
});
