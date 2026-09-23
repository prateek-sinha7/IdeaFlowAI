/**
 * QA-PS-049 / ISS-802 — the list-fetch effect must request
 * GET /api/runs/{id}/artifacts ONCE under React StrictMode, not once per mount.
 *
 * Counted at `fetch`, not on a `vi.mock("@/lib/api")` spy: the component loads
 * the api module with a dynamic `import()`, and under vitest the second,
 * concurrent import of a factory-mocked module resolved to the REAL module, so
 * a spy saw 1 call while 2 requests went out (ArtifactVersionPicker.iss802.test.tsx
 * reads 1 with or without the fix). Observed red before the fix: 2 requests.
 */
import { afterEach, expect, it, vi } from "vitest";
import { render, cleanup } from "@testing-library/react";
import React from "react";
import { ArtifactVersionPicker } from "./ArtifactVersionPicker";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

it("requests the run's artifact list once per agent selection under StrictMode", async () => {
  localStorage.setItem("auth_token", "iss802-token");
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify({ workflow_id: "r1", artifacts: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);

  render(
    <React.StrictMode>
      <ArtifactVersionPicker runId="r1" agentId="prototype-specify" onSelect={() => {}} />
    </React.StrictMode>,
  );
  // Long enough for BOTH mounts' dynamic imports to settle.
  await new Promise((r) => setTimeout(r, 1000));

  const urls = fetchMock.mock.calls.map((c) => String((c as unknown[])[0]));
  expect(urls.filter((u) => u.includes("/api/runs/r1/artifacts")), JSON.stringify(urls)).toHaveLength(1);
});
