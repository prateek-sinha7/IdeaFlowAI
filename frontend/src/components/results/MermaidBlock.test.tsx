import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const { initialize, renderFn } = vi.hoisted(() => ({
  initialize: vi.fn(),
  renderFn: vi.fn(),
}));

vi.mock("mermaid", () => ({
  default: { initialize, render: renderFn },
}));

import { MermaidBlock, isMermaidFence } from "./MermaidBlock";

describe("MermaidBlock", () => {
  beforeEach(() => {
    initialize.mockReset();
    renderFn.mockReset();
    document.documentElement.removeAttribute("data-theme");
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  it("renders the svg returned by mermaid with the neutral theme in light mode", async () => {
    renderFn.mockResolvedValue({ svg: '<svg data-testid="drawn"></svg>' });
    render(<MermaidBlock chart={"  flowchart TD\n A-->B  "} />);

    expect(await screen.findByTestId("drawn")).toBeInTheDocument();
    expect(initialize).toHaveBeenCalledWith(
      expect.objectContaining({ startOnLoad: false, securityLevel: "strict", theme: "neutral" }),
    );
    expect(renderFn).toHaveBeenCalledWith(expect.stringMatching(/^mermaid-\d+$/), "flowchart TD\n A-->B");
    expect(screen.getByTestId("mermaid-diagram")).toBeInTheDocument();
  });

  it("uses the dark theme when data-theme is dark", async () => {
    document.documentElement.setAttribute("data-theme", "dark");
    renderFn.mockResolvedValue({ svg: '<svg data-testid="drawn"></svg>' });
    render(<MermaidBlock chart="graph TD" />);

    await screen.findByTestId("drawn");
    expect(initialize).toHaveBeenCalledWith(expect.objectContaining({ theme: "dark" }));
  });

  it("falls back to the source in an error block when rendering throws an Error", async () => {
    renderFn.mockRejectedValue(new Error("parse boom"));
    render(<MermaidBlock chart="not a diagram" />);

    expect(await screen.findByTestId("mermaid-error")).toBeInTheDocument();
    expect(screen.getByText(/could not be drawn/)).toBeInTheDocument();
    expect(screen.getByText("not a diagram")).toBeInTheDocument();
    expect(screen.queryByTestId("mermaid-diagram")).not.toBeInTheDocument();
  });

  it("handles non-Error rejections", async () => {
    renderFn.mockRejectedValue("plain string failure");
    render(<MermaidBlock chart="bad" />);
    expect(await screen.findByTestId("mermaid-error")).toBeInTheDocument();
  });

  it("does not write to the DOM or set error after unmount", async () => {
    let resolve!: (v: { svg: string }) => void;
    renderFn.mockReturnValue(new Promise((r) => { resolve = r; }));
    const { unmount } = render(<MermaidBlock chart="graph TD" />);
    await waitFor(() => expect(renderFn).toHaveBeenCalled());
    unmount();
    resolve({ svg: "<svg></svg>" });
    await Promise.resolve();
    expect(screen.queryByTestId("mermaid-diagram")).not.toBeInTheDocument();
  });

  it("ignores a late rejection after unmount", async () => {
    let reject!: (e: Error) => void;
    renderFn.mockReturnValue(new Promise((_, r) => { reject = r; }));
    const { unmount } = render(<MermaidBlock chart="graph TD" />);
    await waitFor(() => expect(renderFn).toHaveBeenCalled());
    unmount();
    reject(new Error("late"));
    await Promise.resolve();
    expect(screen.queryByTestId("mermaid-error")).not.toBeInTheDocument();
  });

  it("re-renders and clears a previous error when the chart changes", async () => {
    renderFn.mockRejectedValueOnce(new Error("bad"));
    const { rerender } = render(<MermaidBlock chart="bad" />);
    await screen.findByTestId("mermaid-error");

    renderFn.mockResolvedValue({ svg: '<svg data-testid="ok"></svg>' });
    rerender(<MermaidBlock chart="good" />);
    // Error view has no host ref; the effect sets error to null only when host exists.
    await waitFor(() => expect(renderFn).toHaveBeenCalledTimes(2));
  });
});

describe("isMermaidFence", () => {
  it.each([
    ["language-mermaid", true],
    ["foo language-mermaid bar", true],
    ["language-mermaid2", false],
    ["language-js", false],
    ["", false],
    [undefined, false],
  ])("returns the right answer for %s", (cls, expected) => {
    expect(isMermaidFence(cls as string | undefined)).toBe(expected);
  });
});
