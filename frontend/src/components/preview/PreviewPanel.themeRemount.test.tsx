/**
 * A theme change REMOUNTS the deliverable iframe; it never rewrites srcdoc in place.
 *
 * `useTheme` renders "light" once before its effect reads the real `data-theme`
 * (hooks/useTheme.ts:18 — deliberate, it avoids an SSR hydration mismatch). In dark mode
 * that made this iframe mount carrying the LIGHT document and then have its `srcdoc`
 * attribute rewritten ~40ms later with the dark one. Measured in Chrome 151 on run
 * b0642e0f, with a MutationObserver installed before the frame appeared:
 *
 *     t=36363  iframe added   srcdoc = 72,792   (light)
 *     t=36401  attr:srcdoc    srcdoc = 72,874   (dark, +82 = the injected <style>)
 *     t=36540  load           → frame painted NOTHING
 *
 * A fresh <iframe> with byte-identical attributes appended right beside it rendered the
 * deliverable perfectly, so the content was never the problem — the mutated element was.
 * It is also why clicking Markdown and back appeared to "fix" it: that unmounts this
 * component, and the remount creates the iframe with the final srcDoc already in place
 * (verified: one `iframe-added` at 72,874, one load, rendered).
 *
 * Only `custom`/unknown deliverables reach this component — `prototype` renders through a
 * blob URL and `ppt` through its own path, which is why those never went blank.
 *
 * jsdom does not paint iframes, so this cannot assert "blank". It asserts the MECHANISM
 * the fix relies on: React must replace the node rather than reuse it. Without `key`,
 * React reuses the element and only touches the attribute — the exact shape of the bug.
 */
import { describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import React from "react";
import { PreviewPanel } from "./PreviewPanel";

/**
 * The mock holds REAL React state and hands the setter out, because the flip has to be a
 * genuine re-render of PreviewPanel with every other prop unchanged — which is exactly
 * what the real hook does from its mount effect. Two cheaper harnesses were wrong in
 * opposite directions and both would have shipped a green test over broken code:
 * re-rendering with a fresh props literal tore the subtree down for an unrelated reason
 * (element replaced even with no key), and re-rendering the identical element made React
 * skip the subtree entirely (element never replaced even WITH the key).
 */
let flipTheme: ((t: "light" | "dark") => void) | null = null;
vi.mock("@/hooks/useTheme", async () => {
  const react = await import("react");
  return {
    useTheme: () => {
      const [theme, setTheme] = react.useState<"light" | "dark">("light");
      flipTheme = setTheme;
      return { theme, setTheme, toggleTheme: () => {} };
    },
  };
});

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy({}, {
    get: (_t, prop: string) =>
      ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
        React.createElement(
          prop,
          Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k))),
          children,
        ),
  }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div />,
  deriveDeliverableFilename: (_t: string, _c?: string, fallback?: string) => fallback || "deliverable",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div /> }));

const HTML = "<!doctype html><html><head></head><body><h1>Custom Output</h1></body></html>";
const DARK_MARKER = "color-scheme:dark";

// STABLE props object. Handing `rerender` a fresh literal each time makes React tear the
// subtree down for an unrelated reason, which hid the bug: the element got replaced even
// without the key and the assertion passed against broken code. The only thing that may
// differ between the two renders is the theme.
const DELIVERABLE = { mimetype: "text/html", filename: "prototype.html", content: HTML };
const PANEL = (
  <PreviewPanel workflowType={"custom" as never} isStreaming={false} genericDeliverable={DELIVERABLE} />
);

function renderPanel() {
  return render(PANEL);
}

describe("the deliverable iframe across a theme change", () => {
  it("is a DIFFERENT element after the theme resolves — not the same one rewritten", () => {
    const { container } = renderPanel();
    const before = container.querySelector("iframe");
    expect(before).not.toBeNull();
    expect(before!.getAttribute("srcdoc")).not.toContain(DARK_MARKER);

    act(() => flipTheme!("dark"));

    const after = container.querySelector("iframe");
    expect(after).not.toBeNull();
    // THE ASSERTION. Without `key={theme}` React reuses the node and only rewrites the
    // attribute — `before` and `after` are the same object, and Chrome paints nothing.
    expect(after).not.toBe(before);
    expect(before!.isConnected).toBe(false);
  });

  it("the element it mounts with already carries the final document", () => {
    const { container } = renderPanel();
    act(() => flipTheme!("dark"));
    const iframe = container.querySelector("iframe")!;
    expect(iframe.getAttribute("srcdoc")).toContain(DARK_MARKER);
    expect(iframe.getAttribute("srcdoc")).toContain("Custom Output");
  });

  it("keeps the sandbox contract across the remount (T-18-05)", () => {
    const { container } = renderPanel();
    act(() => flipTheme!("dark"));
    const iframe = container.querySelector("iframe")!;
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("sandbox") || "").not.toContain("allow-same-origin");
  });
});
