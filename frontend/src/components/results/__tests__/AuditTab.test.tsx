import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { exportAuditCSV, exportAuditJSON } from "@/lib/exporters/auditExporter";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 32 plan 09 (SC-3, ND-6) — the Audit-tab export util + tab repoint.
//
//   Task 2: auditExporter — client-side CSV/JSON blob download ONLY. No PDF,
//     no backend export route (ND-6). CSV cells escape commas/quotes/newlines
//     so a cell cannot break the CSV structure (T-32-09-03).
//
// jsdom does not implement URL.createObjectURL / anchor navigation — both are
// stubbed so we can capture the produced Blob and assert its bytes.
// ─────────────────────────────────────────────────────────────────────────────

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
    // ND-6: the exporter MUST NOT touch the network.
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
    // Pretty-printed (2-space indent → contains newlines + indentation).
    expect(text).toContain("\n");
    expect(text).toContain("  ");
    expect(JSON.parse(text)).toEqual(ROWS);
    // ND-6 — no network.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("exportAuditCSV writes a header row + one row per record", async () => {
    exportAuditCSV(ROWS, "audit");
    expect(clicks).toBe(1);
    expect(blobs).toHaveLength(1);
    expect(blobs[0].type).toContain("text/csv");
    const text = await blobs[0].text();
    const lines = text.trim().split(/\r?\n/);
    // header + 2 data rows
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe("kind,step,verdict,detail");
    expect(lines[1]).toContain("gate");
    expect(lines[2]).toContain("validation");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("exportAuditCSV escapes commas, quotes and newlines so a cell cannot break structure", async () => {
    const nasty = [
      {
        a: "has,comma",
        b: 'has "quote"',
        c: "has\nnewline",
        d: "plain",
      },
    ];
    exportAuditCSV(nasty, "audit");
    const text = await blobs[0].text();
    const lines = text.split(/\r?\n/);
    // Header unaffected.
    expect(lines[0]).toBe("a,b,c,d");
    // A comma cell is quote-wrapped.
    expect(text).toContain('"has,comma"');
    // Internal quotes are doubled inside a quoted cell.
    expect(text).toContain('"has ""quote"""');
    // A newline cell is quote-wrapped (so it does not spawn a new record).
    expect(text).toContain('"has\nnewline"');
    // The escaped newline must NOT create an extra structural record: the single
    // data row (containing an embedded newline) means the raw text has exactly
    // one more physical line than a fully-flat row, but re-parsing the quoted
    // field keeps it one logical record — assert the plain cell survives intact.
    expect(text).toContain("plain");
  });

  it("exportAuditCSV neutralizes formula-injection leads (=,+,-,@) so a cell cannot execute", async () => {
    const rows = [{ a: "=cmd()", b: "+1", c: "-2", d: "@x" }];
    exportAuditCSV(rows, "audit");
    const text = await blobs[0].text();
    // Each dangerous lead is prefixed with a single quote (Excel/Sheets guard).
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
