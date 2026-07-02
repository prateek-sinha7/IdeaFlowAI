// ─────────────────────────────────────────────────────────────────────────────
// Workstream C1 (POR §6.1 / §7) — parseRunInput: the SINGLE FE-owned marker
// parser. Every marker family below is FE-composed elsewhere (exact, not
// heuristic — see the source anchors), so the parse is byte-exact string
// slicing over stable delimiters. This lib REPLACES the duplicated
// `safeCleanBrief` logic in DashboardLayout and the manual marker scan in
// RevisionFamilyView's preview shim (INV-12: one parser project-wide).
//
// Marker families (anchors):
//   - Attachment (symmetric):  `=== Attached: {name} === … === End: {name} ===`
//                              (IdeaInputPage.tsx:542)
//   - Existing base (ASYMMETRIC label): open `=== EXISTING {X} ===`,
//                              close `=== END EXISTING {Y} ===` (X != Y — e.g.
//                              PROTOTYPE HTML / HTML, PRESENTATION CODE / CODE)
//                              (DashboardLayout.tsx:496-548)
//   - Revision request:        `=== REVISION REQUEST ===` … (format-TOLERANT:
//                              closes at `=== END REQUEST ===`, the next line
//                              beginning `===`, or EOF)
//   - Chain context:           `=== CONTEXT FROM PREVIOUS PIPELINE ({type}) === …
//                              === END PREVIOUS CONTEXT ===` (DashboardLayout.tsx:926)
//   - User preferences:        `=== USER PREFERENCES === … === END PREFERENCES ===`
// ─────────────────────────────────────────────────────────────────────────────

export interface ParsedRunInput {
  brief: string;
  attachments: { name: string; content: string }[];
  revisionInstruction?: string;
  existingArtifactBlock?: string;
  chainContext?: string;
  preferences?: string;
}

/**
 * Decompose a run's `input` string into its FE-composed marker families.
 * Format-tolerant: clean / instruction-only input passes straight through as
 * `brief`; malformed or partial markers degrade to `brief` (never throw).
 */
export function parseRunInput(input: string): ParsedRunInput {
  const result: ParsedRunInput = { brief: "", attachments: [] };
  if (!input) return result;

  let remaining = input;

  // ── Attachments (symmetric name via backreference; supports multiple) ──────
  const attachRe = /=== Attached: (.+?) ===\n([\s\S]*?)\n=== End: \1 ===/g;
  remaining = remaining.replace(attachRe, (_m, name: string, content: string) => {
    result.attachments.push({ name, content: content.replace(/\n+$/, "") });
    return "";
  });

  // ── Existing base block (ASYMMETRIC labels — open EXISTING, close END
  //    EXISTING; label chars exclude `=`/newline so the open never matches the
  //    close). Only the first is meaningful; strip all. ─────────────────────
  const existingRe = /=== EXISTING [^\n=]*? ===\n([\s\S]*?)\n=== END EXISTING [^\n=]*? ===/g;
  remaining = remaining.replace(existingRe, (_m, inner: string) => {
    if (result.existingArtifactBlock === undefined) result.existingArtifactBlock = inner;
    return "";
  });

  // ── Chain context ─────────────────────────────────────────────────────────
  const chainRe = /=== CONTEXT FROM PREVIOUS PIPELINE \([^)]*\) ===\n([\s\S]*?)\n=== END PREVIOUS CONTEXT ===/g;
  remaining = remaining.replace(chainRe, (_m, inner: string) => {
    if (result.chainContext === undefined) result.chainContext = inner;
    return "";
  });

  // ── User preferences ──────────────────────────────────────────────────────
  const prefRe = /=== USER PREFERENCES ===\n([\s\S]*?)\n=== END PREFERENCES ===/g;
  remaining = remaining.replace(prefRe, (_m, inner: string) => {
    if (result.preferences === undefined) result.preferences = inner;
    return "";
  });

  // ── Revision request (format-tolerant; may be UNCLOSED) ───────────────────
  const rev = stripRevisionRequest(remaining);
  if (rev.instruction !== undefined) {
    result.revisionInstruction = rev.instruction;
    remaining = rev.text;
  }

  // Collapse the blank lines left where blocks were removed, then trim.
  result.brief = remaining.replace(/\n{3,}/g, "\n\n").trim();
  return result;
}

/**
 * Extract the `=== REVISION REQUEST ===` instruction and strip its block.
 * The block closes at `=== END REQUEST ===`, the next line beginning with
 * `===`, or EOF — an unclosed block still yields the instruction.
 */
function stripRevisionRequest(text: string): { text: string; instruction?: string } {
  const MARKER_LEN = "=== REVISION REQUEST ===".length;
  const idx = text.indexOf("=== REVISION REQUEST ===");
  if (idx < 0) return { text };

  let contentStart = idx + MARKER_LEN;
  if (text[contentStart] === "\n") contentStart += 1;

  const isEndRequest = (line: string) => /^\s*===\s*END REQUEST\s*===\s*$/.test(line);
  let cursor = contentStart;
  let instrEnd = text.length; // EOF default
  let blockEnd = text.length; // EOF default

  while (cursor <= text.length) {
    const nl = text.indexOf("\n", cursor);
    const lineEnd = nl === -1 ? text.length : nl;
    const line = text.slice(cursor, lineEnd);
    if (line.trimStart().startsWith("===")) {
      instrEnd = cursor;
      if (isEndRequest(line)) {
        blockEnd = nl === -1 ? text.length : nl + 1; // consume the closing marker
      } else {
        blockEnd = cursor; // leave the following (unrelated) marker in place
      }
      break;
    }
    if (nl === -1) break; // EOF — instruction runs to the end
    cursor = nl + 1;
  }

  const instruction = text.slice(contentStart, instrEnd).trim();
  const stripped = text.slice(0, idx) + text.slice(blockEnd);
  return { text: stripped, instruction };
}
