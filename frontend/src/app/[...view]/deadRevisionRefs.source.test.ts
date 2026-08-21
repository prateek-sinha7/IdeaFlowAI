import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// ISS-063 — INV-12 exit gate (source-lock).
//
// This family has produced a dead revision counter twice already: the original
// in `useWorkflow.ts` (deleted by ISS-039 as write-only dead state) and the
// `specRevisionCount` field in `useRunStateStore.ts` (declared, initialised,
// never written, never read). The fix derives the count in the reducer, so
// FIX-163/164's ref-based detector in `page.tsx` is SUPERSEDED — deleting it is
// part of the change, not a follow-up. Without this lock a third counter is one
// careless merge away.
//
// The huge page.tsx is impractical to render, so this uses the sanctioned
// grep-style source assertion (mirrors attachRunOnOpen.source.test.ts).
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(resolve(__dirname, "page.tsx"), "utf8");
const storeSource = readFileSync(resolve(__dirname, "../../hooks/useRunStateStore.ts"), "utf8");

describe("ISS-063 the superseded arm/consume detector is deleted (source-lock)", () => {
  it.each([
    ["revisionCycleArmedRef", "the arm whose predicate was structurally unsatisfiable"],
    ["setSpecRevisionCountRef", "the setter ref the detector incremented through"],
    ["pipelineAgentsRef", "the post-commit ref the detector read, stale during replay"],
  ])("page.tsx no longer references %s (%s)", (symbol) => {
    // FAIL-BEFORE: all three still live in page.tsx — RED.
    expect(pageSource).not.toContain(symbol);
  });

  it("page.tsx holds no local specRevisionCount state", () => {
    // FAIL-BEFORE: `const [specRevisionCount, setSpecRevisionCount] = useState(0)` — RED.
    expect(pageSource).not.toContain("setSpecRevisionCount");
  });

  it("page.tsx feeds the banner from the per-run store, the single source", () => {
    // FAIL-BEFORE: it passes the local useState value — RED.
    expect(pageSource.replace(/\s+/g, " ")).toContain(
      "specRevisionCount={runStore.viewed.specRevisionCount}",
    );
  });

  it("the store is the one writer of specRevisionCount", () => {
    // FAIL-BEFORE: the field at useRunStateStore.ts:81 is never assigned — RED.
    expect(storeSource).toContain("entry.specRevisionCount = deriveSpecRevisionCount(");
  });
});
