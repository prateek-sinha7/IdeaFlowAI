import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";
import React from "react";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-800 — AuditTab's single fetch effect (AuditTab.tsx:463-609)
// has no in-flight guard on getRunGateEvents / getRunValidationResults /
// getRunExecRuns / getRunHookRuns. `cancelled` blocks only the post-resolution
// setState, never the fetch calls themselves, so React StrictMode's dev-only
// mount->cleanup->mount double-invoke fires each endpoint twice per Audit tab
// open (confirmed 3/3 live, see ISS-800's own Reproduction section).
//
// Mounting under <React.StrictMode> reproduces the real dev double-invoke in
// jsdom (same technique as DashboardLayout.launchLatch.test.tsx for BUG-007).
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_t, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
          React.createElement(prop, rest, children),
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => "tok"),
  getRunGateEvents: vi.fn(),
  getRunValidationResults: vi.fn(),
  getRunExecRuns: vi.fn(),
  getRunHookRuns: vi.fn(),
}));

import * as api from "@/lib/api";
import { AuditTab } from "./AuditTab";

const RUN = "r1";

beforeEach(() => {
  vi.mocked(api.getToken).mockReturnValue("tok");
  vi.mocked(api.getRunGateEvents).mockResolvedValue({ workflow_id: RUN, gate_events: [] });
  vi.mocked(api.getRunValidationResults).mockResolvedValue({ workflow_id: RUN, validation_results: [] });
  vi.mocked(api.getRunExecRuns).mockResolvedValue({ workflow_id: RUN, exec_runs: [] });
  vi.mocked(api.getRunHookRuns).mockResolvedValue({ workflow_id: RUN, hook_runs: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuditTab fetch effect under StrictMode (QA-PS-048 / ISS-800)", () => {
  it("fires each of the 4 audit endpoints exactly once per Audit tab open, not twice", async () => {
    render(
      <React.StrictMode>
        <AuditTab workflowRunId={RUN} />
      </React.StrictMode>,
    );

    await waitFor(() => {
      expect(api.getRunGateEvents).toHaveBeenCalled();
    });

    // Without an in-flight guard, StrictMode's double-invoke fires each of
    // these twice — the bug's own headline symptom.
    expect(api.getRunGateEvents).toHaveBeenCalledTimes(1);
    expect(api.getRunValidationResults).toHaveBeenCalledTimes(1);
    expect(api.getRunExecRuns).toHaveBeenCalledTimes(1);
    expect(api.getRunHookRuns).toHaveBeenCalledTimes(1);
  });
});
