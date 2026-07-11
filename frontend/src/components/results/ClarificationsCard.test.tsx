import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { ClarifyRound } from "@/types/index";
import { ClarificationsCard } from "./ClarificationsCard";

// ─────────────────────────────────────────────────────────────────
// Phase 39 plan 02 — ClarificationsCard real-DOM specs, re-anchored to the mock
// composition: COLLAPSED by default; expanded, the rounds flatten into one Q&A
// list; only HIGH-impact questions get a "★ High impact" badge; answers render
// with a check icon (no "✓" literal). A PROCEED run renders NOTHING; reopen
// loading is aria-busy.
// ─────────────────────────────────────────────────────────────────

const TWO_ROUNDS: ClarifyRound[] = [
  { round: 1, qa: [{ question_id: "q1", question_text: "Which auth method?", impact_level: "high", answer: "OAuth" }] },
  { round: 2, qa: [{ question_id: "q2", question_text: "Which database?", impact_level: "medium", answer: "Postgres" }] },
];

describe("ClarificationsCard — rounds", () => {
  it("is collapsed by default, then reveals the flat Q&A on expand", () => {
    render(<ClarificationsCard clarifications={TWO_ROUNDS} />);

    // Collapsed by default — the header + subtitle show, the Q&A is hidden.
    expect(screen.getByText("Clarifications")).toBeInTheDocument();
    expect(screen.getByText("2 questions across 2 rounds · answered")).toBeInTheDocument();
    expect(screen.queryByText("Which auth method?")).toBeNull();

    // Expand.
    fireEvent.click(screen.getByRole("button", { name: /clarifications/i }));

    // Both questions + their answers (check icon + answer text, no "✓" literal).
    expect(screen.getByText("Which auth method?")).toBeInTheDocument();
    expect(screen.getByText("OAuth")).toBeInTheDocument();
    expect(screen.getByText("Which database?")).toBeInTheDocument();
    expect(screen.getByText("Postgres")).toBeInTheDocument();

    // Only HIGH-impact questions carry a badge (the mock badges high only).
    expect(screen.getByText("★ High impact")).toBeInTheDocument();
    expect(screen.queryByText("Medium impact")).toBeNull();
  });
});

describe("ClarificationsCard — PROCEED run renders nothing", () => {
  it("renders NOTHING for an empty clarifications array", () => {
    const { container } = render(<ClarificationsCard clarifications={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders NOTHING for undefined clarifications", () => {
    const { container } = render(<ClarificationsCard clarifications={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ClarificationsCard — reopen loading", () => {
  it("renders an aria-busy region + spinner while loading", () => {
    render(<ClarificationsCard clarifications={[]} loading />);
    const busy = document.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();
    expect(screen.getAllByText("Loading clarifications…").length).toBeGreaterThan(0);
  });
});
