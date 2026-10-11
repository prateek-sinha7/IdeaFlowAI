import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";

// next/font/google needs the Next build pipeline (SWC font loader) and cannot
// run in jsdom. The mock mirrors the real return shape the layout consumes:
// `{ variable }` carrying the CSS-variable class name from the options.
vi.mock("next/font/google", () => ({
  Manrope: (options: { variable: string }) => ({ variable: `font-class${options.variable}` }),
  Heebo: (options: { variable: string }) => ({ variable: `font-class${options.variable}` }),
}));

// next/script depends on the Next head manager. The mock renders the inline
// script verbatim so its source and strategy are observable. The `children`
// string is injected as raw HTML to avoid React's text escaping of quotes,
// which would otherwise corrupt the JavaScript under inspection.
vi.mock("next/script", () => ({
  default: ({ id, strategy, children }: { id: string; strategy: string; children: string }) => (
    <script id={id} data-strategy={strategy} dangerouslySetInnerHTML={{ __html: children }} />
  ),
}));

import RootLayout, { metadata } from "./layout";

function renderLayout(children: ReactNode = <p>page body</p>): Document {
  const markup = renderToStaticMarkup(<RootLayout>{children}</RootLayout>);
  return new DOMParser().parseFromString(markup, "text/html");
}

describe("metadata", () => {
  it("declares the exact application title and description", () => {
    expect(metadata).toEqual({
      title: "VelocityAI",
      description:
        "Enterprise-grade AI delivery platform \u2014 transform ideas into structured deliverables through specialist AI agents",
    });
  });
});

describe("RootLayout", () => {
  // The markup is parsed with DOMParser, whose documents come from a different
  // realm than the jest-dom matchers' `instanceof HTMLElement` check, so these
  // assertions use the plain DOM API.
  it("renders an English-language <html> element with both font variables and base classes", () => {
    const doc = renderLayout();

    expect(doc.documentElement.getAttribute("lang")).toBe("en");
    expect(Array.from(doc.documentElement.classList)).toEqual([
      "font-class--font-manrope",
      "font-class--font-heebo",
      "h-full",
      "antialiased",
    ]);
  });

  it("renders a <body> carrying the page background and text-color classes", () => {
    const doc = renderLayout();

    expect(Array.from(doc.body.classList)).toEqual([
      "min-h-full",
      "flex",
      "flex-col",
      "bg-surface-white",
      "text-ink-900",
    ]);
  });

  it("renders its children inside the body through the provider stack", () => {
    const doc = renderLayout(<p>page body</p>);

    const paragraph = doc.body.querySelector("p");

    expect(paragraph?.textContent).toBe("page body");
  });

  it("renders different children when the page changes", () => {
    const doc = renderLayout(<main aria-label="other page">other</main>);

    expect(doc.body.querySelector("main")?.getAttribute("aria-label")).toBe("other page");
    expect(doc.body.textContent).not.toContain("page body");
  });

  it("injects the theme-init script before interactive hydration", () => {
    const doc = renderLayout();

    const script = doc.getElementById("theme-init");

    expect(script?.getAttribute("data-strategy")).toBe("beforeInteractive");
  });
});
describe("RootLayout theme-init script", () => {
  function runThemeInit(): void {
    const source = renderLayout().getElementById("theme-init")?.textContent ?? "";
    // Execute the layout's own inline script exactly as the browser would.
    new Function(source)();
  }

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("marks the document dark when the stored theme is 'dark'", () => {
    localStorage.setItem("velocity-theme", "dark");

    runThemeInit();

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("leaves the document theme unset when the stored theme is 'light'", () => {
    localStorage.setItem("velocity-theme", "light");

    runThemeInit();

    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("leaves the document theme unset when no theme is stored", () => {
    runThemeInit();

    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("does not throw when reading storage fails", () => {
    vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });

    expect(() => runThemeInit()).not.toThrow();
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });
});

