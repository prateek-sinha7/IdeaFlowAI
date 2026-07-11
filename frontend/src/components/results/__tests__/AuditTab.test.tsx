import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  cleanup,
} from "@testing-library/react";
import React from "react";
import { exportAuditCSV, exportAuditJSON } from "@/lib/exporters/auditExporter";
import * as exporterMod from "@/lib/exporters/auditExporter";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 32 plan 09 (SC-3, ND-6) — the Audit-tab export util + tab repoint.
//
//   Task 2: auditExporter — client-side CSV/JSON blob download ONLY. No PDF,
//     no backend export route (ND-6). CSV cells escape commas/quotes/newlines
//     so a cell cannot break the CSV structure (T-32-09-03).
//
//   Task 3: AuditTab reads the 3 plan-03 endpoints (gate-events /
//     validation-results / exec-runs) instead of the wrong hook_runs source,
//     renders counters / coverage chips / severity filters, and exports the
//     current (filtered) rows via the Task-2 util.
//
// jsdom does not implement URL.createObjectURL / anchor navigation — both are
// stubbed so we can capture the produced Blob and assert its bytes.
// ─────────────────────────────────────────────────────────────────────────────

// Motion mock (mirrors the sibling PreviewPanel-area component tests).
const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_t, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

// Mock the API layer so the tab's fetchers are observable + deterministic.
vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => "tok"),
  getRunGateEvents: vi.fn(),
  getRunValidationResults: vi.fn(),
  getRunExecRuns: vi.fn(),
  getRunHookRuns: vi.fn(),
}));

import * as api from "@/lib/api";
import { AuditTab } from "../AuditTab";

describe("auditExporter (ND-6 — client-side CSV/JSON blob download only)", () => {
  let blobs: Blob[] = [];
  let clicks = 0;
  const origCreate = URL.createObjectURL;
  const origRevoke = URL.revokeObjectURL;
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    blobs = [];
    clicks = 0;
    URL.createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return "blob:mock-url";
    }) as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      clicks += 1;
    });
    fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    URL.createObjectURL = origCreate;
    URL.revokeObjectURL = origRevoke;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const ROWS = [
    { kind: "gate", step: "build", verdict: "pass", detail: "all good" },
    { kind: "validation", step: "build", verdict: "block", detail: "found 2 issues" },
  ];

  it("exportAuditJSON pretty-prints the rows into a client-side JSON blob download", async () => {
    exportAuditJSON(ROWS, "audit");
    expect(clicks).toBe(1);
    expect(blobs).toHaveLength(1);
    expect(blobs[0].type).toContain("application/json");
    const text = await blobs[0].text();
    expect(text).toContain("\n");
    expect(text).toContain("  ");
    expect(JSON.parse(text)).toEqual(ROWS);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("exportAuditCSV writes a header row + one row per record", async () => {
    exportAuditCSV(ROWS, "audit");
    expect(clicks).toBe(1);
    expect(blobs).toHaveLength(1);
    expect(blobs[0].type).toContain("text/csv");
    const text = await blobs[0].text();
    const lines = text.trim().split(/\r?\n/);
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe("kind,step,verdict,detail");
    expect(lines[1]).toContain("gate");
    expect(lines[2]).toContain("validation");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("exportAuditCSV escapes commas, quotes and newlines so a cell cannot break structure", async () => {
    const nasty = [{ a: "has,comma", b: 'has "quote"', c: "has\nnewline", d: "plain" }];
    exportAuditCSV(nasty, "audit");
    const text = await blobs[0].text();
    const lines = text.split(/\r?\n/);
    expect(lines[0]).toBe("a,b,c,d");
    expect(text).toContain('"has,comma"');
    expect(text).toContain('"has ""quote"""');
    expect(text).toContain('"has\nnewline"');
    expect(text).toContain("plain");
  });

  it("exportAuditCSV neutralizes formula-injection leads (=,+,-,@) so a cell cannot execute", async () => {
    const rows = [{ a: "=cmd()", b: "+1", c: "-2", d: "@x" }];
    exportAuditCSV(rows, "audit");
    const text = await blobs[0].text();
    expect(text).toContain("'=cmd()");
    expect(text).toContain("'+1");
    expect(text).toContain("'-2");
    expect(text).toContain("'@x");
  });

  it("both exporters trigger a client blob download and never call a backend route", () => {
    exportAuditJSON(ROWS);
    exportAuditCSV(ROWS);
    expect(clicks).toBe(2);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Task 3 — AuditTab repoint onto the 3 endpoints + counters/filters/export.
// ─────────────────────────────────────────────────────────────────────────────

describe("AuditTab (SC-3 — 3-endpoint reader + severity filters + export)", () => {
  const RUN = "r1";

  beforeEach(() => {
    vi.mocked(api.getToken).mockReturnValue("tok");
    vi.mocked(api.getRunGateEvents).mockResolvedValue({
      workflow_id: RUN,
      gate_events: [
        { id: "g1", run_id: RUN, step: "specify", gate: "human", outcome: "pass", detail: { note: "ok" }, created_at: "2026-07-08T10:00:00Z" },
        { id: "g2", run_id: RUN, step: "build", gate: "security", outcome: "block", detail: { note: "denied" }, created_at: "2026-07-08T10:01:00Z" },
      ],
    });
    vi.mocked(api.getRunValidationResults).mockResolvedValue({
      workflow_id: RUN,
      validation_results: [
        { id: "v1", run_id: RUN, step: "build", validator: "static_check", severity: "CRITICAL", attempt: 1, issues: ["boom"], created_at: "2026-07-08T10:02:00Z" },
        { id: "v2", run_id: RUN, step: "build", validator: "axe_check", severity: "LOW", attempt: 1, issues: [], created_at: "2026-07-08T10:03:00Z" },
      ],
    });
    vi.mocked(api.getRunExecRuns).mockResolvedValue({
      workflow_id: RUN,
      exec_runs: [
        { id: "e1", run_id: RUN, step: "build", argv_json: ["ls", "-la"], outcome: "allowed", exit_code: 0, duration_ms: 12, policy_snapshot_json: {}, output_digest: "abc123", created_at: "2026-07-08T10:04:00Z" },
      ],
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("reads the 3 plan-03 endpoints (not getRunHookRuns) for the current run", async () => {
    render(<AuditTab workflowRunId={RUN} />);
    await waitFor(() => {
      expect(api.getRunGateEvents).toHaveBeenCalledWith("tok", RUN);
    });
    expect(api.getRunValidationResults).toHaveBeenCalledWith("tok", RUN);
    expect(api.getRunExecRuns).toHaveBeenCalledWith("tok", RUN);
    // The wrong source must NOT be read.
    expect(api.getRunHookRuns).not.toHaveBeenCalled();
  });

  it("renders rows merged from all 3 sources", async () => {
    render(<AuditTab workflowRunId={RUN} />);
    expect(await screen.findByText(/static_check/)).toBeTruthy();
    expect(screen.getByText(/axe_check/)).toBeTruthy();
    // gate + exec rows also present (the gate kind "security" also appears in the
    // header subline, so assert at least one occurrence).
    expect(screen.getAllByText(/security/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/ls/)).toBeTruthy();
  });

  it("severity filter narrows the rendered rows", async () => {
    render(<AuditTab workflowRunId={RUN} />);
    await screen.findByText(/static_check/);
    // Both severities visible initially.
    expect(screen.getByText(/axe_check/)).toBeTruthy();
    // Activate the CRITICAL severity filter.
    fireEvent.click(screen.getByTestId("sev-filter-CRITICAL"));
    await waitFor(() => {
      expect(screen.queryByText(/axe_check/)).toBeNull();
    });
    // The critical row survives the filter.
    expect(screen.getByText(/static_check/)).toBeTruthy();
  });

  it("the Export ▾ menu's CSV / JSON items invoke the Task-2 util over the current rows", async () => {
    const csvSpy = vi.spyOn(exporterMod, "exportAuditCSV").mockImplementation(() => {});
    const jsonSpy = vi.spyOn(exporterMod, "exportAuditJSON").mockImplementation(() => {});
    render(<AuditTab workflowRunId={RUN} />);
    await screen.findByText(/static_check/);
    // The export options live behind the brand Export ▾ menu; each click closes it.
    fireEvent.click(screen.getByTestId("audit-export-menu"));
    fireEvent.click(screen.getByTestId("audit-export-csv"));
    fireEvent.click(screen.getByTestId("audit-export-menu"));
    fireEvent.click(screen.getByTestId("audit-export-json"));
    expect(csvSpy).toHaveBeenCalledTimes(1);
    expect(jsonSpy).toHaveBeenCalledTimes(1);
    // Called with a non-empty rows array (5 merged rows).
    expect(Array.isArray(csvSpy.mock.calls[0][0])).toBe(true);
    expect((csvSpy.mock.calls[0][0] as unknown[]).length).toBe(5);
    csvSpy.mockRestore();
    jsonSpy.mockRestore();
  });

  it("renders the 6-stat compliance grid + verdict banner derived from the live rows", async () => {
    render(<AuditTab workflowRunId={RUN} />);
    await screen.findByText(/static_check/);
    // 5 merged rows → Checks 5. One gate 'block' + one CRITICAL validation → not clean.
    expect(screen.getByTestId("audit-stat-checks").textContent).toContain("5");
    const banner = screen.getByTestId("audit-verdict-banner");
    expect(banner.getAttribute("data-clean")).toBe("false");
    expect(banner.textContent).toMatch(/governance stopped this run/i);
  });

  it("shows the green 'passed all governance gates' banner for a clean run", async () => {
    vi.mocked(api.getRunGateEvents).mockResolvedValue({
      workflow_id: RUN,
      gate_events: [
        { id: "g1", run_id: RUN, step: "specify", gate: "human", outcome: "pass", detail: { note: "ok" }, created_at: "2026-07-08T10:00:00Z" },
      ],
    });
    vi.mocked(api.getRunValidationResults).mockResolvedValue({
      workflow_id: RUN,
      validation_results: [
        { id: "v1", run_id: RUN, step: "build", validator: "static_check", severity: "pass", attempt: 1, issues: [], created_at: "2026-07-08T10:02:00Z" },
      ],
    });
    vi.mocked(api.getRunExecRuns).mockResolvedValue({
      workflow_id: RUN,
      exec_runs: [
        { id: "e1", run_id: RUN, step: "build", argv_json: ["ls"], outcome: "allowed", exit_code: 0, duration_ms: 12, policy_snapshot_json: {}, output_digest: "abc", created_at: "2026-07-08T10:04:00Z" },
      ],
    });
    render(<AuditTab workflowRunId={RUN} />);
    await screen.findByText(/static_check/);
    const banner = screen.getByTestId("audit-verdict-banner");
    expect(banner.getAttribute("data-clean")).toBe("true");
    expect(banner.textContent).toMatch(/passed all governance gates/i);
  });

  it("renders gracefully when a cross-owner / missing run yields empty envelopes", async () => {
    vi.mocked(api.getRunGateEvents).mockResolvedValue({ workflow_id: RUN, gate_events: [] });
    vi.mocked(api.getRunValidationResults).mockResolvedValue({ workflow_id: RUN, validation_results: [] });
    vi.mocked(api.getRunExecRuns).mockResolvedValue({ workflow_id: RUN, exec_runs: [] });
    render(<AuditTab workflowRunId={RUN} />);
    expect(await screen.findByText(/No audit records/i)).toBeTruthy();
  });
});
