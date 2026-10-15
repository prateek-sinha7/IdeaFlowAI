/**
 * ISS-1026 — Back/forward onto the pinned Preview URL /runs/{id}/versions/{v}
 * must re-open Preview. The tracked-run branch of page.tsx maps only
 * "run-detail" to "preview"; "run-version" is its pinned twin.
 * `it.fails` = strict xfail: remove `.fails` when the fix lands.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pageSource = readFileSync(resolve(__dirname, "page.tsx"), "utf8");

describe("ISS-1026 — tracked-run branch re-opens Preview for run-version", () => {
  it("maps run-version to the preview tab like run-detail", () => {
    const start = pageSource.indexOf("if (runId === trackedRunIdRef.current) {");
    expect(start).toBeGreaterThan(-1);
    const branch = pageSource.slice(start, pageSource.indexOf("\n    }", start));
    expect(branch).toContain("reopenTabFor(parsedView.screen)");
    expect(branch).toMatch(/run-version[\s\S]*"preview"/);
  });
});
