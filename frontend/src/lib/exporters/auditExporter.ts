/**
 * auditExporter — client-side CSV / JSON export for the Audit tab (SC-3, ND-6).
 *
 * ND-6: CSV and JSON ONLY, produced entirely in the browser as a Blob download.
 * There is NO PDF path and NO backend export route — nothing here touches the
 * network, so the already-authorized, owner-scoped audit rows never leave the
 * client to a third party (T-32-09-02).
 *
 * Mirrors the existing blob-download exporters (prototypeExporter /
 * storyExporter): build a Blob, object-URL it, click a synthetic anchor, revoke.
 */

/** A generic audit record. The Audit tab passes a normalized flat row shape. */
export type AuditRow = Record<string, unknown>;

/** Trigger a client-side blob download (no network — ND-6). */
function downloadBlob(content: string, mime: string, filename: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** Stable, first-seen-order union of every row's keys (rows can be heterogeneous). */
function collectHeaders(rows: AuditRow[]): string[] {
  const headers: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        seen.add(key);
        headers.push(key);
      }
    }
  }
  return headers;
}

/** Render a cell value to a string; objects/arrays are JSON-serialized. */
function cellToString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Escape a single CSV cell so it cannot break the CSV structure (T-32-09-03):
 *  - neutralize formula-injection leads (= + - @) by prefixing a single quote so
 *    a spreadsheet cannot execute the cell as a formula;
 *  - quote-wrap + double internal quotes when the value carries a comma, quote,
 *    CR or LF, so an embedded separator/newline stays inside one logical field.
 */
function escapeCsvCell(value: unknown): string {
  let s = cellToString(value);

  // Formula-injection guard (CSV injection / T-32-09-03): a leading =,+,-,@ (or a
  // control char) can be evaluated by Excel/Sheets — defuse it with a leading '.
  if (/^[=+\-@\t\r]/.test(s)) {
    s = `'${s}`;
  }

  // Structural escaping: any separator/quote/newline forces a quoted field.
  if (/[",\n\r]/.test(s)) {
    s = `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/**
 * Export audit rows as a client-side CSV blob download (ND-6).
 * Header is the union of row keys; every cell is escaped (T-32-09-03).
 */
export function exportAuditCSV(rows: AuditRow[], filename = "audit"): void {
  const headers = collectHeaders(rows);
  const headerLine = headers.map(escapeCsvCell).join(",");
  const dataLines = rows.map((row) =>
    headers.map((key) => escapeCsvCell(row[key])).join(","),
  );
  const csv = [headerLine, ...dataLines].join("\n");
  downloadBlob(csv, "text/csv;charset=utf-8", `${filename}.csv`);
}

/**
 * Export audit rows as a pretty-printed, client-side JSON blob download (ND-6).
 */
export function exportAuditJSON(rows: AuditRow[], filename = "audit"): void {
  const json = JSON.stringify(rows, null, 2);
  downloadBlob(json, "application/json;charset=utf-8", `${filename}.json`);
}
