/**
 * ISS-579 (QA-KB-019) — stripAttachmentMarker uses `[^\]]*` + split(", "), so a
 * filename containing "]" or ", " is never removed from the idea text.
 *
 * WorkflowView mounts hang the vitest worker in this environment (the sibling
 * WorkflowView.attachmentRemove.test.tsx hangs too), and the helper is not
 * exported, so the function source is extracted from WorkflowView.tsx and run
 * directly. Marker format written by the attach handler: `[Attached: a, b]`.
 * it.fails: red today, goes green (and fails loudly) once the fix lands.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = readFileSync(join(__dirname, "WorkflowView.tsx"), "utf8");
const m = src.match(/function stripAttachmentMarker\(text: string, filename: string\): string \{[\s\S]*?\n\}\n/);
if (!m) throw new Error("stripAttachmentMarker not found in WorkflowView.tsx");
const body = m[0].replace(/: string \| undefined/g, "").replace(/: string/g, "");
const strip = new Function(`${body}; return stripAttachmentMarker;`)() as (t: string, f: string) => string;

const marker = (names: string) => `[Attached: ${names}]`;

describe("WorkflowView stripAttachmentMarker — odd filenames (ISS-579)", () => {
  it('name containing "]" is fully removed', () => {
    expect(strip(marker("my].txt"), "my].txt")).toBe("");
  });

  it('name containing ", " is fully removed', () => {
    expect(strip(marker("a, b.txt"), "a, b.txt")).toBe("");
  });

  it('name containing both "]" and ", " is fully removed', () => {
    expect(strip(marker("a, b].txt"), "a, b].txt")).toBe("");
  });

  // Regression guards: pass today and must keep passing after the fix.
  it("plain name with text typed after the marker keeps the typed text", () => {
    expect(strip(`${marker("plain.txt")}hello`, "plain.txt")).toBe("hello");
  });

  it("removing one of two plain names keeps the other", () => {
    expect(strip(`idea\n\n${marker("a.txt, b.txt")}`, "a.txt")).toBe(`idea\n\n${marker("b.txt")}`);
  });
});
