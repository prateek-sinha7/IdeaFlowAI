import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D3) — StartingPointCard real-DOM specs. Variant
// selection is by the C1-parsed shape (SC-001), the Original-brief fetch is
// lazy (B3 dynamic-import idiom), and the card renders from props alone on the
// reopen mount (no pipelineState). Mocks the dynamic-imported @/lib/api.
// ─────────────────────────────────────────────────────────────────

const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockGetToken = vi.fn(() => "test-token");

vi.mock("@/lib/api", () => ({
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getToken: () => mockGetToken(),
}));

import { StartingPointCard } from "./StartingPointCard";

function makeRun(output: string): WorkflowRun {
  return {
    id: "root-1",
    title: "Root run",
    type: "prototype",
    status: "completed",
    input: "",
    output,
    createdAt: new Date().toISOString(),
    agentCount: 1,
    parentRunId: null,
    rootRunId: "root-1",
  };
}

beforeEach(() => {
  mockGetWorkflow.mockReset();
  mockGetToken.mockReturnValue("test-token");
});

describe("StartingPointCard — NORMAL variant", () => {
  it("renders the brief + an expandable attachment chip", () => {
    const input =
      "Design a landing page." +
      "\n\n=== Attached: spec.md ===\ncontent here\n=== End: spec.md ===";
    render(<StartingPointCard input={input} />);

    // Title + brief render from props alone.
    expect(screen.getByText("Starting point")).toBeInTheDocument();
    expect(screen.getAllByText("Design a landing page.").length).toBeGreaterThan(0);

    // Attachment chip renders with name + char count; expanding reveals content.
    const chip = screen.getByRole("button", { name: /attachment spec\.md/i });
    expect(chip.textContent).toMatch(/spec\.md/);
    expect(chip.textContent).toMatch(/chars/);
    expect(screen.queryByText("content here")).toBeNull();
    fireEvent.click(chip);
    expect(screen.getByText("content here")).toBeInTheDocument();
  });
});

describe("StartingPointCard — REVISION variant (lazy Original brief)", () => {
  it("shows the instruction as primary + fetches the original brief only on expand", async () => {
    mockGetWorkflow.mockResolvedValue(makeRun("The original v1 landing page brief."));
    const input = "=== REVISION REQUEST ===\nmake the header blue\n=== END REQUEST ===";
    render(<StartingPointCard input={input} originalBriefRootRunId="root-1" revisionParentVersion={1} />);

    // Instruction is the PRIMARY emphasis content.
    expect(screen.getByText("Revision Request")).toBeInTheDocument();
    expect(screen.getAllByText("make the header blue").length).toBeGreaterThan(0);

    // The Original-brief expander is present but NOT yet fetched.
    const expander = screen.getByRole("button", { name: /original brief version 1/i });
    expect(mockGetWorkflow).not.toHaveBeenCalled();

    // First expand → lazy fetch fires with the root id; the root brief renders.
    fireEvent.click(expander);
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith(expect.anything(), "root-1"));
    await waitFor(() =>
      expect(screen.getByText("The original v1 landing page brief.")).toBeInTheDocument(),
    );
  });

  it("omits the Original-brief expander when no root id is threaded", () => {
    const input = "=== REVISION REQUEST ===\nmake it pop\n=== END REQUEST ===";
    render(<StartingPointCard input={input} />);
    expect(screen.queryByRole("button", { name: /original brief version 1/i })).toBeNull();
  });
});

describe("StartingPointCard — reopen parity + empty", () => {
  it("renders from the input prop alone (no pipelineState anywhere)", () => {
    render(<StartingPointCard input="Just a plain brief with no markers." />);
    expect(screen.getByText("Starting point")).toBeInTheDocument();
    expect(screen.getAllByText("Just a plain brief with no markers.").length).toBeGreaterThan(0);
  });

  it("renders NOTHING when there is no brief/instruction/attachment/chain", () => {
    const { container } = render(<StartingPointCard input="" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("StartingPointCard — ND-10 not-retained image placeholder", () => {
  it("renders an honest placeholder for a retained:false image ref (no <img>)", () => {
    const { container } = render(
      <StartingPointCard
        input="Design a login screen."
        attachmentRefs={[{ kind: "image", retained: false }]}
      />,
    );

    // The honest "not retained" placeholder is shown …
    expect(screen.getByText(/image not retained/i)).toBeInTheDocument();
    expect(screen.getByText(/not stored after the run/i)).toBeInTheDocument();
    // … and NO <img> is rendered (bytes are never fetched/restored).
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders the placeholder even when the image ref is the only content", () => {
    render(<StartingPointCard input="" attachmentRefs={[{ kind: "image", retained: false }]} />);
    expect(screen.getByText("Starting point")).toBeInTheDocument();
    expect(screen.getByText(/image not retained/i)).toBeInTheDocument();
  });

  it("pluralizes when multiple image refs are not retained", () => {
    render(
      <StartingPointCard
        input="A brief."
        attachmentRefs={[
          { kind: "image", retained: false },
          { kind: "image", retained: false },
        ]}
      />,
    );
    expect(screen.getByText(/2 images not retained/i)).toBeInTheDocument();
  });

  it("shows NO placeholder when there are no image refs (no layout change)", () => {
    render(<StartingPointCard input="A plain brief with no attachments." />);
    expect(screen.queryByText(/not retained/i)).toBeNull();
  });

  it("shows NO placeholder for a retained image ref or a non-image ref", () => {
    render(
      <StartingPointCard
        input="A brief."
        attachmentRefs={[
          { kind: "image", retained: true },
          { kind: "document", retained: false },
        ]}
      />,
    );
    expect(screen.queryByText(/not retained/i)).toBeNull();
  });
});
