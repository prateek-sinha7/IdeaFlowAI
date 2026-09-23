import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";
import React from "react";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-830 (sibling of ISS-800) — SandboxTab.tsx:1035-1066's own
// file-listing effect has no in-flight guard on getRunSandbox: `cancelled`
// blocks only the post-resolution setState, never the fetch call itself, so
// React StrictMode's dev-only mount->cleanup->mount double-invoke fires
// getRunSandbox twice per Workspace tab open on its own — before even
// counting PreviewPanel's independent second caller of the same endpoint.
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => "test-token"),
  getRunSandbox: vi.fn(),
  getRunSandboxFile: vi.fn(),
  getRunSandboxFileBlob: vi.fn(),
  getRunSandboxZip: vi.fn(),
}));

vi.mock("./FilesTab", () => ({
  downloadBlob: vi.fn(),
}));

import * as api from "@/lib/api";
import { SandboxTab } from "./SandboxTab";

beforeEach(() => {
  vi.mocked(api.getToken).mockReturnValue("test-token");
  vi.mocked(api.getRunSandbox).mockResolvedValue({
    run_id: "run-1",
    expired: false,
    truncated: false,
    files: [],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SandboxTab file-listing effect under StrictMode (QA-PS-048 / ISS-830)", () => {
  it("fires getRunSandbox exactly once per Workspace tab open, not twice", async () => {
    render(
      <React.StrictMode>
        <SandboxTab runId="run-1" />
      </React.StrictMode>,
    );

    await waitFor(() => {
      expect(api.getRunSandbox).toHaveBeenCalled();
    });

    // Without an in-flight guard, StrictMode's double-invoke fires this twice
    // — and that is BEFORE PreviewPanel's independent second caller of the
    // same endpoint, which is what compounds to the reported sandbox x4.
    expect(api.getRunSandbox).toHaveBeenCalledTimes(1);
  });
});
