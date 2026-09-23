/**
 * QA-PS-049 / ISS-802 — ArtifactVersionPicker.tsx:104-119's list-fetch effect
 * has no in-flight guard on getRunArtifacts: `cancelled` blocks only the
 * post-resolution setState, never the fetch itself, so React StrictMode's
 * dev-only mount->cleanup->mount double-invoke fires getRunArtifacts twice
 * per agent selection — confirmed 3/3 live on this exact call site (see
 * ISS-802's own Reproduction section).
 *
 * Mounting under <React.StrictMode> reproduces the real dev double-invoke in
 * jsdom (same technique as AuditTab.iss800.test.tsx / SandboxTab.iss830.test.tsx).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, screen, waitFor } from "@testing-library/react";
import React from "react";

const getRunArtifacts = vi.fn();

vi.mock("@/lib/api", () => ({
  getRunArtifacts: (...args: unknown[]) => getRunArtifacts(...args),
  getToken: () => "test-token",
}));

import { ArtifactVersionPicker } from "./ArtifactVersionPicker";

beforeEach(() => {
  getRunArtifacts.mockReset().mockResolvedValue({
    workflow_id: "r1",
    artifacts: [
      { id: "a1", kind: "spec", producer_step: "prototype-specify", producer_agent: "prototype-specify", task_id: null, content_hash: "h1", version: 1, visibility: "private", retention: "run_ttl", location: "artifact_refs/prototype-specify", parents: [], derived_from: null, children: [] },
    ],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ArtifactVersionPicker list-fetch effect under StrictMode (QA-PS-049 / ISS-802)", () => {
  it.fails("fires getRunArtifacts exactly once per agent selection, not twice", async () => {
    render(
      <React.StrictMode>
        <ArtifactVersionPicker runId="r1" agentId="prototype-specify" onSelect={() => {}} />
      </React.StrictMode>,
    );

    await waitFor(() => {
      expect(getRunArtifacts).toHaveBeenCalled();
    });

    // Without an in-flight guard, StrictMode's double-invoke fires this twice
    // — the bug's own headline symptom (24ms-apart, byte-identical pair).
    expect(getRunArtifacts).toHaveBeenCalledTimes(1);
  });
});
