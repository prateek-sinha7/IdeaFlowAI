import { readFileSync } from "node:fs";
import { join } from "node:path";
/**
 * SandboxTab — the run workspace (spec 017 phase 2).
 *
 * The behaviours worth pinning:
 *
 *  1. Two panes. Artifacts = root-level deliverables + `.agents/` on a spine.
 *     All files = every group, sortable. Both derive from the listing alone —
 *     no test here names a workflow, because the component cannot either.
 *  2. `deliverable: false` is the SERVER's answer (`is_deliverable_relpath`).
 *     The component must not re-derive it, or `_DELIVERABLE_EXCLUDE` grows a
 *     second copy in TypeScript that drifts.
 *  3. The tree is built from a FLAT listing (the API returns paths, not nodes).
 *  4. A file's bytes are fetched only when it is opened — the whole reason this
 *     tab exists rather than extending FilesTab, which receives everything up
 *     front. Toggling a view never refetches.
 *  5. A binary is not previewed; Download fetches it WITH the auth header — an
 *     <a href> at the endpoint sends none and saves the API's 401 body (BUG-031).
 *  6. An expired workspace says so. An empty tree would read as "the run wrote
 *     nothing", which is a different and wrong statement.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  SandboxTab,
  artifactGroups,
  allFileGroups,
  agentIdFromPath,
  fenceAgentPayloads,
} from "./SandboxTab";
import type { SandboxFile } from "@/lib/api";

const getRunSandbox = vi.fn();
const getRunSandboxFile = vi.fn();
const getRunSandboxFileBlob = vi.fn();
const getRunSandboxZip = vi.fn();
const downloadBlob = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getRunSandbox: (...args: unknown[]) => getRunSandbox(...args),
  getRunSandboxFile: (...args: unknown[]) => getRunSandboxFile(...args),
  getRunSandboxFileBlob: (...args: unknown[]) => getRunSandboxFileBlob(...args),
  getRunSandboxZip: (...args: unknown[]) => getRunSandboxZip(...args),
}));

vi.mock("./FilesTab", () => ({
  downloadBlob: (...args: unknown[]) => downloadBlob(...args),
}));

const f = (
  path: string,
  size: number,
  extra: Partial<SandboxFile> = {},
): SandboxFile => ({ path, size, modified: 1, text: true, kind: "text", deliverable: true, ...extra });

/** The shape a real ppt_v2 run leaves behind. */
const PPT_V2 = {
  run_id: "run-1",
  expired: false,
  truncated: false,
  files: [
    f("presentation.pptx", 251_000, { text: false, kind: "binary" }),
    f("presentation.html", 52_000),
    f("PLANNER.md", 2_000, { deliverable: false }),
    f(".agents/01-ppt-brief-analyst.md", 9_000, { deliverable: false }),
    f(".agents/02-ppt-composer.md", 53_000, { deliverable: false }),
    f(".verify/report.txt", 14_000, { deliverable: false }),
    f(".verify/slide-01.png", 24_000, { text: false, kind: "image", deliverable: false }),
    f(".verify/presentation.pdf", 495_000, { text: false, kind: "pdf", deliverable: false }),
  ],
};

const AGENT_NAMES = {
  "ppt-brief-analyst": "Brief Analyst",
  "ppt-composer": "Deck Composer",
};

const allFiles = () => userEvent.click(screen.getByRole("tab", { name: /all files/i }));

beforeEach(() => {
  getRunSandbox.mockReset();
  getRunSandboxFile.mockReset();
  getRunSandboxFileBlob.mockReset();
  getRunSandboxZip.mockReset();
  downloadBlob.mockReset();
  getRunSandbox.mockResolvedValue(PPT_V2);
});

// ── Grouping — pure, and the reason nothing here knows what a workflow is ─────

describe("grouping", () => {
  it("puts root deliverables, .agents/ and the excluded root file in three groups", () => {
    const g = artifactGroups(PPT_V2.files);
    expect(g.map((x) => x.id)).toEqual(["deliverables", "agents", "notes"]);
    expect(g[0].files.map((x) => x.path)).toEqual(["presentation.pptx", "presentation.html"]);
    // PLANNER.md is `deliverable: false` from the server — never re-derived here.
    expect(g[2].files.map((x) => x.path)).toEqual(["PLANNER.md"]);
    // .verify/ is nested and not an agent output: Artifacts does not claim it.
    expect(g.flatMap((x) => x.files).some((x) => x.path.startsWith(".verify/"))).toBe(false);
  });

  it("renders no agent group for a run that wrote none", () => {
    // A different workflow entirely — three flat markdown files, no `.agents/`.
    const hello = [f("greeting.md", 1000), f("ask-hello.md", 400)];
    expect(artifactGroups(hello).map((x) => x.id)).toEqual(["deliverables"]);
  });

  it("groups All files by top-level directory, root first", () => {
    expect(allFileGroups(PPT_V2.files).map((x) => x.label)).toEqual([
      "Root",
      ".agents",
      ".verify",
    ]);
  });

  it("reads the agent id out of the engine's filename, loop identity included", () => {
    expect(agentIdFromPath(".agents/02-ppt-composer.md")).toBe("ppt-composer");
    expect(agentIdFromPath(".agents/07-code-writer-t3.md")).toBe("code-writer");
    expect(agentIdFromPath(".agents/07-code-writer-p2.md")).toBe("code-writer");
  });
});

// ── The tab ───────────────────────────────────────────────────────────────────

describe("CodeView theming", () => {
  it("carries NO literal colour — every one resolves through a token", () => {
    // The editor took its background from var(--surface-white) but its text
    // from a literal #20222B. In dark the surface flipped to #222 and the ink
    // did not, so a code block rendered as line numbers beside an empty column,
    // and an HTML block lost its property names while keeping its strings.
    // A hex here is that bug returning; the --code-* tokens carry both themes.
    const src = readFileSync(
      join(process.cwd(), "src/components/results/SandboxTab.tsx"),
      "utf8",
    );
    const theme = src.slice(
      src.indexOf("const highlight = language.HighlightStyle.define("),
      src.indexOf("const e = (lang || \"\").toLowerCase();"),
    );
    expect(theme.length).toBeGreaterThan(500); // the slice actually found it
    const literals = theme
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .flatMap((l) => l.match(/#[0-9A-Fa-f]{3,8}\b|rgba?\(/g) ?? []);
    expect(literals).toEqual([]);
  });
});

describe("fenceAgentPayloads", () => {
  it("fences <artifact> and a bare HTML document", () => {
    const out = fenceAgentPayloads(
      'a\n\n<artifact type="text/html"><!DOCTYPE html><html></html></artifact>',
    );
    expect(out).toContain("```html");
    expect(out).not.toContain("<artifact");
  });

  it("fences an unmarked line long enough to be pasted source", () => {
    // conversation_history holds 29–32k-character lines that cost micromark
    // ~300ms EACH to tokenise inline. Nobody writes prose that long on a line,
    // and the length is the only signal — there is no tag to match.
    const long = "x".repeat(5000);
    expect(fenceAgentPayloads(`intro\n${long}\nouttro`)).toBe(
      "intro\n```\n" + long + "\n```\nouttro",
    );
  });

  it("leaves ordinary markdown alone", () => {
    const md = "# Title\n\nA paragraph.\n\n```js\nconst a = 1;\n```\n";
    expect(fenceAgentPayloads(md)).toBe(md);
  });

  it("a markdown <spec> body is UNWRAPPED, not fenced (renders as markdown)", () => {
    // The spec writer's <spec> carries a markdown DOCUMENT; the brief analyst's
    // carries JSON. Fencing on the tag NAME turned the first into raw source —
    // which is why 01-prototype-specify.md showed `#` and `|` as literal text
    // while 02-…-plan.md (<tasks>) and 03-…-analyze.md (<analysis>) rendered,
    // purely because those two names were absent from the alternation.
    const out = fenceAgentPayloads("<spec>\n# Title\n\n| a | b |\n</spec>");
    expect(out).not.toContain("```");
    expect(out).not.toContain("<spec>");
    expect(out).toContain("# Title");
  });

  it("unwraps ALL THREE prose wrappers, whatever the body looks like", () => {
    // spec/tasks/analysis are transport markers naming the STEP, not the
    // content — all three carry a markdown document. No branch on the body:
    // a `{`-leading payload is unwrapped the same as a `#`-leading one.
    for (const tag of ["spec", "tasks", "analysis"]) {
      const md = fenceAgentPayloads(`<${tag}>\n## Report\n\n| a | b |\n</${tag}>`);
      expect(md).not.toContain("```");
      expect(md).not.toContain(`<${tag}>`);
      expect(md).toContain("## Report");

      const json = fenceAgentPayloads(`<${tag}> {"x":1} </${tag}>`);
      expect(json).not.toContain("```");
      expect(json).toContain('{"x":1}');
    }
  });

  it("unwraps a fence whose WHOLE body is a prose wrapper (the agent fenced its own markdown)", () => {
    // The task planner writes `# Task Planner Agent`, then opens a bare ``` and
    // puts <tasks>…</tasks> inside it — so its markdown arrived as a code block
    // with `<tasks>` sitting on line 1 of the editor.
    const md = "# Task Planner Agent\n\n```\n<tasks>\n## Task 1\n**Goal**: ship\n</tasks>\n```";
    const out = fenceAgentPayloads(md);
    expect(out).not.toContain("```");
    expect(out).not.toContain("<tasks>");
    expect(out).toContain("## Task 1");
    expect(out).toContain("# Task Planner Agent");
  });

  it("leaves a fence that NAMES a language alone, even around a wrapper", () => {
    // ```js is a deliberate claim about the content. Only a BARE fence whose
    // entire body is a wrapper is treated as an agent fencing its own prose.
    const md = "```js\n<tasks>\nconst a = 1;\n</tasks>\n```";
    expect(fenceAgentPayloads(md)).toBe(md);
  });

  it("leaves a fence with anything outside the wrapper alone", () => {
    const md = "```\nnote\n<tasks>\n## T\n</tasks>\n```";
    expect(fenceAgentPayloads(md)).toBe(md);
  });

  it("emits an unterminated fence verbatim rather than swallowing it", () => {
    const md = "intro\n```\nstill open";
    expect(fenceAgentPayloads(md)).toContain("still open");
  });

  it("never reaches inside an existing fence", () => {
    const md = '```\n<artifact><!DOCTYPE html></artifact>\n```';
    expect(fenceAgentPayloads(md)).toBe(md);
  });
});

describe("SandboxTab", () => {
  it("opens on Artifacts and counts the deliverables in the header", async () => {
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("presentation.pptx")).toBeInTheDocument());

    expect(screen.getByText("2 deliverables · 8 files")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /artifacts/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // Nested working files are not in this pane.
    expect(screen.queryByText("report.txt")).toBeNull();
  });

  it("names an agent output by its agent and stamps the spine initials", async () => {
    render(<SandboxTab runId="run-1" agentNameById={AGENT_NAMES} />);
    await waitFor(() => expect(screen.getByText("02-ppt-composer.md")).toBeInTheDocument());

    expect(screen.getByText("Deck Composer")).toBeInTheDocument();
    expect(screen.getByText("DC")).toBeInTheDocument();
  });

  it("falls back to the id when the run's agent names are gone", async () => {
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("Ppt Composer")).toBeInTheDocument());
    expect(screen.getByText("PC")).toBeInTheDocument();
  });

  it("shows every group under All files, with sort and bulk collapse", async () => {
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("presentation.pptx")).toBeInTheDocument());

    // The topbar belongs to All files only — Artifacts is a curated order.
    expect(screen.queryByRole("button", { name: /collapse all/i })).toBeNull();
    await allFiles();

    // Directory headers keep their on-disk casing — `.verify`, not `.VERIFY`.
    expect(screen.getByText(".verify")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /name/i })).toBeInTheDocument();

    // …and the pane opens COLLAPSED: the set of directories first, not 8 rows.
    expect(screen.queryByText("report.txt")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /expand all/i }));
    expect(screen.getByText("report.txt")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /collapse all/i }));
    expect(screen.queryByText("report.txt")).toBeNull();
  });

  it("leaves group expansion alone when a file is opened", async () => {
    // Expansion is the user's. A group that folds itself away under the click
    // that opened a file makes the list impossible to navigate twice the same
    // way — you lose your place every time you read something.
    getRunSandboxFile.mockResolvedValue("# the plan");
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("PLANNER.md")).toBeInTheDocument());

    await userEvent.click(screen.getByText("PLANNER.md"));

    expect(screen.getByText("02-ppt-composer.md")).toBeInTheDocument();
    for (const label of [/deliverables/i, /agent outputs/i, /run notes/i])
      expect(screen.getByRole("button", { name: label })).toHaveAttribute(
        "aria-expanded",
        "true",
      );

    // …and a group the user collapsed STAYS collapsed across an open.
    await userEvent.click(screen.getByRole("button", { name: /agent outputs/i }));
    expect(screen.queryByText("02-ppt-composer.md")).toBeNull();
    await userEvent.click(screen.getByText("presentation.html"));
    expect(screen.queryByText("02-ppt-composer.md")).toBeNull();
  });

  it("fetches a file's bytes only when it is opened, and never again on a toggle", async () => {
    getRunSandboxFile.mockResolvedValue("# the plan");
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("PLANNER.md")).toBeInTheDocument());
    expect(getRunSandboxFile).not.toHaveBeenCalled();

    await userEvent.click(screen.getByText("PLANNER.md"));
    // Markdown opens RENDERED, so the heading is an <h1> and the `#` is gone.
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "the plan" })).toBeInTheDocument(),
    );
    expect(getRunSandboxFile).toHaveBeenCalledWith("test-token", "run-1", "PLANNER.md");

    await userEvent.click(screen.getByRole("button", { name: /code/i }));
    expect(screen.getByText("# the plan")).toBeInTheDocument();
    expect(getRunSandboxFile).toHaveBeenCalledTimes(1);
  });

  it("shows HTML as source first, with a Preview that sandboxes it", async () => {
    getRunSandboxFile.mockResolvedValue(
      "<!DOCTYPE html><html><body><h1>Deck</h1></body></html>",
    );
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("presentation.html")).toBeInTheDocument());
    await userEvent.click(screen.getByText("presentation.html"));

    await waitFor(() => expect(screen.getByText(/<h1>Deck<\/h1>/)).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /preview/i }));
    const frame = screen.getByTitle("presentation.html");
    // allow-scripts WITHOUT allow-same-origin: an opaque origin that cannot
    // reach this document. Adding allow-same-origin here is stored XSS.
    expect(frame).toHaveAttribute("sandbox", "allow-scripts");
    expect(frame.getAttribute("srcdoc")).toContain("<h1>Deck</h1>");
  });

  it("renders a source file as code, gutter and all, with no Preview toggle", async () => {
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("build.js", 40, { deliverable: false })],
    });
    getRunSandboxFile.mockResolvedValue("const a = 1;\nconst b = 2;\nconst c = 3;");
    render(<SandboxTab runId="run-1" />);
    // A root file — it lands in Run notes, no pane switching needed.
    await waitFor(() => expect(screen.getByText("build.js")).toBeInTheDocument());
    await userEvent.click(screen.getByText("build.js"));

    // CodeMirror is lazily imported; until it resolves the same bytes are in a
    // <pre>. Either way the file's text is on screen and never wrapped away.
    await waitFor(() =>
      expect(document.body.textContent).toContain("const b = 2;"),
    );
    // A real editor mounts, with a line gutter — a long file has to be
    // navigable by line the way an error message names one.
    await waitFor(() => expect(document.querySelector(".cm-editor")).toBeTruthy());
    expect(document.querySelector(".cm-lineNumbers")).toBeTruthy();
    // Code has one presentation; a Preview/Code toggle would be a no-op control.
    expect(screen.queryByRole("button", { name: /^preview$/i })).toBeNull();
  });

  it("opens Find and Replace on the code view, and can actually replace", async () => {
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("build.js", 40, { deliverable: false })],
    });
    getRunSandboxFile.mockResolvedValue("const a = 1;\nconst b = 2;");
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("build.js")).toBeInTheDocument());
    await userEvent.click(screen.getByText("build.js"));
    await waitFor(() => expect(document.querySelector(".cm-editor")).toBeTruthy());

    // The bar is NOT permanent chrome — it costs a row of the viewer and most
    // reads never search.
    expect(document.querySelector(".cm-search")).toBeNull();

    const content = document.querySelector(".cm-content") as HTMLElement;
    content.focus();
    // Mod-f is Cmd on a Mac and Ctrl elsewhere; fire both so the test does not
    // depend on what platform jsdom claims to be.
    await userEvent.keyboard("{Control>}f{/Control}");
    if (!document.querySelector(".cm-search")) await userEvent.keyboard("{Meta>}f{/Meta}");

    const panel = document.querySelector(".cm-search");
    expect(panel).toBeTruthy();
    // Replace, not just Find — a read-only editor would render a dead control.
    expect(panel!.querySelector("[name=replace]")).toBeTruthy();
    expect(document.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe(
      "true",
    );

    // …and Escape gives the row back.
    await userEvent.keyboard("{Escape}");
    expect(document.querySelector(".cm-search")).toBeNull();
  });

  it("fences an agent's <artifact> document into a code block", async () => {
    // A whole pasted document is the case that NEEDS the fence: react-markdown
    // runs WITHOUT rehype-raw (a security invariant), so unfenced it is escaped
    // tag by tag and reflowed into one unreadable paragraph.
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("qa.md", 52_000, { deliverable: false })],
    });
    getRunSandboxFile.mockResolvedValue(
      '# Deck QA Agent\n\nHere it is:\n\n<artifact type="text/html"><!DOCTYPE html>\n<html><body>deck</body></html></artifact>',
    );
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("qa.md")).toBeInTheDocument());
    await userEvent.click(screen.getByText("qa.md"));

    // md is still md…
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Deck QA Agent" })).toBeInTheDocument(),
    );
    // …and the document landed in the editor, not in a paragraph.
    await waitFor(() => expect(document.querySelector(".cm-editor")).toBeTruthy());
  });

  it("renders a <spec> agent output AS MARKDOWN — the tag names the step, not the type", async () => {
    // Regression: spec was fenced on its tag name, so 01-prototype-specify.md
    // showed its headings and table pipes as literal characters while the
    // <tasks>/<analysis> siblings rendered, purely because those names were not
    // on the list. All three are markdown documents; none of them is code.
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("01-prototype-specify.md", 17_000, { deliverable: false })],
    });
    getRunSandboxFile.mockResolvedValue(
      "# Spec Writer Agent\n\n<spec>\n## Overview\n\n| Section | Rows |\n|---|---|\n| Profile | 4 |\n</spec>",
    );
    render(<SandboxTab runId="run-1" />);
    await waitFor(() =>
      expect(screen.getByText("01-prototype-specify.md")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByText("01-prototype-specify.md"));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument(),
    );
    // A real table, not pipes in a code block — and no editor at all.
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(document.querySelector(".cm-editor")).toBeNull();
    expect(document.body.textContent).not.toContain("<spec>");
  });

  it("renders an image and a PDF instead of offering only a download", async () => {
    getRunSandboxFileBlob.mockResolvedValue(new Blob(["x"], { type: "image/png" }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock-url");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("presentation.pptx")).toBeInTheDocument());
    await allFiles();
    await userEvent.click(screen.getByRole("button", { name: /expand all/i }));
    await userEvent.click(screen.getByText("slide-01.png"));

    const img = await screen.findByAltText(".verify/slide-01.png");
    expect(img).toHaveAttribute("src", "blob:mock-url");
    expect(getRunSandboxFileBlob).toHaveBeenCalledWith(
      "test-token",
      "run-1",
      ".verify/slide-01.png",
    );
    expect(getRunSandboxFile).not.toHaveBeenCalled();
    expect(screen.queryByText(/binary file/i)).toBeNull();

    await userEvent.click(screen.getByText("presentation.pdf"));
    await waitFor(() =>
      expect(screen.getByTitle(".verify/presentation.pdf")).toBeInTheDocument(),
    );
  });

  it("says a zero-byte file is empty rather than showing a blank editor", async () => {
    // An empty editor is indistinguishable from a failed load.
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("empty.txt", 0)],
    });
    getRunSandboxFile.mockResolvedValue("");
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("empty.txt")).toBeInTheDocument());
    await userEvent.click(screen.getByText("empty.txt"));

    await waitFor(() => expect(screen.getByText(/this file is empty/i)).toBeInTheDocument());
  });

  it("offers a download for a binary file instead of reading it", async () => {
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("presentation.pptx")).toBeInTheDocument());
    await userEvent.click(screen.getByText("presentation.pptx"));

    expect(getRunSandboxFile).not.toHaveBeenCalled();
    expect(screen.getByText(/binary file/i)).toBeInTheDocument();

    // Not a link: a navigation to the endpoint carries no Authorization header
    // (the token lives in JS, not a cookie), so it downloads the API's
    // {"detail":"Not authenticated"} body instead of the file — BUG-031.
    expect(screen.queryByRole("link", { name: /download/i })).toBeNull();

    getRunSandboxFileBlob.mockResolvedValue(new Blob(["x"]));
    // Exact: the rail header carries a "Download all" button too.
    await userEvent.click(screen.getByRole("button", { name: "Download" }));

    expect(getRunSandboxFileBlob).toHaveBeenCalledWith(
      "test-token",
      "run-1",
      "presentation.pptx",
    );
    await waitFor(() => expect(downloadBlob).toHaveBeenCalled());
    expect(downloadBlob.mock.calls[0][1]).toBe("presentation.pptx");
  });

  it("keeps a nested file's path relative to its group, not just the basename", async () => {
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("src/app/page.tsx", 6000), f("src/lib/page.tsx", 4000)],
    });
    render(<SandboxTab runId="run-1" />);
    // Nothing is at the root, so Artifacts has no groups — it must say where
    // the files went instead of rendering a blank column.
    await waitFor(() =>
      expect(screen.getByText(/wrote nothing at the top level/i)).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: /see all 2 files/i }));
    await userEvent.click(screen.getByRole("button", { name: /expand all/i }));

    // Two files named page.tsx — a bare basename would render them identically.
    const rail = screen.getByText("src").closest("div")!;
    expect(within(rail).getByText("app/page.tsx")).toBeInTheDocument();
    expect(within(rail).getByText("lib/page.tsx")).toBeInTheDocument();
  });

  it("downloads the whole workspace as one zip", async () => {
    // One archive, not 36 sequential downloads — a browser blocks those after
    // a handful, which is what the Files tab's Download All does.
    getRunSandboxZip.mockResolvedValue(new Blob(["PK"], { type: "application/zip" }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:zip");
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("presentation.pptx")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /download all/i }));

    expect(getRunSandboxZip).toHaveBeenCalledWith("test-token", "run-1");
    await waitFor(() => expect(downloadBlob).toHaveBeenCalled());
    expect(downloadBlob.mock.calls[0][1]).toBe("workspace-run-1.zip");
  });

  it("surfaces a refused archive instead of failing silently", async () => {
    getRunSandboxZip.mockRejectedValue(new Error("This workspace is too large to archive"));
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("presentation.pptx")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /download all/i }));
    await waitFor(() =>
      expect(screen.getByText(/too large to archive/i)).toBeInTheDocument(),
    );
  });

  it("says the workspace expired rather than showing an empty tree", async () => {
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: true,
      truncated: false,
      files: [],
    });
    render(<SandboxTab runId="run-1" />);

    await waitFor(() => expect(screen.getByText(/workspace expired/i)).toBeInTheDocument());
    expect(screen.queryByText(/wrote no files/i)).not.toBeInTheDocument();
  });

  it("distinguishes a run that genuinely wrote nothing", async () => {
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [],
    });
    render(<SandboxTab runId="run-1" />);

    await waitFor(() => expect(screen.getByText(/wrote no files/i)).toBeInTheDocument());
    expect(screen.queryByText(/workspace expired/i)).not.toBeInTheDocument();
  });

  it("does not fetch at all without a run id", () => {
    render(<SandboxTab runId={null} />);
    expect(getRunSandbox).not.toHaveBeenCalled();
    expect(screen.getByText(/once a run has started/i)).toBeInTheDocument();
  });
});
