/**
 * ISS-766 (QA-PS-025, sibling of ISS-705) — regression check on FIX-111.
 * FIX-111 fixed the identical "prototype-build runs single_shot" failure for
 * one narrow case: composing the native `prototype-specify -> prototype-plan
 * -> prototype-build` triple through the composer with the `prototype.html`
 * deliverable selected. Its fix injected
 * `"prototype-build": { strategy: "task_loop" }` into the launch selections
 * whenever `deliverableOverride.name === "prototype.html"` AND
 * `prototype-build` was in the composed agent list.
 *
 * ISS-766 found that injection had vanished from both composer launch entry
 * points — IdeaInputPage.tsx and composer/ComposerPage.tsx. It is restored
 * (landed via 9efb704d) as ONE shared helper, `withPrototypeTaskLoop`, defined
 * and exported from IdeaInputPage.tsx and called by both (INV-12). These locks
 * pin that: the plain `mergedSelections` merge is still built, and it is fed
 * through the helper before launch in each file. Two launch paths, two tests.
 *
 * Source is read with CRLF normalised to LF: git stores these files as LF but
 * a Windows checkout materialises them as CRLF, and a multi-line `toContain`
 * written with `\n` must match on both.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const readSource = (rel: string) =>
  readFileSync(path.join(__dirname, rel), "utf8").replace(/\r\n/g, "\n");

describe("mergedSelections construction — ISS-766 FIX-111 task_loop injection missing", () => {
  it("IdeaInputPage.tsx still injects task_loop for prototype-build under the prototype.html deliverable", () => {
    const src = readSource("IdeaInputPage.tsx");

    // The plain-merge block the card names is still where the selections start.
    expect(src).toContain(
      "const mergedSelections = deliverableOverride\n      ? { ...selections, __deliverable__: deliverableOverride }\n      : selections;",
    );

    // FIX-111's rule lives in the shared helper: prototype.html deliverable +
    // prototype-build in the agent set + no explicit strategy → task_loop.
    expect(src).toContain("function withPrototypeTaskLoop(");
    expect(src).toContain('deliverableName !== "prototype.html"');
    expect(src).toContain('!agents.some((a) => a.id === "prototype-build")');
    expect(src).toContain('return { ...selections, "prototype-build": { ...entry, strategy: "task_loop" } };');

    // …and THIS launch path applies it to the merged selections it sends.
    expect(src).toContain(
      "const launchSelections = withPrototypeTaskLoop(\n      mergedSelections,\n      pipelineAgents,\n      deliverableOverride?.name,\n    );",
    );
    expect(src).toContain("selections: launchSelections");
  });

  it("ComposerPage.tsx still injects task_loop for prototype-build under the resolved deliverable", () => {
    const src = readSource("composer/ComposerPage.tsx");

    // The plain-merge block the card names is still where the selections start.
    expect(src).toContain(
      "const mergedSelections = effectiveDeliverable\n      ? { ...withSkills, __deliverable__: effectiveDeliverable }\n      : withSkills;",
    );

    // This newer entry point never had FIX-111's special case; it now calls the
    // SAME helper IdeaInputPage exports (INV-12 — no duplicated rule).
    expect(src).toMatch(/import\s*\{[^}]*\bwithPrototypeTaskLoop\b[^}]*\}\s*from\s*"[^"]*IdeaInputPage"/);
    expect(src).toContain(
      "const launchSelections = withPrototypeTaskLoop(\n      mergedSelections,\n      pipelineAgents,\n      effectiveDeliverable?.name,\n    );",
    );
  });
});
