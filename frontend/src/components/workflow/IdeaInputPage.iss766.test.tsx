/**
 * ISS-766 (QA-PS-025, sibling of ISS-705) — regression check on FIX-111.
 * FIX-111 fixed the identical "prototype-build runs single_shot" failure for
 * one narrow case: composing the native `prototype-specify -> prototype-plan
 * -> prototype-build` triple through the composer with the `prototype.html`
 * deliverable selected. Its fix injected
 * `"prototype-build": { strategy: "task_loop" }` into `mergedSelections`
 * whenever `deliverableOverride.name === "prototype.html"` AND
 * `prototype-build` was in the composed agent list. Neither of today's two
 * composer launch entry points — IdeaInputPage.tsx and
 * composer/ComposerPage.tsx — contains that special-case anymore; both build
 * `mergedSelections` as a plain passthrough merge. Two distinct launch
 * paths, two tests, per the card. Both pin the gap against the real, current
 * source, so they fail today and start failing loudly once the injection is
 * restored in each file.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("mergedSelections construction — ISS-766 FIX-111 task_loop injection missing", () => {
  it("IdeaInputPage.tsx still injects task_loop for prototype-build under the prototype.html deliverable", () => {
    const src = readFileSync(path.join(__dirname, "IdeaInputPage.tsx"), "utf8");

    // Sanity: the exact plain-merge shape the card names must still be here,
    // otherwise this test is no longer pinning the right block.
    expect(src).toContain(
      "const mergedSelections = deliverableOverride\n      ? { ...selections, __deliverable__: deliverableOverride }\n      : selections;",
    );

    // ISS-766 unfixed: FIX-111's prototype-build/task_loop special case no
    // longer exists anywhere in this file.
    expect(src).toContain("task_loop");
  });

  it("ComposerPage.tsx still injects task_loop for prototype-build under the resolved deliverable", () => {
    const src = readFileSync(
      path.join(__dirname, "composer/ComposerPage.tsx"),
      "utf8",
    );

    // Sanity: the exact plain-merge shape the card names must still be here.
    expect(src).toContain(
      "const mergedSelections = effectiveDeliverable\n      ? { ...withSkills, __deliverable__: effectiveDeliverable }\n      : withSkills;",
    );

    // ISS-766 unfixed: this newer launch entry point never had FIX-111's
    // prototype-build/task_loop special case at all.
    expect(src).toContain("task_loop");
  });
});
