import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { SummaryRail } from "./SummaryRail";

describe("SummaryRail", () => {
  it("shows the agent count, review-gate count, strategy and estimated duration", () => {
    render(
      <SummaryRail agentCount={4} gateCount={2} strategy="Sequential" estDurationLabel="~12 min" />,
    );

    const rail = screen.getByTestId("composer-summary-rail");
    expect(within(rail).getByText("Summary")).toBeInTheDocument();
    expect(within(rail).getByText("4")).toBeInTheDocument();
    expect(within(rail).getByText("Agents")).toBeInTheDocument();
    expect(within(rail).getByText("2")).toBeInTheDocument();
    expect(within(rail).getByText("Review gates")).toBeInTheDocument();
    expect(rail).toHaveTextContent("StrategySequential");
    expect(within(rail).getByText("~12 min")).toBeInTheDocument();
  });

  it("shows zero counts for an empty workflow", () => {
    render(<SummaryRail agentCount={0} gateCount={0} strategy="Sequential" estDurationLabel="—" />);

    expect(screen.getAllByText("0")).toHaveLength(2);
  });

  it("does not show a fabricated cost row", () => {
    render(<SummaryRail agentCount={1} gateCount={0} strategy="Sequential" estDurationLabel="~1 min" />);

    expect(screen.queryByText(/cost/i)).not.toBeInTheDocument();
  });
});
