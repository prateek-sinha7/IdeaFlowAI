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

// Ordinary prose of a realistic size, rendered in the SAME run as the corpus so
// it carries the same machine load. Rendering speed is compared against this,
// never against a wall-clock number: under vitest's parallel pool the identical
// 311 KB file takes 1.3s alone and 10s alongside 128 other suites, so an absolute
// budget measures the runner, not the transform. A ratio cancels that out.
const CONTROL_PROSE =
  "Ordinary prose a person might plausibly write, with a `code span` and a [link](x).\n\n".repeat(1500);

// Below this, a file's time is dominated by fixed per-render overhead rather than
// its content — a 0.4 KB greeting measures 128 ms/KB and means nothing. Small
// files get the flat budget; only real documents are rate-checked.
const RATE_CHECK_FROM_KB = 50;

// Headroom over the worst healthy file measured across this corpus (2.85x control
// under load, a prose-heavy 311 KB conversation_history), and far below the
// pathology this guards: 313 KB took 4341ms before the transform existed, on a
// machine where ordinary prose ran orders faster.
const MAX_RATE_VS_CONTROL = 6;

describe.skipIf(!HAVE_RUNS)("fenceAgentPayloads over real runs", () => {
  it("leaves no payload in a paragraph, and renders every file fast", () => {
    const files = markdownIn(RUNS);
    expect(files.length).toBeGreaterThan(0);
    render(<ReactMarkdown>{"# warm"}</ReactMarkdown>);

    const controlStarted = performance.now();
    render(<ReactMarkdown remarkPlugins={[remarkGfm]}>{CONTROL_PROSE}</ReactMarkdown>);
    const controlRate = (performance.now() - controlStarted) / (CONTROL_PROSE.length / 1024);

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
      // Read only the text OUTSIDE inline code. A payload that leaked is escaped
      // tag by tag into running prose; `<artifact>` inside backticks is prose
      // ABOUT the format — the agent instructions say "Emit between `<artifact>`
      // tags:", which renders as <p><code>&lt;artifact&gt;</code></p>. That is
      // correct output, and counting it as a leak made this check fail on three
      // files that render exactly as intended.
      const paragraphs = [...container.querySelectorAll("p")].map((n) => {
        const clone = n.cloneNode(true) as HTMLElement;
        clone.querySelectorAll("code").forEach((c) => c.remove());
        return clone.textContent || "";
      });
      for (const marker of ["<!DOCTYPE", "<artifact", "<spec>", "```"])
        if (paragraphs.some((text) => text.includes(marker)))
          problems.push(`${name}: "${marker}" reached a <p>`);

      // …and the payload has to land somewhere, not vanish.
      const code = [...container.querySelectorAll("pre")].map((n) => n.textContent).join("");
      if (fixed.includes("<!DOCTYPE html") && !code.includes("<!DOCTYPE html"))
        problems.push(`${name}: has a document but none reached a <pre>`);

      // The flat 500ms this used to assert was right when the biggest file here was
      // the 313 KB conversation_history that took 4341ms before the transform. The
      // corpus now holds a 2.2 MB one, and a document that is merely LARGE is not
      // the failure being guarded — a document that tokenises pathologically is,
      // at any size. So: rate against the control, not wall-clock.
      const kb = fixed.length / 1024;
      if (kb >= RATE_CHECK_FROM_KB) {
        const rate = ms / kb;
        if (rate > controlRate * MAX_RATE_VS_CONTROL)
          problems.push(
            `${name}: ${rate.toFixed(2)} ms/KB over ${kb.toFixed(0)}KB — ` +
              `${(rate / controlRate).toFixed(1)}x ordinary prose, past the ${MAX_RATE_VS_CONTROL}x ceiling`,
          );
      } else if (ms > 500) {
        problems.push(`${name}: ${ms.toFixed(0)}ms to render`);
      }
    }

    expect(problems).toEqual([]);
    // 30s for the SUITE, which is not the same budget as the per-file one above:
    // this renders every markdown file under runs/ — 172 of them, ~3.5 MB — and
    // takes ~7s on this machine, over vitest's 5s default. The per-file budget is
    // what guards rendering speed; this only stops the whole sweep being cut off.
  }, 30_000);
});
