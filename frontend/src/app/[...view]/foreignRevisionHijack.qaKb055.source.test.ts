/**
 * QA-KB-055 — another family's finished `*_revision` must not re-point the
 * run-detail screen being viewed. Cards: ISS-745 (root), ISS-1074, ISS-1077.
 * page.tsx is too large to mount, so these are source assertions
 * (same idiom as contentSourceRunScope.source.test.ts). They assert the
 * CORRECT shape, so they fail today and pass once the lineage guard lands.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const page = readFileSync(path.join(__dirname, "page.tsx"), "utf8");
const _layout = readFileSync(
  path.join(__dirname, "..", "..", "components", "layout", "DashboardLayout.tsx"),
  "utf8",
);

function handlerWindow(): string {
  const start = page.indexOf("const isRevisionCompletion");
  expect(start).toBeGreaterThan(-1);
  const end = page.indexOf("setContentSourceRunId(completingRunId)", start);
  expect(end).toBeGreaterThan(start);
  return page.slice(start, end);
}

describe("QA-KB-055 foreign-family revision completion", () => {
  it("ISS-745: isRevisionCompletion requires lineage, not just the _revision suffix", () => {
    const w = handlerWindow();
    const decl = w.slice(0, w.indexOf(";") + 1);
    // Today: the declaration is the bare endsWith("_revision") test.
    // Fixed: it (or the admitting condition) also ties the run to the tracked family.
    const lineageRef = /root|family|lineage|parent/i.test(decl.replace(/_revision/g, ""));
    const admit = w.slice(w.indexOf("if (completingRunId && (!isForeignCompletion"));
    const admitLineage = /root|family|lineage|parent|sameFamily/i.test(admit.split("\n")[0]);
    expect(lineageRef || admitLineage).toBe(true);
  });

  it("ISS-1074: final_output is not written into Preview slots for a foreign-family completion", () => {
    const from = page.indexOf("setContentSourceRunId(completingRunId)");
    const slots = page.indexOf("setUserStoryContent(finalOutput)", from);
    expect(slots).toBeGreaterThan(from);
    // Look at the code between the finalOutput read and the first slot write
    const gate = page.slice(page.indexOf("const finalOutput = data.final_output", from), slots);
    expect(/isForeign|sameFamily|isViewedFamily|foreign/i.test(gate)).toBe(true);
  });

  // ISS-1077 retired 2026-10-09: the owner chose option a (ESCALATIONS.md#qa-kb-055). The
  // Revision Families B1 pin (revisionFamilyLinkage.source.test.ts:28) stands; FIX-752 covers the trigger.
});
