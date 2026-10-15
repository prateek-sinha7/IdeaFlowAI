import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// mermaid 11 draws its "Syntax error in text" graphic into a container it appends
// to <body> (`d<id>`) and leaves it there when render() rejects. The mock does
// exactly that, so the test fails if MermaidBlock stops cleaning it up.
vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (id: string) => {
      const leftover = document.createElement("div");
      leftover.id = `d${id}`;
      leftover.textContent = "Syntax error in text";
      document.body.appendChild(leftover);
      throw new Error("Parse error on line 2");
    }),
  },
}));

import { MermaidBlock } from "./MermaidBlock";

describe("MermaidBlock", () => {
  it("a diagram that does not parse leaves nothing behind in <body>", async () => {
    render(<MermaidBlock chart={"sequenceDiagram\n A->>B: x; y"} />);

    await waitFor(() => expect(screen.getByTestId("mermaid-error")).toBeInTheDocument());
    expect(document.body.textContent).not.toContain("Syntax error in text");
    expect(document.querySelector('[id^="dmermaid-"]')).toBeNull();
  });
});
