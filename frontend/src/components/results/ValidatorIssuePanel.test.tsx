import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ValidatorIssuePanel } from "./ValidatorIssuePanel";
import type { ValidationIssue } from "@/types/index";

describe("ValidatorIssuePanel", () => {
  it("renders the empty state when there are no issues", () => {
    render(<ValidatorIssuePanel issues={[]} />);
    expect(screen.getByText("Validator / Issues")).toBeInTheDocument();
    expect(screen.getByText(/No validator issues reported/)).toBeInTheDocument();
  });

  it("groups issues by severity in CRITICAL to LOW order with counts", () => {
    const issues = [
      { severity: "LOW", message: "low one" },
      { severity: "CRITICAL", message: "crit one" },
      { severity: "CRITICAL", message: "crit two" },
      { severity: "MEDIUM", message: "med one" },
      { severity: "HIGH", message: "high one" },
    ] as ValidationIssue[];
    const { container } = render(<ValidatorIssuePanel issues={issues} />);

    expect(screen.getByText("Critical (2)")).toBeInTheDocument();
    expect(screen.getByText("High (1)")).toBeInTheDocument();
    expect(screen.getByText("Medium (1)")).toBeInTheDocument();
    expect(screen.getByText("Low (1)")).toBeInTheDocument();
    expect(screen.queryByText(/No validator issues/)).not.toBeInTheDocument();

    const text = container.textContent ?? "";
    expect(text.indexOf("Critical (2)")).toBeLessThan(text.indexOf("High (1)"));
    expect(text.indexOf("High (1)")).toBeLessThan(text.indexOf("Medium (1)"));
    expect(text.indexOf("Medium (1)")).toBeLessThan(text.indexOf("Low (1)"));
    expect(screen.getByText("crit two")).toBeInTheDocument();
  });

  it("omits severity groups that have no issues", () => {
    render(
      <ValidatorIssuePanel
        issues={[{ severity: "HIGH", message: "only high" } as ValidationIssue]}
      />,
    );
    expect(screen.getByText("High (1)")).toBeInTheDocument();
    expect(screen.queryByText(/Critical \(/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Low \(/)).not.toBeInTheDocument();
  });

  it("shows validator name and warning marker when present", () => {
    const issues = [
      { severity: "MEDIUM", message: "m1", validator: "contrast" },
      { severity: "MEDIUM", message: "m2", validator: "spacing", warning: true },
      { severity: "LOW", message: "m3", warning: true },
      { severity: "LOW", message: "m4" },
    ] as ValidationIssue[];
    const { container } = render(<ValidatorIssuePanel issues={issues} />);

    expect(screen.getByText("contrast")).toBeInTheDocument();
    expect(screen.getByText(/spacing\s*· warning/)).toBeInTheDocument();
    expect(screen.getByText("· warning")).toBeInTheDocument();
    // m4 has neither validator nor warning: no meta line rendered.
    expect(container.querySelectorAll("p.text-\\[9px\\]")).toHaveLength(3);
  });
});
