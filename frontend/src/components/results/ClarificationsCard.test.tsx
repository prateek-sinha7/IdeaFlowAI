import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ClarifyRound } from "@/types/index";
import { ClarificationsCard } from "./ClarificationsCard";

// ─────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D4) — ClarificationsCard real-DOM specs. Per-round
// Q&A + impact badges; a PROCEED run (no rounds) renders NOTHING; reopen
// loading is aria-busy.
// ─────────────────────────────────────────────────────────────────

const TWO_ROUNDS: ClarifyRound[] = [
  { round: 1, qa: [{ question_id: "q1", question_text: "Which auth method?", impact_level: "high", answer: "OAuth" }] },
  { round: 2, qa: [{ question_id: "q2", question_text: "Which database?", impact_level: "medium", answer: "Postgres" }] },
];

describe("ClarificationsCard — rounds", () => {
  it("renders per-round Q&A with emerald answers + high/medium impact badges", () => {
    render(<ClarificationsCard clarifications={TWO_ROUNDS} />);

    // Both questions + their emerald answer lines.
    expect(screen.getByText("Which auth method?")).toBeInTheDocument();
    expect(screen.getByText("✓ OAuth")).toBeInTheDocument();
    expect(screen.getByText("Which database?")).toBeInTheDocument();
    expect(screen.getByText("✓ Postgres")).toBeInTheDocument();

    // Impact badges — high = amber, medium = gray tier.
    expect(screen.getByText("★ High impact")).toBeInTheDocument();
    expect(screen.getByText("Medium impact")).toBeInTheDocument();

    // Grouped under Round 1 / Round 2 (round numbers rendered in count chips).
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
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
