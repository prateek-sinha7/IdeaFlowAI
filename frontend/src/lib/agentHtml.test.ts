/**
 * ISS-1067 / ISS-1160 / ISS-1161 / ISS-1162: the agent-HTML helper, and a source
 * guard that keeps every viewer on it.
 *
 * The iframe token was fixed once (5db19e6db) and regressed twice (77228e567,
 * d2970ff7f) with no test noticing, so the guard reads the source. jsdom cannot
 * show origin or navigation; those were measured in real Chrome
 * (evidence/qa-kb-125/analysis-1..4).
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AGENT_HTML_SANDBOX, frameableAgentHtml, openAgentHtmlInNewTab } from "./agentHtml";

const BASE = '<base href="about:srcdoc">';

describe("frameableAgentHtml", () => {
  it("puts the base first in <head>", () => {
    expect(frameableAgentHtml('<!DOCTYPE html><html><head lang="x"><title>t</title></head></html>')).toBe(
      `<!DOCTYPE html><html><head lang="x">${BASE}<title>t</title></head></html>`,
    );
  });

  it("without <head>: after <html>, else after the doctype (never before it), else first", () => {
    expect(frameableAgentHtml("<html><body><header>h</header></body></html>")).toBe(
      `<html>${BASE}<body><header>h</header></body></html>`,
    );
    expect(frameableAgentHtml("<!doctype html><p>x</p>")).toBe(`<!doctype html>${BASE}<p>x</p>`);
    expect(frameableAgentHtml("<p>x</p>")).toBe(`${BASE}<p>x</p>`);
  });

  it("is idempotent", () => {
    const once = frameableAgentHtml("<html><head></head></html>");
    expect(frameableAgentHtml(once)).toBe(once);
  });
});

describe("openAgentHtmlInNewTab", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens a script-free wrapper, noopener, whose sandboxed srcdoc carries the agent HTML exactly", async () => {
    let blob: Blob | undefined;
    vi.spyOn(URL, "createObjectURL").mockImplementation((b) => {
      blob = b as Blob;
      return "blob:x";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const agent = `<html><head></head><body><a title='"q" &amp; x' href="#a">a</a><script>alert(1)</script></body></html>`;

    openAgentHtmlInNewTab(agent);

    expect(open).toHaveBeenCalledWith("blob:x", "_blank", "noopener,noreferrer");
    const page = await new Promise<string>((res) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result));
      r.readAsText(blob!);
    });
    const doc = new DOMParser().parseFromString(page, "text/html");
    const frames = doc.querySelectorAll("iframe");
    expect(frames).toHaveLength(1);
    expect(frames[0].getAttribute("sandbox")).toBe(AGENT_HTML_SANDBOX);
    expect(frames[0].getAttribute("srcdoc")).toBe(frameableAgentHtml(agent));
    expect(doc.querySelectorAll("script")).toHaveLength(0);
  });
});

describe("source guard: agent HTML never gets the app origin", () => {
  const SRC = resolve(__dirname, "..");
  const strip = (s: string) =>
    s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
  const files = (readdirSync(SRC, { recursive: true }) as string[])
    .filter((f) => /\.tsx?$/.test(f) && !/\.(test|spec)\.tsx?$/.test(f))
    .map((f) => ({ path: f.split("\\").join("/"), code: strip(readFileSync(join(SRC, f), "utf8")) }));

  it("no frame gets allow-same-origin", () => {
    // DesignSystemDetailModal frames repo-owned content, not agent output: the static
    // components.html from skills/opendesign/design-systems/, or the output of
    // generateDesignSystemPreviewHtml, which emits no <script> (ISS-1067 analysis).
    const allowed = ["components/workflow/prototype/DesignSystemDetailModal.tsx"];
    const offenders = files
      .filter((f) => f.code.includes("allow-same-origin") && !allowed.includes(f.path))
      .map((f) => f.path);
    expect(offenders).toEqual([]);
  });

  it("no blob URL is opened in a new tab outside openAgentHtmlInNewTab", () => {
    // window.open calls allowed in a file that also creates blob URLs.
    const allowed: Record<string, number> = {
      "lib/agentHtml.ts": 1, // the helper
      "components/preview/PreviewPanel.tsx": 1, // handlePreviewOpen, non-HTML types; HTML goes through the helper
      "components/preview/AppBuilderPreview.tsx": 2, // the app's own /preview-fullscreen route; its blobs are ZIP downloads
      "components/workflow/prototype/DesignSystemDetailModal.tsx": 1, // repo-owned preview, as above
    };
    const offenders = files
      .filter((f) => f.code.includes("createObjectURL("))
      .map((f) => [f.path, (f.code.match(/window\.open\(/g) ?? []).length] as const)
      .filter(([path, n]) => n > (allowed[path] ?? 0));
    expect(offenders).toEqual([]);
  });
});
