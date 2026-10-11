import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DesignSpecView } from "./DesignSpecView";

describe("DesignSpecView", () => {
  it("shows a loading message when source is null", () => {
    render(<DesignSpecView source={null} />);
    expect(screen.getByText("Loading spec…")).toBeInTheDocument();
  });

  it("shows a loading message when source is undefined", () => {
    render(<DesignSpecView source={undefined} />);
    expect(screen.getByText("Loading spec…")).toBeInTheDocument();
  });

  it("renders an empty code block for an empty string", () => {
    const { container } = render(<DesignSpecView source="" />);
    expect(container.querySelector("pre code")?.children).toHaveLength(0);
  });

  it("styles headings by depth, capping at level 4 sizes", () => {
    render(
      <DesignSpecView source={["# One", "## Two", "### Three", "#### Four", "###### Six"].join("\n")} />,
    );
    expect(screen.getByText("# One")).toHaveClass("text-[15px]");
    expect(screen.getByText("## Two")).toHaveClass("text-[13px]");
    expect(screen.getByText("### Three")).toHaveClass("text-[12px]");
    expect(screen.getByText("#### Four")).toHaveClass("text-[11.5px]");
    expect(screen.getByText("###### Six")).toHaveClass("text-[11.5px]");
  });

  it("styles blockquote, list, table, fence, blank and plain lines", () => {
    const src = ["> quote", "- item", "| a | b |", "```", "", "plain"].join("\n");
    render(<DesignSpecView source={src} />);
    expect(screen.getByText("> quote")).toHaveClass("italic");
    expect(screen.getByText("- item")).toHaveClass("text-gray-300");
    expect(screen.getByText("| a | b |")).toHaveClass("text-ink-400");
    expect(screen.getByText("```")).toHaveClass("text-ink-500");
    expect(screen.getByText("plain")).toHaveClass("text-gray-300");
    const blank = document.querySelectorAll("span.block")[4];
    expect(blank).toHaveClass("h-3");
  });

  it("renders bold, italic and code tokens", () => {
    render(<DesignSpecView source="a **bold** b *ital* c `code` d" />);
    expect(screen.getByText("bold")).toHaveClass("font-bold");
    expect(screen.getByText("ital")).toHaveClass("italic");
    expect(screen.getByText("code")).toHaveClass("font-mono");
  });

  it("renders a swatch for hex colors with the token text", () => {
    const { container } = render(<DesignSpecView source="Primary #ff00aa end" />);
    expect(screen.getByText("#ff00aa")).toHaveClass("text-amber-300");
    const swatch = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(swatch.style.backgroundColor).toBe("rgb(255, 0, 170)");
  });

  it("handles CRLF line endings", () => {
    render(<DesignSpecView source={"# Title\r\nbody"} />);
    expect(screen.getByText("# Title")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });
});
