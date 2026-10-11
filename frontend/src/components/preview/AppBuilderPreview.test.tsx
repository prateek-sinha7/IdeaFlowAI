import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";

function file(path: string, content = `// ${path}`, language = "typescript"): ParsedFile {
  const name = path.split("/").pop() as string;
  const ext = name.includes(".") ? (name.split(".").pop() as string) : "";
  return { path, name, ext, content, language };
}

const FILES: ParsedFile[] = [
  file("README.md", "# Readme\nline two", "markdown"),
  file("src/app.ts", "export const app = 1;"),
  file("src/lib/util.ts", "export const util = 2;"),
];

type HljsStub = NonNullable<Window["hljs"]>;
const w = window as unknown as Record<string, unknown>;

// ─── highlight.js loader (module-level state) ────────────────────────────────
// AppBuilderPreview keeps highlight.js load state at module scope, shared by every
// test in this file. This describe MUST stay first: it drives the one-time CDN
// load (intercepted at the document.head.appendChild boundary) and later tests run
// against the already-loaded state.
describe("AppBuilderPreview — highlight.js loading", () => {
  afterEach(() => {
    delete w.hljs;
    vi.restoreAllMocks();
  });

  it("shows escaped plain code until highlight.js loads, then highlights it", async () => {
    let onScriptLoad: (() => void) | null = null;
    const realAppend = document.head.appendChild.bind(document.head);
    const appendSpy = vi.spyOn(document.head, "appendChild").mockImplementation(<T extends Node>(node: T): T => {
      if (node instanceof HTMLScriptElement) {
        onScriptLoad = node.onload as unknown as () => void;
        return node;
      }
      return realAppend(node);
    });
    const { container } = render(
      <AppBuilderPreview files={[file("a.js", "if (a < b) { run(); }", "javascript")]} />,
    );

    // Before load: code is HTML-escaped plain text.
    await waitFor(() => expect(container.querySelector("pre")?.innerHTML).toContain("a &lt; b"));
    expect(appendSpy).toHaveBeenCalledTimes(2); // stylesheet + script
    expect(onScriptLoad).not.toBeNull();

    w.hljs = {
      getLanguage: (lang: string) => lang === "javascript",
      highlight: (code: string) => ({ value: `<span class="hljs-kw">${code}</span>` }),
      highlightAuto: (code: string) => ({ value: `<span class="hljs-auto">${code}</span>` }),
    } satisfies HljsStub;
    act(() => {
      onScriptLoad!();
    });

    await waitFor(() => expect(container.querySelector(".hljs-kw")).toBeInTheDocument());
  });

  it("uses highlightAuto for an unsupported language", async () => {
    w.hljs = {
      getLanguage: () => undefined,
      highlight: () => ({ value: "never" }),
      highlightAuto: (code: string) => ({ value: `<span class="hljs-auto">${code}</span>` }),
    } satisfies HljsStub;
    const { container } = render(<AppBuilderPreview files={[file("a.xyz", "data", "unknown")]} />);

    await waitFor(() => expect(container.querySelector(".hljs-auto")).toBeInTheDocument());
  });

  it("falls back to escaped text when highlight.js throws", async () => {
    w.hljs = {
      getLanguage: () => true,
      highlight: () => {
        throw new Error("boom");
      },
      highlightAuto: () => ({ value: "" }),
    } satisfies HljsStub;
    const { container } = render(<AppBuilderPreview files={[file("a.ts", "x < y")]} />);

    await waitFor(() => expect(container.querySelector("pre")?.innerHTML).toContain("x &lt; y"));
  });

  it("escapes HTML in a file's content when no highlighter is present", async () => {
    const payload = '<script>window.__pwned = true;</script><a href="javascript:alert(1)">x</a>';
    const { container } = render(<AppBuilderPreview files={[file("evil.html", payload, "html")]} />);

    await waitFor(() => expect(container.querySelector("pre")?.textContent).toBe(payload));
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("pre a")).toBeNull();
    expect(w.__pwned).toBeUndefined();
  });
});

describe("AppBuilderPreview — empty state", () => {
  it("shows the 'No files generated yet' placeholder when there are no files", () => {
    render(<AppBuilderPreview files={[]} />);

    expect(screen.getByText("No files generated yet")).toBeInTheDocument();
    expect(screen.queryByLabelText("Search files")).not.toBeInTheDocument();
  });

  it("populates the explorer and selects the first file when files arrive after an empty render", async () => {
    const { rerender } = render(<AppBuilderPreview files={[]} />);

    rerender(<AppBuilderPreview files={FILES} />);

    expect(await screen.findByText("3 files")).toBeInTheDocument();
    expect(screen.getByText("README.md", { selector: "span.font-mono" })).toBeInTheDocument();
  });
});

describe("AppBuilderPreview — layout and file viewer", () => {
  it("shows the project name (default and custom) and the file count", () => {
    const { rerender } = render(<AppBuilderPreview files={FILES} />);
    expect(screen.getByText("Project")).toBeInTheDocument();
    expect(screen.getByText("3 files")).toBeInTheDocument();

    rerender(<AppBuilderPreview files={FILES} projectName="Shop" />);
    expect(screen.getByText("Shop")).toBeInTheDocument();
  });

  it("opens the first file in the viewer with its path, extension badge and line count", () => {
    render(<AppBuilderPreview files={FILES} />);

    expect(screen.getByText("README.md", { selector: "span.font-mono" })).toBeInTheDocument();
    expect(screen.getByText("md")).toBeInTheDocument();
    expect(screen.getByText("2 lines")).toBeInTheDocument();
  });

  it("falls back to a 'txt' badge for a file without an extension", () => {
    render(<AppBuilderPreview files={[file("Makefile", "all:")]} />);

    expect(screen.getByText("txt")).toBeInTheDocument();
  });

  it("opens a clicked file in a new tab and shows its content", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: "app.ts" }));

    expect(screen.getByText("src/app.ts", { selector: "span.font-mono" })).toBeInTheDocument();
    expect(screen.getByText("1 lines")).toBeInTheDocument();
  });

  it("does not duplicate a tab when an already-open file is selected again", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: "app.ts" }));
    // Second click goes through the explorer row (first in DOM order), not the new tab.
    await user.click(screen.getAllByRole("button", { name: "app.ts" })[0]);

    // One explorer row + one tab.
    expect(screen.getAllByRole("button", { name: "app.ts" })).toHaveLength(2);
  });

  it("collapses and re-expands a folder from the explorer", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);
    expect(screen.getByRole("button", { name: "app.ts" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "src" }));
    expect(screen.queryByRole("button", { name: "app.ts" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "src" }));
    expect(screen.getByRole("button", { name: "app.ts" })).toBeInTheDocument();
  });

  it("downloads the active file under its own name with its content", async () => {
    const user = userEvent.setup();
    const created = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:file");
    const revoked = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: "Download" }));

    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe("README.md");
    expect(clicked[0].href).toContain("blob:file");
    expect(await (created.mock.calls[0][0] as Blob).text()).toBe("# Readme\nline two");
    expect(revoked).toHaveBeenCalledWith("blob:file");
  });

  it("copies the active file's content and confirms with 'Copied'", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: "Copy" }));

    expect(writeText).toHaveBeenCalledWith("# Readme\nline two");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});

describe("AppBuilderPreview — tabs", () => {
  async function openThreeTabs() {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);
    await user.click(screen.getByRole("button", { name: "app.ts" }));
    await user.click(screen.getByRole("button", { name: "lib" })); // nested folders start collapsed
    await user.click(screen.getByRole("button", { name: "util.ts" }));
    return user;
  }

  // The close affordance is an icon-only <span> (no role, no name): the last span
  // inside the tab button. See report: a11y finding.
  function closeControl(tabName: string): HTMLElement {
    const tab = screen.getAllByRole("button", { name: tabName }).find((b) => b.className.includes("border-r"));
    return tab!.lastElementChild as HTMLElement;
  }

  it("switches the viewer when an inactive tab is clicked", async () => {
    const user = await openThreeTabs();

    const readmeTab = screen.getAllByRole("button", { name: "README.md" }).find((b) => b.className.includes("border-r"))!;
    await user.click(readmeTab);

    expect(screen.getByText("README.md", { selector: "span.font-mono" })).toBeInTheDocument();
  });

  it("activates the neighbouring tab when the active tab is closed", async () => {
    const user = await openThreeTabs();

    await user.click(closeControl("util.ts"));

    expect(screen.getByText("src/app.ts", { selector: "span.font-mono" })).toBeInTheDocument();
  });

  it("keeps the active tab when a different tab is closed", async () => {
    const user = await openThreeTabs();

    await user.click(closeControl("app.ts"));

    expect(screen.getByText("src/lib/util.ts", { selector: "span.font-mono" })).toBeInTheDocument();
  });

  it("shows the empty viewer once the last open tab is closed", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);

    await user.click(closeControl("README.md"));

    expect(screen.getByText("Select a file to view its contents")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy" })).not.toBeInTheDocument();
  });
});

describe("AppBuilderPreview — explorer expand/collapse all", () => {
  it("labels the toggle 'Collapse all' while folders are open", () => {
    render(<AppBuilderPreview files={FILES} />);

    expect(screen.getByRole("button", { name: "Collapse all" })).toBeInTheDocument();
  });

  // SUSPECTED BUG (see report): on first use 'Collapse all' compares the open set
  // (top-level only) with the set of ALL folders; they differ, so it EXPANDS every
  // nested folder instead of collapsing. it.fails is the repo's xfail idiom.
  it.fails("collapses every folder on the first 'Collapse all' click", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: "Collapse all" }));

    expect(screen.queryByRole("button", { name: "app.ts" })).not.toBeInTheDocument();
  });

  it("collapses everything on the second click and offers 'Expand all'", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: "Collapse all" }));
    await user.click(screen.getByRole("button", { name: "Collapse all" }));

    expect(screen.queryByRole("button", { name: "app.ts" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand all" })).toBeInTheDocument();
  });

  it("expands every nested folder from 'Expand all'", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} />);
    await user.click(screen.getByRole("button", { name: "Collapse all" }));
    await user.click(screen.getByRole("button", { name: "Collapse all" }));

    await user.click(screen.getByRole("button", { name: "Expand all" }));

    expect(screen.getByRole("button", { name: "util.ts" })).toBeInTheDocument();
  });
});

describe("AppBuilderPreview — sidebar resize", () => {
  function sidebarOf() {
    return screen.getByLabelText("Search files").closest("div[style]") as HTMLElement;
  }

  // The drag handle is a bare <div> (no role). fireEvent is needed because the
  // drag is driven by window-level mousemove/mouseup events.
  function dragHandle(container: HTMLElement) {
    return container.querySelector(".cursor-col-resize") as HTMLElement;
  }

  it("resizes the sidebar while dragging, clamped between 160px and 380px", () => {
    const { container } = render(<AppBuilderPreview files={FILES} />);
    expect(sidebarOf().style.width).toBe("220px");

    fireEvent.mouseDown(dragHandle(container), { clientX: 220 });
    fireEvent.mouseMove(window, { clientX: 300 });
    expect(sidebarOf().style.width).toBe("300px");

    fireEvent.mouseMove(window, { clientX: 10 });
    expect(sidebarOf().style.width).toBe("160px");

    fireEvent.mouseMove(window, { clientX: 5000 });
    expect(sidebarOf().style.width).toBe("380px");
  });

  it("stops resizing after the mouse button is released", () => {
    const { container } = render(<AppBuilderPreview files={FILES} />);

    fireEvent.mouseDown(dragHandle(container), { clientX: 220 });
    fireEvent.mouseMove(window, { clientX: 300 });
    fireEvent.mouseUp(window);
    fireEvent.mouseMove(window, { clientX: 350 });

    expect(sidebarOf().style.width).toBe("300px");
  });
});

describe("AppBuilderPreview — full screen", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("stores the files in sessionStorage and opens the full-screen route", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    render(<AppBuilderPreview files={FILES} projectName="Shop" />);

    await user.click(screen.getByRole("button", { name: /Full Screen/ }));

    expect(open).toHaveBeenCalledWith("/preview-fullscreen", "_blank");
    expect(JSON.parse(sessionStorage.getItem("__app_preview__") as string)).toEqual({
      files: FILES,
      projectName: "Shop",
    });
  });

  it("opens the full-screen route with a quota flag when sessionStorage rejects the write", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: /Full Screen/ }));

    expect(open).toHaveBeenCalledWith("/preview-fullscreen?error=quota", "_blank");
    expect(warn).toHaveBeenCalled();
  });
});

describe("AppBuilderPreview — Download ZIP", () => {
  class FakeZip {
    static instances: FakeZip[] = [];
    added: Array<[string, string]> = [];
    constructor() {
      FakeZip.instances.push(this);
    }
    file(path: string, content: string) {
      this.added.push([path, content]);
    }
    generateAsync = vi.fn().mockResolvedValue(new Blob(["zip"]));
  }

  let clicked: HTMLAnchorElement[];

  beforeEach(() => {
    FakeZip.instances = [];
    clicked = [];
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:zip");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
  });

  afterEach(() => {
    delete w.JSZip;
    vi.restoreAllMocks();
  });

  it("zips every file and downloads a sanitised, lower-cased project archive", async () => {
    const user = userEvent.setup();
    w.JSZip = FakeZip;
    render(<AppBuilderPreview files={FILES} projectName="My Shop App" />);

    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));

    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(clicked[0].download).toBe("my-shop-app.zip");
    expect(FakeZip.instances[0].added).toEqual(FILES.map((f) => [f.path, f.content]));
  });

  it("disables the button and shows 'Zipping...' until the archive is ready", async () => {
    const user = userEvent.setup();
    let resolveZip!: (b: Blob) => void;
    class SlowZip extends FakeZip {
      generateAsync = vi.fn().mockReturnValue(new Promise<Blob>((r) => (resolveZip = r)));
    }
    w.JSZip = SlowZip;
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));

    const busy = await screen.findByRole("button", { name: /Zipping/ });
    expect(busy).toBeDisabled();

    await act(async () => {
      resolveZip(new Blob(["zip"]));
    });
    expect(await screen.findByRole("button", { name: /Download ZIP/ })).toBeEnabled();
  });

  it("alerts the user and recovers when zip generation fails", async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    class FailingZip extends FakeZip {
      generateAsync = vi.fn().mockRejectedValue(new Error("nope"));
    }
    w.JSZip = FailingZip;
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));

    await waitFor(() =>
      expect(alertSpy).toHaveBeenCalledWith("Failed to generate ZIP. Please try downloading files individually."),
    );
    expect(clicked).toHaveLength(0);
    expect(await screen.findByRole("button", { name: /Download ZIP/ })).toBeEnabled();
  });

  it("loads JSZip from the CDN when it is not present, then zips", async () => {
    const user = userEvent.setup();
    const realAppend = document.head.appendChild.bind(document.head);
    vi.spyOn(document.head, "appendChild").mockImplementation(<T extends Node>(node: T): T => {
      if (node instanceof HTMLScriptElement && node.src.includes("jszip")) {
        w.JSZip = FakeZip;
        node.onload?.(new Event("load"));
        return node;
      }
      return realAppend(node);
    });
    render(<AppBuilderPreview files={FILES} projectName="cdn" />);

    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));

    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(clicked[0].download).toBe("cdn.zip");
  });

  it("alerts the user when the JSZip script fails to load", async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const realAppend = document.head.appendChild.bind(document.head);
    vi.spyOn(document.head, "appendChild").mockImplementation(<T extends Node>(node: T): T => {
      if (node instanceof HTMLScriptElement && node.src.includes("jszip")) {
        node.onerror?.(new Event("error"));
        return node;
      }
      return realAppend(node);
    });
    render(<AppBuilderPreview files={FILES} />);

    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledTimes(1));
    expect(clicked).toHaveLength(0);
  });
});

describe("AppBuilderPreview — revision bar", () => {
  it("does not render the revision bar when onRevise is not provided", () => {
    render(<AppBuilderPreview files={FILES} />);

    expect(screen.queryByLabelText("Revision instructions")).not.toBeInTheDocument();
  });

  it("disables Revise until the input has non-whitespace text", async () => {
    const user = userEvent.setup();
    render(<AppBuilderPreview files={FILES} onRevise={vi.fn()} />);
    const revise = screen.getByRole("button", { name: /Revise/ });

    expect(revise).toBeDisabled();
    await user.type(screen.getByLabelText("Revision instructions"), "  ");
    expect(revise).toBeDisabled();
    await user.type(screen.getByLabelText("Revision instructions"), "x");
    expect(revise).toBeEnabled();
  });

  it("submits the trimmed instruction on click and clears the input", async () => {
    const user = userEvent.setup();
    const onRevise = vi.fn();
    render(<AppBuilderPreview files={FILES} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  switch to postgres  ");
    await user.click(screen.getByRole("button", { name: /Revise/ }));

    expect(onRevise).toHaveBeenCalledWith("switch to postgres");
    expect(input).toHaveValue("");
  });

  it("submits on Enter and ignores Enter on a blank input", async () => {
    const user = userEvent.setup();
    const onRevise = vi.fn();
    render(<AppBuilderPreview files={FILES} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  {Enter}");
    expect(onRevise).not.toHaveBeenCalled();

    await user.type(input, "add auth{Enter}");
    expect(onRevise).toHaveBeenCalledTimes(1);
    expect(onRevise).toHaveBeenCalledWith("add auth");
  });
});

describe("AppBuilderPreview — explorer is scoped to its own tree", () => {
  it("renders file names in the explorer as text, not markup", () => {
    const evil = file("<img src=x onerror=alert(1)>.ts", "x");
    const { container } = render(<AppBuilderPreview files={[evil]} />);

    expect(container.querySelector("img")).toBeNull();
    const explorer = screen.getByLabelText("Search files").closest("div[style]") as HTMLElement;
    expect(within(explorer).getByText("<img src=x onerror=alert(1)>.ts")).toBeInTheDocument();
  });
});
