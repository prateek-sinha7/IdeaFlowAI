import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MarkdownPreview } from "./MarkdownPreview";

// Boundary: the browser clipboard. `userEvent.setup()` installs a stub
// `navigator.clipboard`; each test spies on its `writeText`.
function setup(ui: React.ReactElement) {
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText");
  return { user, writeText, ...render(ui) };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MarkdownPreview — empty state", () => {
  it.each([
    ["undefined", undefined],
    ["an empty string", ""],
  ])("shows the 'No Output Yet' placeholder when content is %s", (_label, content) => {
    render(<MarkdownPreview content={content} />);

    expect(screen.getByText("No Output Yet")).toBeInTheDocument();
    expect(screen.getByText("Run the pipeline to generate output")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy All/i })).not.toBeInTheDocument();
  });
});

describe("MarkdownPreview — markdown rendering", () => {
  it("renders headings, paragraphs and emphasis as semantic elements", () => {
    render(
      <MarkdownPreview
        content={"# Top\n\n## Second\n\n### Third\n\nPlain **bold** and *italic* text.\n"}
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Top" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Second" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Third" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
  });

  it("renders unordered and ordered lists with their items", () => {
    render(<MarkdownPreview content={"- apple\n- banana\n\n1. first\n2. second\n"} />);

    const lists = screen.getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(within(lists[0]).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "apple",
      "banana",
    ]);
    expect(within(lists[1]).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "first",
      "second",
    ]);
  });

  it("renders GFM tables with header and body cells", () => {
    render(<MarkdownPreview content={"| Name | Age |\n| --- | --- |\n| Ann | 30 |\n"} />);

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Name",
      "Age",
    ]);
    expect(within(table).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Ann", "30"]);
  });

  it("renders blockquotes and horizontal rules", () => {
    const { container } = render(<MarkdownPreview content={"> quoted line\n\n---\n\nafter"} />);

    expect(container.querySelector("blockquote")).toHaveTextContent("quoted line");
    expect(screen.getByRole("separator")).toBeInTheDocument();
  });

  it("renders inline code without a code-block header or copy control", () => {
    render(<MarkdownPreview content={"Use `npm test` today."} />);

    expect(screen.getByText("npm test").tagName).toBe("CODE");
    expect(screen.queryByRole("button", { name: /^Copy$/ })).not.toBeInTheDocument();
  });

  it("opens links in a new tab with noopener noreferrer", () => {
    render(<MarkdownPreview content={"[docs](https://example.com/docs)"} />);

    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("href", "https://example.com/docs");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});

describe("MarkdownPreview — h1 section toggle", () => {
  it("swaps the chevron when the h1 toggle is clicked and swaps it back on a second click", async () => {
    const { user, container } = setup(<MarkdownPreview content={"# Section\n\nbody"} />);

    expect(container.querySelector("svg.lucide-chevron-down")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Section" }));
    expect(container.querySelector("svg.lucide-chevron-right")).toBeInTheDocument();
    expect(container.querySelector("svg.lucide-chevron-down")).not.toBeInTheDocument();

    // Re-query: the h1 renderer is re-created each render, so the old node is replaced.
    await user.click(screen.getByRole("button", { name: "Section" }));
    expect(container.querySelector("svg.lucide-chevron-down")).toBeInTheDocument();
  });
});

describe("MarkdownPreview — code blocks", () => {
  it("labels a fenced block with its language and shows the code", () => {
    render(<MarkdownPreview content={"```ts\nconst x = 1;\n```\n"} />);

    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("const x = 1;")).toBeInTheDocument();
  });

  it("labels a filename-style fence with a file marker", () => {
    render(<MarkdownPreview content={"```src/app.ts\nexport {};\n```\n"} />);

    expect(screen.getByText("📄 src/app.ts")).toBeInTheDocument();
  });

  it("falls back to the 'code' label for a multi-line fence without a language", () => {
    render(<MarkdownPreview content={"```\nline one\nline two\n```\n"} />);

    expect(screen.getByText("code")).toBeInTheDocument();
  });

  it("copies the block's code and confirms with 'Copied'", async () => {
    const { user, writeText } = setup(<MarkdownPreview content={"```ts\nconst x = 1;\n```\n"} />);

    await user.click(screen.getByRole("button", { name: /^Copy$/ }));

    expect(writeText).toHaveBeenCalledWith("const x = 1;");
    expect(await screen.findByRole("button", { name: /Copied/ })).toBeInTheDocument();
  });

  it("reports 'Copy failed' on the block button when the clipboard write rejects", async () => {
    const { user, writeText } = setup(<MarkdownPreview content={"```ts\nconst x = 1;\n```\n"} />);
    writeText.mockRejectedValueOnce(new DOMException("denied"));

    await user.click(screen.getByRole("button", { name: /^Copy$/ }));

    expect(await screen.findByRole("button", { name: /Copy failed/ })).toBeInTheDocument();
  });
});

describe("MarkdownPreview — Copy All", () => {
  it("copies the full markdown source and confirms with 'Copied!'", async () => {
    const content = "# Title\n\nbody text";
    const { user, writeText } = setup(<MarkdownPreview content={content} />);

    await user.click(screen.getByRole("button", { name: /Copy All/i }));

    expect(writeText).toHaveBeenCalledWith(content);
    expect(await screen.findByText("Copied!")).toBeInTheDocument();
  });

  it("reports 'Copy failed' when the clipboard write rejects", async () => {
    const { user, writeText } = setup(<MarkdownPreview content={"# Title"} />);
    writeText.mockRejectedValueOnce(new DOMException("denied"));

    await user.click(screen.getByRole("button", { name: /Copy All/i }));

    expect(await screen.findByText("Copy failed")).toBeInTheDocument();
    expect(screen.queryByText("Copied!")).not.toBeInTheDocument();
  });
});

describe("MarkdownPreview — revision bar", () => {
  it("does not render the revision bar when onRevise is not provided", () => {
    render(<MarkdownPreview content={"# Title"} />);

    expect(screen.queryByLabelText("Revision instructions")).not.toBeInTheDocument();
  });

  it("disables Revise until the input has non-whitespace text", async () => {
    const { user } = setup(<MarkdownPreview content={"# Title"} onRevise={vi.fn()} />);
    const input = screen.getByLabelText("Revision instructions");
    const revise = screen.getByRole("button", { name: /Revise/ });

    expect(revise).toBeDisabled();
    await user.type(input, "   ");
    expect(revise).toBeDisabled();
    await user.type(input, "x");
    expect(revise).toBeEnabled();
  });

  it("submits the trimmed instruction on Revise click and clears the input", async () => {
    const onRevise = vi.fn();
    const { user } = setup(<MarkdownPreview content={"# Title"} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  add a section  ");
    await user.click(screen.getByRole("button", { name: /Revise/ }));

    expect(onRevise).toHaveBeenCalledTimes(1);
    expect(onRevise).toHaveBeenCalledWith("add a section");
    expect(input).toHaveValue("");
  });

  it("submits the instruction when Enter is pressed", async () => {
    const onRevise = vi.fn();
    const { user } = setup(<MarkdownPreview content={"# Title"} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "tighten wording{Enter}");

    expect(onRevise).toHaveBeenCalledWith("tighten wording");
    expect(input).toHaveValue("");
  });

  it("ignores Enter when the input is blank", async () => {
    const onRevise = vi.fn();
    const { user } = setup(<MarkdownPreview content={"# Title"} onRevise={onRevise} />);

    await user.type(screen.getByLabelText("Revision instructions"), "   {Enter}");

    expect(onRevise).not.toHaveBeenCalled();
  });
});

describe("MarkdownPreview — unsafe content is rendered safely", () => {
  let originalPwned: unknown;

  beforeEach(() => {
    originalPwned = (window as unknown as Record<string, unknown>).__pwned;
    delete (window as unknown as Record<string, unknown>).__pwned;
  });

  afterEach(() => {
    (window as unknown as Record<string, unknown>).__pwned = originalPwned;
  });

  it("never creates a live <script> element and never executes the payload", () => {
    const { container } = render(
      <MarkdownPreview content={"# Title\n\n<script>window.__pwned = true;</script>\n"} />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect((window as unknown as Record<string, unknown>).__pwned).toBeUndefined();
  });

  it("neutralises a javascript: link target", () => {
    render(<MarkdownPreview content={"[click me](javascript:alert(1))"} />);

    const link = screen.queryByRole("link", { name: "click me" });
    // Either the anchor is dropped or its href no longer carries the scheme.
    const href = link?.getAttribute("href") ?? "";
    expect(href.toLowerCase()).not.toContain("javascript:");
  });

  it("neutralises a mixed-case javascript: link target", () => {
    render(<MarkdownPreview content={"[click me](JaVaScRiPt:alert(1))"} />);

    const href = screen.queryByRole("link", { name: "click me" })?.getAttribute("href") ?? "";
    expect(href.toLowerCase()).not.toContain("javascript:");
  });

  it("does not create a live element for an inline event-handler payload", () => {
    const { container } = render(
      <MarkdownPreview content={'<img src=x onerror="window.__pwned=true"> and <a href="javascript:alert(1)">x</a>'} />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect(container.querySelector('a[href^="javascript:" i]')).toBeNull();
  });
});
