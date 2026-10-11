import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { authedFetchMock, getTokenMock } = vi.hoisted(() => ({
  authedFetchMock: vi.fn(),
  getTokenMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  authedFetch: authedFetchMock,
  getToken: getTokenMock,
}));

vi.mock("@/lib/env", () => ({ ENV: { API_URL: "http://api.test" } }));

import {
  exportFigmaJson,
  exportFigmaZip,
  htmlToFigmaJson,
  type FigmaGroupNode,
  type FigmaNode,
  type FigmaRectNode,
  type FigmaTextNode,
} from "./figmaExporter";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const WHITE = { r: 1, g: 1, b: 1, a: 1 };
const DARK_TEXT = { r: 0.1, g: 0.1, b: 0.1, a: 1 };

function bodyChildren(html: string): FigmaNode[] {
  return htmlToFigmaJson(`<html><body>${html}</body></html>`).document.screens[0].children;
}

function firstNode<T extends FigmaNode>(html: string): T {
  return bodyChildren(html)[0] as T;
}

class FakeZip {
  static instances: FakeZip[] = [];
  files = new Map<string, string>();
  constructor() {
    FakeZip.instances.push(this);
  }
  file(name: string, content: string): void {
    this.files.set(name, content);
  }
  generateAsync(): Promise<Blob> {
    return Promise.resolve(new Blob(["zip"]));
  }
}

function lastZip(): FakeZip {
  return FakeZip.instances[FakeZip.instances.length - 1];
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response;
}

function textResponse(status: number, body: string | Error): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.reject(new Error("no json")),
    text: () => (body instanceof Error ? Promise.reject(body) : Promise.resolve(body)),
  } as unknown as Response;
}

// ─── htmlToFigmaJson ──────────────────────────────────────────────────────────

describe("htmlToFigmaJson", () => {
  describe("document name", () => {
    it("uses the <title> text when present", () => {
      const doc = htmlToFigmaJson("<html><head><title>  My App  </title></head><body><h1>Hero</h1></body></html>");
      expect(doc.version).toBe(1);
      expect(doc.document.name).toBe("My App");
    });

    it("falls back to the <h1> text when no title exists", () => {
      expect(htmlToFigmaJson("<body><h1>Welcome</h1></body>").document.name).toBe("Welcome");
    });

    it("falls back to the default name when neither title nor h1 exist", () => {
      expect(htmlToFigmaJson("<body><p>x</p></body>").document.name).toBe("Prototype");
    });

    it("falls back to the provided name argument", () => {
      expect(htmlToFigmaJson("<body></body>", "Custom").document.name).toBe("Custom");
    });

    it("converts curly quotes and strips disallowed characters from the name", () => {
      const doc = htmlToFigmaJson("<title>\u201CHi\u201D \u2018you\u2019 @#$ ok!</title>");
      expect(doc.document.name).toBe("\"Hi\" 'you'  ok");
    });

    it("uses Node when sanitizing leaves an empty name", () => {
      expect(htmlToFigmaJson("<title>@@@</title>").document.name).toBe("Node");
    });

    it("truncates the name to 60 characters", () => {
      const doc = htmlToFigmaJson(`<title>${"a".repeat(70)}</title>`);
      expect(doc.document.name).toBe("a".repeat(60));
    });
  });

  describe("screen roots", () => {
    it("uses data-screen elements with names from data-screen, aria-label, heading, and index", () => {
      const doc = htmlToFigmaJson(`<body>
        <div data-screen="Login"><p>a</p></div>
        <div data-screen="" aria-label="Signup"><p>b</p></div>
        <div data-screen=""><h2>Dashboard</h2></div>
        <div data-screen=""><p>d</p></div>
        <section>ignored landmark</section>
      </body>`);
      expect(doc.document.screens.map((s) => s.name)).toEqual(["Login", "Signup", "Dashboard", "Screen 4"]);
    });

    it("falls back to section/main/article landmarks", () => {
      const doc = htmlToFigmaJson("<body><main><p>m</p></main><article><p>a</p></article></body>");
      expect(doc.document.screens.map((s) => s.name)).toEqual(["Screen 1", "Screen 2"]);
    });

    it("caps landmark screens at 20", () => {
      const doc = htmlToFigmaJson(`<body>${"<section><p>s</p></section>".repeat(25)}</body>`);
      expect(doc.document.screens).toHaveLength(20);
    });

    it("treats the body as a single 1440x900 white screen as a last resort", () => {
      const doc = htmlToFigmaJson("<body><p>Only</p></body>");
      expect(doc.document.screens).toHaveLength(1);
      expect(doc.document.screens[0]).toMatchObject({
        name: "Screen 1",
        width: 1440,
        height: 900,
        backgroundColor: WHITE,
      });
    });

    it("uses the root inline background color for the screen", () => {
      const doc = htmlToFigmaJson('<body><main style="background-color: rgba(0, 0, 0, 0.5)"><p>x</p></main></body>');
      expect(doc.document.screens[0].backgroundColor).toEqual({ r: 0, g: 0, b: 0, a: 0.5 });
    });

    it("uses a Tailwind bg class for the screen background", () => {
      const doc = htmlToFigmaJson('<body><main class="bg-black"><p>x</p></main></body>');
      expect(doc.document.screens[0].backgroundColor).toEqual({ r: 0, g: 0, b: 0, a: 1 });
    });

    it("falls back to white for an unknown Tailwind bg class", () => {
      const doc = htmlToFigmaJson('<body><main class="bg-unknown-123"><p>x</p></main></body>');
      expect(doc.document.screens[0].backgroundColor).toEqual(WHITE);
    });

    it("falls back to white for a transparent inline background", () => {
      const doc = htmlToFigmaJson('<body><main style="background-color: transparent"><p>x</p></main></body>');
      expect(doc.document.screens[0].backgroundColor).toEqual(WHITE);
    });
  });

  describe("element walking", () => {
    it("returns no nodes for an empty body", () => {
      expect(bodyChildren("")).toEqual([]);
    });

    it("skips non-visual and hidden elements", () => {
      const nodes = bodyChildren(`
        <script>var x = 1;</script><style>p{}</style><noscript>n</noscript><template><p>t</p></template>
        <p style="display: none">hidden1</p><p style="visibility: hidden">hidden2</p>`);
      expect(nodes).toEqual([]);
    });

    it("maps an svg to a placeholder rect named from aria-label", () => {
      expect(firstNode('<svg aria-label="Logo"></svg>')).toEqual({
        type: "RECT",
        name: "Logo",
        cornerRadius: 0,
        fill: { r: 0.9, g: 0.9, b: 0.9, a: 1 },
        stroke: null,
        strokeWeight: 0,
        note: "SVG icon placeholder — re-draw or replace with a Figma icon component.",
      });
    });

    it("names an unlabeled svg 'SVG icon'", () => {
      expect(firstNode<FigmaRectNode>("<svg></svg>").name).toBe("SVG icon");
    });

    it("maps an img to a placeholder rect using alt text", () => {
      expect(firstNode('<img alt="Avatar" class="rounded-lg">')).toEqual({
        type: "RECT",
        name: "Avatar",
        cornerRadius: 8,
        fill: { r: 0.85, g: 0.85, b: 0.85, a: 1 },
        stroke: null,
        strokeWeight: 0,
        note: "Image placeholder: Avatar",
      });
    });

    it("names an img without alt 'Image'", () => {
      const node = firstNode<FigmaRectNode>("<img>");
      expect(node.name).toBe("Image");
      expect(node.note).toBe("Image placeholder: Image");
    });

    it.each([
      ["rounded-full", 9999],
      ["rounded-2xl", 16],
      ["rounded-xl", 12],
      ["rounded-md", 6],
      ["rounded-sm", 4],
      ["rounded", 4],
      ["shadow", 0],
    ])("maps class %s to corner radius %i", (cls, radius) => {
      expect(firstNode<FigmaRectNode>(`<img class="${cls}">`).cornerRadius).toBe(radius);
    });

    it("prefers an inline border-radius over classes", () => {
      expect(firstNode<FigmaRectNode>('<img class="rounded-full" style="border-radius: 10px">').cornerRadius).toBe(10);
    });

    it("builds an h1 text node with heading defaults", () => {
      expect(firstNode("<h1>  Big Title  </h1>")).toEqual({
        type: "TEXT",
        name: "Big Title",
        characters: "Big Title",
        fontSize: 36,
        fontWeight: 700,
        color: DARK_TEXT,
        italic: false,
        textAlign: "LEFT",
      });
    });

    it.each([
      ["h2", 28, 700],
      ["h3", 22, 600],
      ["h6", 14, 600],
      ["p", 14, 400],
      ["span", 13, 400],
      ["label", 12, 400],
      ["legend", 12, 400],
    ])("builds a %s text node with size %i and weight %i", (tag, size, weight) => {
      const node = firstNode<FigmaTextNode>(`<${tag}>txt</${tag}>`);
      expect([node.fontSize, node.fontWeight]).toEqual([size, weight]);
    });

    it("builds an 11px caption text node inside a table", () => {
      expect(firstNode<FigmaTextNode>("<table><caption>Cap</caption></table>").fontSize).toBe(11);
    });

    it("keeps straight-converted quotes in characters and truncates the name to 40 chars", () => {
      const text = `\u201CQuoted\u201D ${"b".repeat(50)}`;
      const node = firstNode<FigmaTextNode>(`<p>${text}</p>`);
      expect(node.characters).toBe(`"Quoted" ${"b".repeat(50)}`);
      expect(node.name).toBe(`"Quoted" ${"b".repeat(31)}`);
    });

    it("applies inline font-size, color, italic and center alignment", () => {
      const node = firstNode<FigmaTextNode>(
        '<p style="font-size: 20px; color: rgb(0, 0, 255); font-style: italic; text-align: center">x</p>',
      );
      expect(node).toMatchObject({ fontSize: 20, color: { r: 0, g: 0, b: 1, a: 1 }, italic: true, textAlign: "CENTER" });
    });

    it("applies inline right alignment", () => {
      expect(firstNode<FigmaTextNode>('<p style="text-align: right">x</p>').textAlign).toBe("RIGHT");
    });

    it("applies Tailwind size, italic and center classes", () => {
      const node = firstNode<FigmaTextNode>('<p class="text-2xl italic text-center">x</p>');
      expect(node).toMatchObject({ fontSize: 24, italic: true, textAlign: "CENTER", color: DARK_TEXT });
    });

    it("applies the Tailwind text-right class", () => {
      expect(firstNode<FigmaTextNode>('<p class="text-right">x</p>').textAlign).toBe("RIGHT");
    });

    it("applies a Tailwind text color class", () => {
      expect(firstNode<FigmaTextNode>('<p class="text-white">x</p>').color).toEqual(WHITE);
    });

    it("emits nothing for an empty text element", () => {
      expect(bodyChildren("<p>   </p>")).toEqual([]);
    });

    it("builds a button group with a default blue bg and white centered label", () => {
      expect(firstNode("<button>Save</button>")).toEqual({
        type: "GROUP",
        name: "Save",
        children: [
          { type: "RECT", name: "bg", cornerRadius: 0, fill: { r: 0.24, g: 0.47, b: 1, a: 1 }, stroke: null, strokeWeight: 0 },
          {
            type: "TEXT",
            name: "label",
            characters: "Save",
            fontSize: 14,
            fontWeight: 600,
            color: WHITE,
            italic: false,
            textAlign: "CENTER",
          },
        ],
      });
    });

    it("builds an anchor group with Tailwind bg, size and text color", () => {
      const group = firstNode<FigmaGroupNode>('<a class="bg-blue-500 text-lg rounded-md">Go</a>');
      expect(group.children[0]).toMatchObject({ fill: { r: 59 / 255, g: 130 / 255, b: 246 / 255, a: 1 }, cornerRadius: 6 });
      expect(group.children[1]).toMatchObject({ fontSize: 18, color: WHITE });
    });

    it("builds an empty button group named after its tag with only a bg rect", () => {
      const group = firstNode<FigmaGroupNode>("<button></button>");
      expect(group.name).toBe("button");
      expect(group.children.map((c) => c.name)).toEqual(["bg"]);
    });

    it("uses an inline named color for a button label", () => {
      const group = firstNode<FigmaGroupNode>('<button style="color: red">X</button>');
      expect((group.children[1] as FigmaTextNode).color).toEqual({ r: 1, g: 0, b: 0, a: 1 });
    });

    it("maps an input with placeholder to a bordered rect", () => {
      expect(firstNode('<input placeholder="Email">')).toEqual({
        type: "RECT",
        name: "Email",
        cornerRadius: 0,
        fill: WHITE,
        stroke: { r: 0.8, g: 0.8, b: 0.8, a: 1 },
        strokeWeight: 1,
        note: "Input field: Email",
      });
    });

    it("uses the placeholder attribute of a textarea", () => {
      expect(firstNode<FigmaRectNode>('<textarea placeholder="Notes"></textarea>').name).toBe("Notes");
    });

    it("names a select without placeholder after its tag", () => {
      const node = firstNode<FigmaRectNode>("<select></select>");
      expect([node.name, node.note]).toEqual(["select", "Input field: select"]);
    });

    it("builds a text node for a container leaf like li", () => {
      const nodes = bodyChildren("<ul><li>One</li></ul>");
      expect(nodes).toEqual([
        { type: "TEXT", name: "One", characters: "One", fontSize: 14, fontWeight: 400, color: DARK_TEXT, italic: false, textAlign: "LEFT" },
      ]);
    });

    it("emits nothing for an empty container", () => {
      expect(bodyChildren("<div></div>")).toEqual([]);
    });

    it("flattens a container with a single child and no background", () => {
      expect(bodyChildren("<div><svg></svg></div>").map((n) => [n.type, n.name])).toEqual([["RECT", "SVG icon"]]);
    });

    it("groups multiple children under a container named by aria-label", () => {
      const group = firstNode<FigmaGroupNode>('<div aria-label="Card"><svg></svg><img></div>');
      expect([group.type, group.name, group.children.map((c) => c.name)]).toEqual(["GROUP", "Card", ["SVG icon", "Image"]]);
    });

    it.each([
      ['<div id="hero-box">', "hero-box"],
      ['<div role="list">', "list (div)"],
      ["<div>", "Lead text"],
    ])("derives the group name from %s", (open, name) => {
      expect(firstNode<FigmaGroupNode>(`${open}<span>Lead text</span><img></div>`).name).toBe(name);
    });

    it("names a group after its tag when it has no label, id, role or text", () => {
      expect(firstNode<FigmaGroupNode>("<nav><svg></svg><img></nav>").name).toBe("nav");
    });

    it("prepends a bg rect with border stroke and width when the container has a background", () => {
      const group = firstNode<FigmaGroupNode>(
        '<div style="background-color: rgb(255, 0, 0); border: 2px solid rgb(0, 255, 0); border-radius: 4px"><svg></svg></div>',
      );
      expect(group.children[0]).toEqual({
        type: "RECT",
        name: "bg",
        cornerRadius: 4,
        fill: { r: 1, g: 0, b: 0, a: 1 },
        stroke: { r: 0, g: 1, b: 0, a: 1 },
        strokeWeight: 2,
      });
      expect(group.children).toHaveLength(2);
    });

    it("uses a null stroke and zero weight when a background container has no border", () => {
      const group = firstNode<FigmaGroupNode>('<div class="bg-white"><svg></svg></div>');
      expect(group.children[0]).toMatchObject({ fill: WHITE, stroke: null, strokeWeight: 0 });
    });

    it("stops recursing past depth 8 and turns the cut-off container into text", () => {
      const html = `${"<div>".repeat(10)}<h1>Deep</h1>${"</div>".repeat(10)}`;
      expect(bodyChildren(html)).toEqual([
        { type: "TEXT", name: "Deep", characters: "Deep", fontSize: 14, fontWeight: 400, color: DARK_TEXT, italic: false, textAlign: "LEFT" },
      ]);
    });

    it("walks at most 60 children per node", () => {
      expect(bodyChildren("<p>x</p>".repeat(61))).toHaveLength(60);
    });
  });
});

// ─── exportFigmaZip / exportFigmaJson ─────────────────────────────────────────

describe("exportFigmaZip", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let clickSpy: ReturnType<typeof vi.spyOn>;
  let downloads: { href: string; download: string }[];
  let createUrl: ReturnType<typeof vi.fn>;
  let revokeUrl: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    FakeZip.instances = [];
    (window as unknown as { JSZip?: unknown }).JSZip = FakeZip;
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
    getTokenMock.mockReturnValue("tok");
    fetchMock = vi.fn((url: string) => Promise.resolve(textResponse(200, `content of ${url}`)));
    vi.stubGlobal("fetch", fetchMock);
    createUrl = vi.fn(() => "blob:fake");
    revokeUrl = vi.fn();
    // jsdom has no createObjectURL/revokeObjectURL; install controlled stubs.
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revokeUrl });
    downloads = [];
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push({ href: this.href, download: this.download, attached: document.body.contains(this) } as never);
    });
  });

  afterEach(() => {
    delete (window as unknown as { JSZip?: unknown }).JSZip;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authedFetchMock.mockReset();
    getTokenMock.mockReset();
  });

  it("uses the client-side fallback and downloads a zip when no runId is given", async () => {
    await exportFigmaZip("<title>T</title><body><p>Hi</p></body>", "proto");

    expect(authedFetchMock).not.toHaveBeenCalled();
    const json = JSON.parse(lastZip().files.get("proto-figma.json")!);
    expect(json.version).toBe(1);
    expect(json.document.name).toBe("T");
    expect(downloads).toEqual([{ href: "blob:fake", download: "proto-figma-export.zip", attached: true }]);
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(revokeUrl).toHaveBeenCalledWith("blob:fake");
    expect(document.querySelectorAll("a[download]")).toHaveLength(0);
  });

  it("names the fallback document after the stem 'prototype' when filename is empty", async () => {
    await exportFigmaZip("<body></body>", "");
    const json = JSON.parse(lastZip().files.get("prototype-figma.json")!);
    expect(json.document.name).toBe("prototype");
    expect(downloads[0].download).toBe("prototype-figma-export.zip");
  });

  it("bundles every fetched plugin file under the plugin folder", async () => {
    await exportFigmaZip("<body></body>", "p");
    expect(fetchMock.mock.calls.map((c) => c[0]).sort()).toEqual([
      "/figma-plugin/README.md",
      "/figma-plugin/code.js",
      "/figma-plugin/manifest.json",
      "/figma-plugin/ui.html",
    ]);
    expect(lastZip().files.get("velocityai-figma-plugin/code.js")).toBe("content of /figma-plugin/code.js");
    expect(lastZip().files.size).toBe(5);
  });

  it("skips plugin files that return non-OK or reject", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith("code.js")) return Promise.resolve(textResponse(404, "nope"));
      if (url.endsWith("ui.html")) return Promise.reject(new Error("offline"));
      return Promise.resolve(textResponse(200, "ok"));
    });
    await exportFigmaZip("<body></body>", "p");
    expect([...lastZip().files.keys()].sort()).toEqual([
      "p-figma.json",
      "velocityai-figma-plugin/README.md",
      "velocityai-figma-plugin/manifest.json",
    ]);
    expect(downloads).toHaveLength(1);
  });

  it("uses the backend payload when the backend responds OK", async () => {
    const payload = { version: 3, screens: [{ id: "s1" }], viewport: { w: 1 }, tokens: {} };
    authedFetchMock.mockResolvedValue(jsonResponse(payload));

    await exportFigmaZip("<body><p>ignored</p></body>", "b", "run/1");

    expect(authedFetchMock).toHaveBeenCalledWith("http://api.test/api/runs/run%2F1/figma-export", {
      method: "POST",
      headers: { Authorization: "Bearer tok" },
    });
    expect(JSON.parse(lastZip().files.get("b-figma.json")!)).toEqual(payload);
    expect(lastZip().files.get("b-figma.json")).toBe(JSON.stringify(payload, null, 2));
  });

  it.each([503, 404])("falls back to the DOM walk without error when the backend returns %i", async (status) => {
    authedFetchMock.mockResolvedValue(textResponse(status, "unavailable"));

    await exportFigmaZip("<title>Fallback</title>", "f", "r1");

    expect(JSON.parse(lastZip().files.get("f-figma.json")!).document.name).toBe("Fallback");
    expect(console.warn).toHaveBeenCalledWith("[figmaExporter] backend non-OK:", status, "unavailable");
    expect(console.warn).not.toHaveBeenCalledWith("[figmaExporter] backend failed, falling back:", expect.anything());
  });

  it("treats other backend errors as failures, then still falls back", async () => {
    authedFetchMock.mockResolvedValue(textResponse(500, "boom"));

    await exportFigmaZip("<title>Fallback</title>", "f", "r1");

    const failed = (console.warn as unknown as ReturnType<typeof vi.fn>).mock.calls.find(
      (c) => c[0] === "[figmaExporter] backend failed, falling back:",
    );
    expect((failed?.[1] as Error).message).toBe("Figma export failed (500): boom");
    expect(JSON.parse(lastZip().files.get("f-figma.json")!).version).toBe(1);
  });

  it("uses an empty body when reading the error response text rejects", async () => {
    authedFetchMock.mockResolvedValue(textResponse(500, new Error("stream")));

    await exportFigmaZip("<body></body>", "f", "r1");

    expect(console.warn).toHaveBeenCalledWith("[figmaExporter] backend non-OK:", 500, "");
  });

  it("falls back when the backend request rejects", async () => {
    authedFetchMock.mockRejectedValue(new Error("network"));

    await exportFigmaZip("<body></body>", "f", "r1");

    expect(JSON.parse(lastZip().files.get("f-figma.json")!).version).toBe(1);
    expect(downloads).toHaveLength(1);
  });

  it("loads JSZip from the CDN when it is not on window", async () => {
    delete (window as unknown as { JSZip?: unknown }).JSZip;
    const appended: string[] = [];
    vi.spyOn(document.head, "appendChild").mockImplementation(<T extends Node>(node: T): T => {
      const script = node as unknown as HTMLScriptElement;
      appended.push(script.src);
      (window as unknown as { JSZip?: unknown }).JSZip = FakeZip;
      queueMicrotask(() => script.onload?.(new Event("load")));
      return node;
    });

    await exportFigmaZip("<body></body>", "z");

    expect(appended).toEqual(["https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"]);
    expect(lastZip().files.has("z-figma.json")).toBe(true);
    expect(downloads).toHaveLength(1);
  });

  it("rejects when the JSZip script fails to load", async () => {
    delete (window as unknown as { JSZip?: unknown }).JSZip;
    vi.spyOn(document.head, "appendChild").mockImplementation(<T extends Node>(node: T): T => {
      queueMicrotask(() => (node as unknown as HTMLScriptElement).onerror?.(new Event("error")));
      return node;
    });

    await expect(exportFigmaZip("<body></body>", "z")).rejects.toThrow("Could not load JSZip.");
    expect(downloads).toHaveLength(0);
    expect(clickSpy).not.toHaveBeenCalled();
  });
});

describe("exportFigmaJson", () => {
  beforeEach(() => {
    FakeZip.instances = [];
    (window as unknown as { JSZip?: unknown }).JSZip = FakeZip;
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(textResponse(404, ""))));
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    delete (window as unknown as { JSZip?: unknown }).JSZip;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    authedFetchMock.mockReset();
  });

  it("delegates to the zip export using the client-side fallback", async () => {
    await exportFigmaJson("<title>Legacy</title>", "old");
    expect(authedFetchMock).not.toHaveBeenCalled();
    expect(JSON.parse(lastZip().files.get("old-figma.json")!).document.name).toBe("Legacy");
  });
});
