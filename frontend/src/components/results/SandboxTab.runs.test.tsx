/**
 * Regression check against the REAL run artifacts on this machine.
 *
 * `fenceAgentPayloads` exists because agent outputs are markdown with a machine
 * payload pasted inside, and every previous attempt at handling that broke on a
 * shape no fixture had: a payload that already fenced itself, a deck with a
 * second document nested in its presenter-window template, an orphaned
 * `<!DOCTYPE html>` whose closing tag had already been consumed. Fixtures are
 * written from what went wrong last time; this reads what the pipeline actually
 * produced.
 *
 * Skipped wherever `runs/` is absent (CI, a fresh clone) — it is a check on
 * real data, not a substitute for the unit tests in SandboxTab.test.tsx.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import fs from "node:fs";
import path from "node:path";

import { fenceAgentPayloads } from "./SandboxTab";

const RUNS = path.resolve(__dirname, "../../../../runs");
const HAVE_RUNS = fs.existsSync(RUNS);

function markdownIn(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    // `.logs/` is the engine trace and `.uploads/` is the owner's staging —
    // neither is listed in the workspace, so neither is ever rendered.
    if (e.isDirectory()) {
      if (e.name === ".logs" || e.name === ".uploads") continue;
      markdownIn(full, out);
    } else if (/\.(md|markdown)$/i.test(e.name)) out.push(full);
  }
  return out;
}

describe.skipIf(!HAVE_RUNS)("fenceAgentPayloads over real runs", () => {
  it("leaves no payload in a paragraph, and renders every file fast", () => {
    const files = markdownIn(RUNS);
    expect(files.length).toBeGreaterThan(0);
    render(<ReactMarkdown>{"# warm"}</ReactMarkdown>);

    const problems: string[] = [];
    for (const file of files) {
      const name = path.basename(file);
      const fixed = fenceAgentPayloads(fs.readFileSync(file, "utf8"));

      // Unbalanced fences spill the tail of the document into the page.
      const fences = (fixed.match(/^(`{3,}|~{3,})/gm) || []).length;
      if (fences % 2 !== 0) problems.push(`${name}: ${fences} fence markers (odd)`);

      const started = performance.now();
      const { container } = render(
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{fixed}</ReactMarkdown>,
      );
      const ms = performance.now() - started;

      // The failure this whole transform exists to prevent: a machine payload
      // escaped tag by tag and reflowed into a paragraph.
      const paragraphs = [...container.querySelectorAll("p")].map((n) => n.textContent || "");
      for (const marker of ["<!DOCTYPE", "<artifact", "<spec>", "```"])
        if (paragraphs.some((text) => text.includes(marker)))
          problems.push(`${name}: "${marker}" reached a <p>`);

      // …and the payload has to land somewhere, not vanish.
      const code = [...container.querySelectorAll("pre")].map((n) => n.textContent).join("");
      if (fixed.includes("<!DOCTYPE html") && !code.includes("<!DOCTYPE html"))
        problems.push(`${name}: has a document but none reached a <pre>`);

      // 313 KB of conversation_history took 4341ms before the transform.
      if (ms > 500) problems.push(`${name}: ${ms.toFixed(0)}ms to render`);
    }

    expect(problems).toEqual([]);
  });
});
