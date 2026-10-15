import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ISS-682 (QA-KB-021): the page.tsx cold-mount seeds for /workflows/{id}/edit and
// /run must carry the saved row's manifest, or ComposerPage.initialManifest is
// undefined and a re-save drops limits / input_providers / seed_files.
// Source-lock: page.tsx has no mount harness.
const src = readFileSync(resolve(__dirname, "page.tsx"), "utf8");
const MANIFEST = "manifest: (saved.manifest as Record<string, unknown> | undefined) ?? null";

function slice(from: string, to: string): string {
  const a = src.indexOf(from);
  expect(a, `anchor not found: ${from}`).toBeGreaterThan(-1);
  const b = src.indexOf(to, a);
  expect(b, `anchor not found: ${to}`).toBeGreaterThan(a);
  return src.slice(a, b);
}

describe("ISS-682 page.tsx seeds carry the saved row manifest", () => {
  it("/edit effect seeds manifest", () => {
    const s = slice("const workflowId = workflowEditIdFor(parsedView);", "const workflowId = workflowDetailIdFor(parsedView);");
    expect(s).toContain(MANIFEST);
  });
  it("/run effect seeds manifest", () => {
    const s = slice("const workflowId = workflowRunIdFor(parsedView);", 'setWorkflowRunMainView(isComposerWorkflow(saved) ? "composer" : "input");');
    expect(s).toContain(MANIFEST);
  });
});
