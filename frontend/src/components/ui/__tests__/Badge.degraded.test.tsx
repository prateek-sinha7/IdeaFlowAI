/**
 * Badge — degraded status contract (Task 11.9, Requirement 20).
 *
 * Validates that `degraded` is visually AND semantically distinguishable from
 * `completed`/`done`:
 *  - Label text is "Degraded" — never "Done", "Queued", or any other status
 *  - Token class uses the amber ramp (not the done/green ramp)
 *  - normalizeStatus("degraded") maps to "degraded", NOT "queued" (the fallback
 *    for unknown statuses) and NOT "done"
 *  - A `completed` run shows "Done" and the done (green) ramp — different from degraded
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "../Badge";

describe("Badge — degraded status (Req 20 distinctness)", () => {
  it("renders label 'Degraded' (not 'Done', not 'Queued')", () => {
    render(<Badge status="degraded" />);
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.queryByText("Done")).not.toBeInTheDocument();
    expect(screen.queryByText("Queued")).not.toBeInTheDocument();
  });

  it("uses the amber token class (text-status-amber) not the done/green class", () => {
    const { container } = render(<Badge status="degraded" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).toContain("text-status-amber");
    expect(badge.className).not.toContain("text-status-done");
    expect(badge.className).not.toContain("text-status-running");
  });

  it("completed/done renders 'Done' with text-status-done — distinct from degraded", () => {
    const { container } = render(<Badge status="completed" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.textContent).toBe("Done");
    expect(badge.className).toContain("text-status-done");
    expect(badge.className).not.toContain("text-status-amber");
  });

  it("degraded and completed produce different className and textContent", () => {
    const { container: degradedContainer } = render(<Badge status="degraded" />);
    const { container: doneContainer } = render(<Badge status="completed" />);
    const degradedBadge = degradedContainer.firstElementChild as HTMLElement;
    const doneBadge = doneContainer.firstElementChild as HTMLElement;
    expect(degradedBadge.textContent).not.toBe(doneBadge.textContent);
    expect(degradedBadge.className).not.toBe(doneBadge.className);
  });

  it("normalizes 'degraded' to 'degraded' (not fallback 'queued')", () => {
    // The fallback for unknown statuses is 'queued' (text-status-queued).
    // 'degraded' must NOT fall through to that branch.
    const { container } = render(<Badge status="degraded" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge.className).not.toContain("text-status-queued");
  });

  it("renders a custom label when provided, overriding the default", () => {
    render(<Badge status="degraded" label="Degraded (blocked)" />);
    expect(screen.getByText("Degraded (blocked)")).toBeInTheDocument();
  });

  it("degraded is semantically distinct from gate/cancelled (same amber token but different label)", () => {
    const { container: degradedC } = render(<Badge status="degraded" />);
    const { container: cancelledC } = render(<Badge status="cancelled" />);
    // Both use amber token — tokens may overlap but label text must differ
    const degradedText = (degradedC.firstElementChild as HTMLElement).textContent;
    const cancelledText = (cancelledC.firstElementChild as HTMLElement).textContent;
    expect(degradedText).not.toBe(cancelledText);
    // degraded renders "Degraded" not "Cancelled"
    expect(degradedText).toBe("Degraded");
    expect(cancelledText).toBe("Cancelled");
  });

  it("the 'Degraded' label text is present as accessible text content", () => {
    // Assistive tech reads the text content — assert it is present as text
    const { container } = render(<Badge status="degraded" />);
    expect(container.textContent).toBe("Degraded");
  });
});
