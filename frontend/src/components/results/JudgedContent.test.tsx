/**
 * JudgedContent — the kind is decided by the TEXT, never by the panel.
 *
 * Ported with the component from `impeccable-redesign`. The cases here are the
 * two failures that motivated it, in opposite directions: a document shown as
 * monospace source, and an agent transcript reflowed into one paragraph.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JudgedContent } from "./JudgedContent";

const kindOf = (value: string): string | null => {
  const { container } = render(<JudgedContent value={value} data-testid="jc" />);
  return container.querySelector("[data-testid='jc']")?.getAttribute("data-content-kind") ?? null;
};

describe("JudgedContent", () => {
  it("renders a real document as markdown, with its headings", () => {
    render(
      <JudgedContent value={"## Screens\n\n- Account # [text]\n- Status [dropdown: Any]\n"} />,
    );
    expect(screen.getByRole("heading", { name: "Screens" })).toBeInTheDocument();
    expect(screen.getByText("Account # [text]")).toBeInTheDocument();
  });

  it("keeps an agent transcript's line breaks instead of reflowing it", () => {
    // The live complaint: `.agents/NN-<step>.md` is prose with hard newlines and
    // no markdown structure. Through a markdown renderer it arrives as one
    // run-together paragraph, which is how a 300-line reader log became a wall.
    const transcript = "Reading pages 1-21.\nNow I'll read pages 6-10.\nContinue with 11-15.";
    const { container } = render(<JudgedContent value={transcript} data-testid="jc" />);
    const el = container.querySelector("[data-testid='jc']")!;

    expect(el.getAttribute("data-content-kind")).toBe("plain");
    expect(el.className).toContain("whitespace-pre-wrap");
    expect(el.querySelector("h1, h2, h3")).toBeNull();
  });

  it("gives code its own scrolled, unwrapped body and a language chip", () => {
    const { container } = render(
      <JudgedContent value={'{"documents_expected": 4, "gaps": []}'} data-testid="jc" />,
    );
    expect(container.querySelector("[data-testid='jc']")?.getAttribute("data-content-kind")).toBe(
      "code",
    );
    expect(screen.getByText("json")).toBeInTheDocument();
    expect(container.querySelector(".whitespace-pre")).not.toBeNull();
  });

  it("classifies each kind from the text alone", () => {
    expect(kindOf("<!DOCTYPE html><html></html>")).toBe("code");
    expect(kindOf("# Title\n\n- one\n- two")).toBe("markdown");
    expect(kindOf("A single sentence about the run.")).toBe("plain");
    expect(kindOf("")).toBe("plain");
  });

  it("drops the scroll cap when maxHeight is 0", () => {
    const { container } = render(
      <JudgedContent value={"# T\n\n- a\n- b"} maxHeight={0} data-testid="jc" />,
    );
    const el = container.querySelector("[data-testid='jc']") as HTMLElement;
    expect(el.style.maxHeight).toBe("");
  });
});
