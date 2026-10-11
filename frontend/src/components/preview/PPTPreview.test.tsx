import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PPTPreview } from "./PPTPreview";

// Boundaries PPTPreview imports. None of the export/download handlers are wired
// to the rendered tree, so these only keep module loading side-effect free.
vi.mock("@/lib/api", () => ({
  authedFetch: vi.fn(),
  getToken: vi.fn(() => "test-token"),
}));
vi.mock("@/lib/env", () => ({ ENV: { API_URL: "http://api.test" } }));

const DECK = "<!DOCTYPE html>\n<html><head><title>Deck</title></head><body><h1>Slide One</h1></body></html>";

function getDeckFrame(): HTMLIFrameElement {
  return screen.getByTitle("Slide Deck Preview") as HTMLIFrameElement;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("PPTPreview — empty / loading / invalid states", () => {
  it("shows the 'No Slides Yet' placeholder when there is no content and no pptx code", () => {
    render(<PPTPreview />);

    expect(screen.getByText("No Slides Yet")).toBeInTheDocument();
    expect(screen.getByText("Run the pipeline to generate your presentation.")).toBeInTheDocument();
    expect(screen.queryByTitle("Slide Deck Preview")).not.toBeInTheDocument();
  });

  it("shows 'Generating slides...' when pptx code exists but HTML content has not arrived", () => {
    render(<PPTPreview pptxCode="pptx.writeFile()" />);

    expect(screen.getByText("Generating slides...")).toBeInTheDocument();
    expect(screen.queryByTitle("Slide Deck Preview")).not.toBeInTheDocument();
  });

  it("shows an error card when the output contains no HTML document", () => {
    render(<PPTPreview content="just some prose with no html document" />);

    expect(screen.getByText("Invalid presentation output")).toBeInTheDocument();
    expect(screen.getByText("Try running the pipeline again.")).toBeInTheDocument();
    expect(screen.queryByTitle("Slide Deck Preview")).not.toBeInTheDocument();
  });
});

describe("PPTPreview — deck extraction", () => {
  it("renders a valid deck into the preview iframe's srcdoc unchanged", () => {
    render(<PPTPreview content={DECK} />);

    expect(getDeckFrame()).toHaveAttribute("srcdoc", DECK);
  });

  it("strips a surrounding markdown html fence", () => {
    render(<PPTPreview content={"```html\n" + DECK + "\n```"} />);

    expect(getDeckFrame()).toHaveAttribute("srcdoc", DECK);
  });

  it("unwraps an <artifact> envelope", () => {
    render(<PPTPreview content={`<artifact type="text/html">\n${DECK}\n</artifact>`} />);

    expect(getDeckFrame()).toHaveAttribute("srcdoc", DECK);
  });

  it("drops a validator preamble that quotes the doctype mid-sentence", () => {
    const preamble = "✓ Single complete file starting with `<!DOCTYPE html>`\nVERDICT: PASS\n";
    render(<PPTPreview content={preamble + DECK} />);

    const srcdoc = getDeckFrame().getAttribute("srcdoc");
    expect(srcdoc).toBe(DECK);
    expect(srcdoc).not.toContain("VERDICT");
  });

  it("falls back to a loose <html> match when the document tag is not at the start of a line", () => {
    const loose = "Report text <html><body>deck</body></html>";
    render(<PPTPreview content={loose} />);

    expect(getDeckFrame()).toHaveAttribute("srcdoc", "<html><body>deck</body></html>");
  });

  it("drops text appended after the closing </html>", () => {
    render(<PPTPreview content={DECK + "\n\nVERDICT: all slides verified"} />);

    const srcdoc = getDeckFrame().getAttribute("srcdoc");
    expect(srcdoc).toBe(DECK);
    expect(srcdoc).not.toContain("VERDICT");
  });

  it("removes baked-in download/export buttons", () => {
    const html =
      '<!DOCTYPE html><html><body>' +
      '<button class="dl-btn">Save</button>' +
      '<button onclick="generatePresentation()">Make</button>' +
      "<button>Download PPTX</button>" +
      "<button>Keep me</button>" +
      "</body></html>";
    render(<PPTPreview content={html} />);

    const srcdoc = getDeckFrame().getAttribute("srcdoc") ?? "";
    expect(srcdoc).not.toContain("dl-btn");
    expect(srcdoc).not.toContain("generatePresentation");
    expect(srcdoc).not.toContain("Download PPTX");
    expect(srcdoc).toContain("<button>Keep me</button>");
  });

  it("removes the static-preview fallback style when the deck carries its own runtime script", () => {
    const html =
      "<!DOCTYPE html><html><head>" +
      "<style>/* Static-preview fallback (runtime.js is absent) */ .slide{opacity:1}</style>" +
      "</head><body><script>/* is-active */</script></body></html>";
    render(<PPTPreview content={html} />);

    expect(getDeckFrame().getAttribute("srcdoc")).not.toContain("Static-preview fallback");
  });

  it("keeps the static-preview fallback style when the deck has no runtime script", () => {
    const html =
      "<!DOCTYPE html><html><head>" +
      "<style>/* Static-preview fallback (runtime.js is absent) */ .slide{opacity:1}</style>" +
      "</head><body></body></html>";
    render(<PPTPreview content={html} />);

    expect(getDeckFrame().getAttribute("srcdoc")).toContain("Static-preview fallback");
  });
});

describe("PPTPreview — iframe scaling", () => {
  it("scales and centres the 1280x720 iframe to fit its container", () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(2000);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(360);
    render(<PPTPreview content={DECK} />);

    const frame = getDeckFrame();
    // min(2000/1280, 360/720) = 0.5 → scaled box is 640x360, centred horizontally.
    expect(frame.style.width).toBe("1280px");
    expect(frame.style.height).toBe("720px");
    expect(frame.style.transform).toBe("scale(0.5)");
    expect(frame.style.left).toBe("680px");
    expect(frame.style.top).toBe("0px");
  });

  it("re-scales the iframe when the observed container is resized", () => {
    const callbacks: Array<() => void> = [];
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          callbacks.push(cb);
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    const width = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1280);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(720);
    render(<PPTPreview content={DECK} />);
    expect(getDeckFrame().style.transform).toBe("scale(1)");

    width.mockReturnValue(640);
    callbacks.forEach((cb) => cb());

    expect(getDeckFrame().style.transform).toBe("scale(0.5)");
  });
});

describe("PPTPreview — revision bar", () => {
  it("does not render the revision bar when onRevise is not provided", () => {
    render(<PPTPreview content={DECK} />);

    expect(screen.queryByLabelText("Revision instructions")).not.toBeInTheDocument();
  });

  it("disables Revise until the input has non-whitespace text", async () => {
    const user = userEvent.setup();
    render(<PPTPreview content={DECK} onRevise={vi.fn()} />);
    const input = screen.getByLabelText("Revision instructions");
    const revise = screen.getByRole("button", { name: /Revise/ });

    expect(revise).toBeDisabled();
    await user.type(input, "  ");
    expect(revise).toBeDisabled();
    await user.type(input, "x");
    expect(revise).toBeEnabled();
  });

  it("submits the trimmed instruction on Revise click and clears the input", async () => {
    const user = userEvent.setup();
    const onRevise = vi.fn();
    render(<PPTPreview content={DECK} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  bigger title  ");
    await user.click(screen.getByRole("button", { name: /Revise/ }));

    expect(onRevise).toHaveBeenCalledTimes(1);
    expect(onRevise).toHaveBeenCalledWith("bigger title");
    expect(input).toHaveValue("");
  });

  it("submits the instruction when Enter is pressed", async () => {
    const user = userEvent.setup();
    const onRevise = vi.fn();
    render(<PPTPreview content={DECK} onRevise={onRevise} />);

    await user.type(screen.getByLabelText("Revision instructions"), "add ROI slide{Enter}");

    expect(onRevise).toHaveBeenCalledWith("add ROI slide");
  });

  it("ignores Enter when the input is blank", async () => {
    const user = userEvent.setup();
    const onRevise = vi.fn();
    render(<PPTPreview content={DECK} onRevise={onRevise} />);

    await user.type(screen.getByLabelText("Revision instructions"), "  {Enter}");

    expect(onRevise).not.toHaveBeenCalled();
  });
});

describe("PPTPreview — unsafe deck content stays contained", () => {
  const UNSAFE_DECK =
    "<!DOCTYPE html><html><body>" +
    "<script>window.__pwned = true;</script>" +
    '<a href="javascript:alert(1)">go</a>' +
    "</body></html>";

  it("keeps the script and javascript: link out of the host document", () => {
    const { container } = render(<PPTPreview content={UNSAFE_DECK} />);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href^="javascript:" i]')).toBeNull();
    expect((window as unknown as Record<string, unknown>).__pwned).toBeUndefined();
  });

  it("confines the deck to a sandboxed iframe without top-navigation, popup or form privileges", () => {
    render(<PPTPreview content={UNSAFE_DECK} />);

    const tokens = (getDeckFrame().getAttribute("sandbox") ?? "").split(/\s+/);
    expect(tokens).toContain("allow-scripts");
    expect(tokens).not.toContain("allow-top-navigation");
    expect(tokens).not.toContain("allow-popups");
    expect(tokens).not.toContain("allow-forms");
  });

  it("never injects a deck script into the host when the output is not an HTML document", () => {
    const { container } = render(<PPTPreview content={"<script>window.__pwned = true;</script>"} />);

    expect(screen.getByText("Invalid presentation output")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });
});
