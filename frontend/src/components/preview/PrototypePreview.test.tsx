import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PrototypePreview } from "./PrototypePreview";

const PAGE =
  "<!DOCTYPE html><html><head><title>P</title></head><body><h1>Hello</h1></body></html>";

// Boundary: Blob URLs. Every Blob handed to createObjectURL is recorded so a test
// can read the HTML that would be loaded into the preview iframe.
let blobs: Blob[] = [];
let createObjectURL: ReturnType<typeof vi.spyOn>;
let revokeObjectURL: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  blobs = [];
  createObjectURL = vi.spyOn(URL, "createObjectURL").mockImplementation((obj: Blob | MediaSource) => {
    blobs.push(obj as Blob);
    return `blob:mock/${blobs.length}`;
  });
  revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function lastBlobText(): Promise<string> {
  return blobs[blobs.length - 1].text();
}

describe("PrototypePreview — non-preview states", () => {
  it("shows 'No Preview Yet' when there is no content", () => {
    render(<PrototypePreview />);

    expect(screen.getByText("No Preview Yet")).toBeInTheDocument();
    expect(screen.queryByTitle("Prototype Preview")).not.toBeInTheDocument();
  });

  it("shows 'Building prototype...' while streaming", () => {
    render(<PrototypePreview content={PAGE} isStreaming />);

    expect(screen.getByText("Building prototype...")).toBeInTheDocument();
    expect(screen.queryByTitle("Prototype Preview")).not.toBeInTheDocument();
  });

  it("shows the raw text when the output is not an HTML document", () => {
    render(<PrototypePreview content={"plain text output, not html"} />);

    expect(screen.getByText("Output (text format):")).toBeInTheDocument();
    expect(screen.getByText("plain text output, not html")).toBeInTheDocument();
    expect(screen.queryByTitle("Prototype Preview")).not.toBeInTheDocument();
  });

  it("shows 'Loading preview...' while the blob URL is not yet available for an HTML document", () => {
    createObjectURL.mockReturnValue("");
    render(<PrototypePreview content={PAGE} />);

    expect(screen.getByText("Loading preview...")).toBeInTheDocument();
  });

  it("returns to the empty state when the content is cleared", () => {
    const { rerender } = render(<PrototypePreview content={PAGE} />);
    expect(screen.getByTitle("Prototype Preview")).toBeInTheDocument();

    rerender(<PrototypePreview content="" />);

    expect(screen.getByText("No Preview Yet")).toBeInTheDocument();
  });
});

describe("PrototypePreview — HTML extraction and iframe", () => {
  it("loads the document into a sandboxed iframe through a blob URL", () => {
    render(<PrototypePreview content={PAGE} />);

    const frame = screen.getByTitle("Prototype Preview");
    expect(frame).toHaveAttribute("src", "blob:mock/1");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin");
  });

  it("strips markdown fences, the artifact envelope and any preamble before the doctype", async () => {
    const wrapped = `\`\`\`html\n<artifact type="text/html">\nIntro text\n${PAGE}\n</artifact>\n\`\`\``;
    render(<PrototypePreview content={wrapped} />);

    await screen.findByTitle("Prototype Preview");

    expect(await lastBlobText()).toBe(PAGE);
  });

  it("revokes the previous blob URL when the content changes", () => {
    const { rerender } = render(<PrototypePreview content={PAGE} />);

    rerender(<PrototypePreview content={PAGE.replace("Hello", "Bye")} />);

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock/1");
  });

  it("opens the blob URL in a new tab from the Open button", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    render(<PrototypePreview content={PAGE} />);

    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(open).toHaveBeenCalledWith("blob:mock/1", "_blank");
  });
});

describe("PrototypePreview — zoom", () => {
  it("steps through the zoom levels with the zoom buttons and resets to 100%", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    expect(screen.getByRole("button", { name: /^\d+%$/ })).toHaveTextContent("100%");

    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByRole("button", { name: /^\d+%$/ })).toHaveTextContent("110%");

    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(screen.getByRole("button", { name: /^\d+%$/ })).toHaveTextContent("90%");

    await user.click(screen.getByRole("button", { name: /^\d+%$/ }));
    expect(screen.getByRole("button", { name: /^\d+%$/ })).toHaveTextContent("100%");
  });

  it("disables Zoom out at the minimum level (50%)", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);

    for (let i = 0; i < 4; i++) {
      await user.click(screen.getByRole("button", { name: "Zoom out" }));
    }

    expect(screen.getByRole("button", { name: /^\d+%$/ })).toHaveTextContent("50%");
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeDisabled();
  });

  it("disables Zoom in at the maximum level (200%)", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);

    for (let i = 0; i < 5; i++) {
      await user.click(screen.getByRole("button", { name: "Zoom in" }));
    }

    expect(screen.getByRole("button", { name: /^\d+%$/ })).toHaveTextContent("200%");
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeDisabled();
  });
});

describe("PrototypePreview — source view", () => {
  it("shows the rendered source with size and line count, and returns to the preview", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);

    await user.click(screen.getByRole("button", { name: "Source" }));

    expect(screen.getByText("index.html")).toBeInTheDocument();
    expect(screen.getByText(/KB · 1 lines/)).toBeInTheDocument();
    expect(screen.queryByTitle("Prototype Preview")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Source" }));
    expect(screen.getByTitle("Prototype Preview")).toBeInTheDocument();
  });

  it("closes the source view with its close control", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Source" }));

    // The close control is an icon-only button with no accessible name; it is the
    // sibling that follows 'Copy all' (see report: a11y finding).
    const closeButton = screen.getByRole("button", { name: /Copy all/i }).nextElementSibling as HTMLElement;
    await user.click(closeButton);

    expect(screen.getByTitle("Prototype Preview")).toBeInTheDocument();
  });

  it("copies the rendered source and confirms with 'Copied'", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Source" }));

    await user.click(screen.getByRole("button", { name: /Copy all/i }));

    expect(writeText).toHaveBeenCalledWith(PAGE);
    expect(await screen.findByRole("button", { name: /Copied/ })).toBeInTheDocument();
  });

  it("switches from the tweaks panel to source and back (mutually exclusive panels)", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);

    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    expect(screen.getByText("Edit HTML")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Source" }));
    expect(screen.queryByText("Edit HTML")).not.toBeInTheDocument();
    expect(screen.getByText("index.html")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    expect(screen.queryByText("index.html")).not.toBeInTheDocument();
    expect(screen.getByText("Edit HTML")).toBeInTheDocument();
  });
});

describe("PrototypePreview — tweaks", () => {
  it("opens the tweaks panel and closes it from the panel's own close button", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);

    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    expect(screen.getByText("Edit HTML")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close tweaks" }));

    expect(screen.queryByText("Edit HTML")).not.toBeInTheDocument();
  });

  it("rebuilds the preview with a themed style block when a preset is applied", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.click(screen.getByRole("button", { name: "Dark" }));

    await waitFor(async () => {
      const html = await lastBlobText();
      expect(html).toContain('<style id="flowin-tweaks">');
      expect(html).toContain("--bg: #0f172a !important;");
      // Dark background uses the light-on-dark alternating row tint.
      expect(html).toContain("rgba(255,255,255,0.06)");
    });
  });

  it("uses the dark-on-light alternating row tint for a light background", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.click(screen.getByRole("button", { name: "Light" }));

    await waitFor(async () => {
      expect(await lastBlobText()).toContain("rgba(0,0,0,0.04)");
    });
  });

  it("shows the 'tweaks applied' marker in the source view after a tweak", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    await user.click(screen.getByRole("button", { name: "Sepia" }));
    await waitFor(async () => expect(await lastBlobText()).toContain("#fdf6e3"));

    await user.click(screen.getByRole("button", { name: "Source" }));

    expect(screen.getByText("tweaks applied")).toBeInTheDocument();
  });

  it("debounces a hex edit and then rebuilds the preview with the new color", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    const before = blobs.length;

    await user.type(screen.getByLabelText("Accent / Primary hex value"), "a");

    expect(blobs).toHaveLength(before); // rebuild is debounced, not immediate
    await waitFor(async () => expect(await lastBlobText()).toContain("--accent: #2563eba !important;"));
  });

  it("falls back to a light computation for a short, non-6-digit background hex", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.type(screen.getByLabelText("Background hex value"), "{Backspace}{Backspace}");

    await waitFor(async () => {
      const html = await lastBlobText();
      expect(html).toContain("--bg: #ffff !important;");
      expect(html).toContain("rgba(0,0,0,0.04)");
    });
  });

  it("injects the Google Fonts link inside </head> when a web font is chosen", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.click(screen.getByRole("button", { name: "Inter" }));

    await waitFor(async () => {
      const html = await lastBlobText();
      expect(html).toContain('<link id="flowin-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">\n</head>');
    });
  });

  it("injects the Google Fonts link after an unclosed <head> tag", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={"<html><head><body>x</body></html>"} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.click(screen.getByRole("button", { name: "Roboto" }));

    await waitFor(async () => {
      expect(await lastBlobText()).toContain("<head>\n<link id=\"flowin-font\"");
    });
  });

  it("does not add a font link for a system font", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.click(screen.getByRole("button", { name: "Georgia (Serif)" }));

    await waitFor(async () => {
      const html = await lastBlobText();
      expect(html).toContain("font-family: Georgia, 'Times New Roman', serif !important;");
      expect(html).not.toContain("flowin-font");
    });
  });

  it("appends the style block at the end when the document has no </body>", async () => {
    const user = userEvent.setup();
    const noBody = "<!DOCTYPE html><html><head></head><p>hi</p></html>";
    render(<PrototypePreview content={noBody} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.click(screen.getByRole("button", { name: "Dark" }));

    await waitFor(async () => {
      const html = await lastBlobText();
      expect(html.startsWith(noBody + "\n<style id=\"flowin-tweaks\">")).toBe(true);
      expect(html.endsWith("</style>")).toBe(true);
    });
  });

  it("replaces the previous tweak block instead of stacking blocks across edits", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));

    await user.click(screen.getByRole("button", { name: "Dark" }));
    await waitFor(async () => expect(await lastBlobText()).toContain("#0f172a"));
    await user.click(screen.getByRole("button", { name: "Sepia" }));
    await waitFor(async () => expect(await lastBlobText()).toContain("#fdf6e3"));

    const html = await lastBlobText();
    expect(html.match(/<style id="flowin-tweaks">/g)).toHaveLength(1);
    expect(html).not.toContain("--bg: #0f172a !important;");
  });

  it("restores the untweaked document when Reset is clicked", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    await user.click(screen.getByRole("button", { name: "Dark" }));
    await waitFor(async () => expect(await lastBlobText()).toContain("flowin-tweaks"));

    await user.click(screen.getByRole("button", { name: "Reset all tweaks" }));

    await waitFor(async () => expect(await lastBlobText()).toBe(PAGE));
  });

  it("applies edited HTML without tweaks when no tweak is active", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));

    await user.type(screen.getByLabelText("Edit HTML directly"), "<!--edited-->");
    await user.click(screen.getByRole("button", { name: "Apply changes" }));

    await waitFor(async () => expect(await lastBlobText()).toBe(PAGE + "<!--edited-->"));
  });

  it("bakes active tweaks into edited HTML and drops a stale tweak block from the edit", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    await user.click(screen.getByRole("button", { name: "Dark" }));
    await waitFor(async () => expect(await lastBlobText()).toContain("#0f172a"));
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));

    await user.type(
      screen.getByLabelText("Edit HTML directly"),
      '<style id="flowin-tweaks">stale</style>',
    );
    await user.click(screen.getByRole("button", { name: "Apply changes" }));

    await waitFor(async () => {
      const html = await lastBlobText();
      expect(html).not.toContain("stale");
      expect(html.match(/<style id="flowin-tweaks">/g)).toHaveLength(1);
      expect(html).toContain("--bg: #0f172a !important;");
    });
  });

  it("clears tweaks and loads the new document when the content prop changes", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<PrototypePreview content={PAGE} />);
    await user.click(screen.getByRole("button", { name: "Tweaks" }));
    await user.click(screen.getByRole("button", { name: "Dark" }));
    await waitFor(async () => expect(await lastBlobText()).toContain("flowin-tweaks"));

    const next = PAGE.replace("Hello", "Next run");
    rerender(<PrototypePreview content={next} />);

    await waitFor(async () => expect(await lastBlobText()).toBe(next));
  });
});

describe("PrototypePreview — revision bar", () => {
  it("does not render the revision bar when onRevise is not provided", () => {
    render(<PrototypePreview content={PAGE} />);

    expect(screen.queryByLabelText("Revision instructions")).not.toBeInTheDocument();
  });

  it("disables Revise until the input has non-whitespace text", async () => {
    const user = userEvent.setup();
    render(<PrototypePreview content={PAGE} onRevise={vi.fn()} />);
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
    render(<PrototypePreview content={PAGE} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  add reports page  ");
    await user.click(screen.getByRole("button", { name: /Revise/ }));

    expect(onRevise).toHaveBeenCalledWith("add reports page");
    expect(input).toHaveValue("");
  });

  it("submits on Enter and ignores Enter on a blank input", async () => {
    const user = userEvent.setup();
    const onRevise = vi.fn();
    render(<PrototypePreview content={PAGE} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  {Enter}");
    expect(onRevise).not.toHaveBeenCalled();

    await user.type(input, "rename tab{Enter}");
    expect(onRevise).toHaveBeenCalledTimes(1);
    expect(onRevise).toHaveBeenCalledWith("rename tab");
  });
});

describe("PrototypePreview — unsafe content", () => {
  const UNSAFE =
    "<!DOCTYPE html><html><body><script>window.__pwned = true;</script>" +
    '<a href="javascript:alert(1)">go</a></body></html>';

  it("keeps a script payload and javascript: link out of the host document in preview mode", () => {
    const { container } = render(<PrototypePreview content={UNSAFE} />);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href^="javascript:" i]')).toBeNull();
    expect((window as unknown as Record<string, unknown>).__pwned).toBeUndefined();
  });

  it("renders the payload as inert text in the source view", async () => {
    const user = userEvent.setup();
    const { container } = render(<PrototypePreview content={UNSAFE} />);

    await user.click(screen.getByRole("button", { name: "Source" }));

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.getByText(/<script>window\.__pwned = true;<\/script>/)).toBeInTheDocument();
  });

  it("renders non-HTML output containing a script payload as inert text", () => {
    const { container } = render(<PrototypePreview content={"<script>window.__pwned = true;</script>"} />);

    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("<script>window.__pwned = true;</script>")).toBeInTheDocument();
  });

  it("scopes the sandbox so it does not grant top-navigation or popup privileges", () => {
    render(<PrototypePreview content={UNSAFE} />);

    const tokens = (screen.getByTitle("Prototype Preview").getAttribute("sandbox") ?? "").split(/\s+/);
    expect(tokens).not.toContain("allow-top-navigation");
    expect(tokens).not.toContain("allow-popups");
    expect(within(document.body).getByTitle("Prototype Preview")).toBeInTheDocument();
  });
});
