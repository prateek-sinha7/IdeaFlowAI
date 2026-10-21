/**
 * ADR-0056 — TimeSeriesChart render, a11y and hover contract.
 *
 * Same a11y invariant as BarChart/DonutChart: one role="img" carrying the
 * caller's summary. Hover is driven with a stubbed getBoundingClientRect
 * (jsdom lays nothing out, so every rect is zero-sized by default).
 */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TimeSeriesChart } from "./TimeSeriesChart";
import type { TimeSeriesChartProps } from "./TimeSeriesChart";

const START = Date.UTC(2026, 9, 21, 10, 0);

function renderChart(overrides: Partial<TimeSeriesChartProps> = {}) {
  const props: TimeSeriesChartProps = {
    lines: [
      { key: "cpu_used", label: "Total", color: "var(--brand)", values: [10, 20, 30, 40, 50], detail: "50.0%" },
      { key: "cpu_user", label: "User", color: "var(--status-done)", values: [5, null, 15, 20, 25] },
    ],
    startMs: START,
    periodMs: 60_000,
    ariaLabel: "CPU utilization over the last 1h",
    formatValue: (v) => `${v}%`,
    formatTime: (ms) => `T+${(ms - START) / 60_000}m`,
    formatTick: (ms) => `tick-${(ms - START) / 60_000}`,
    yMax: 100,
    ...overrides,
  };
  return render(<TimeSeriesChart {...props} />);
}

function stubPlotRect(width = 400) {
  const plot = screen.getByTestId("time-series-plot");
  plot.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width, height: 100, right: width, bottom: 100, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
  return plot;
}

describe("TimeSeriesChart — render + a11y", () => {
  it("exposes one role='img' carrying the caller's summary", () => {
    renderChart();
    expect(screen.getByRole("img", { name: "CPU utilization over the last 1h" })).toBeInTheDocument();
  });

  it("draws one path per line and lists each line in the legend", () => {
    renderChart();
    expect(screen.getAllByTestId("time-series-line")).toHaveLength(2);
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
  });

  it("renders the y-axis ticks and the first/last x-axis ticks", () => {
    renderChart();
    for (const tick of ["0%", "25%", "50%", "75%", "100%"]) {
      expect(screen.getByText(tick)).toBeInTheDocument();
    }
    expect(screen.getByText("tick-0")).toBeInTheDocument();
    expect(screen.getByText("tick-4")).toBeInTheDocument();
  });

  it("draws a labelled threshold line when one is given", () => {
    renderChart({ threshold: { value: 75, label: "Gate 75%" } });
    expect(screen.getByTestId("time-series-threshold")).toBeInTheDocument();
    expect(screen.getByText("Gate 75%")).toBeInTheDocument();
  });

  it("scales the axis to the data and threshold when no yMax is given", () => {
    renderChart({
      yMax: undefined,
      lines: [{ key: "net_in", label: "In", color: "var(--brand)", values: [100, 3_700] }],
      formatValue: (v) => `${v} B/s`,
    });
    expect(screen.getByText("4000 B/s")).toBeInTheDocument();
  });

  it("renders nothing when every line is empty", () => {
    const { container } = renderChart({ lines: [{ key: "a", label: "A", color: "var(--brand)", values: [] }] });
    expect(container).toBeEmptyDOMElement();
  });

  it("uses only design tokens for colours", () => {
    const { container } = renderChart({ threshold: { value: 75, label: "Gate" } });
    expect(container.innerHTML).not.toMatch(/#[0-9a-f]{3,8}\b/i);
  });
});

describe("TimeSeriesChart — hover tooltip", () => {
  it("shows the hovered bucket's time and every line's value, with a dash for gaps", () => {
    renderChart();
    const plot = stubPlotRect(400);
    fireEvent.pointerMove(plot, { clientX: 100 }); // 25% → bucket 1
    const tooltip = screen.getByTestId("time-series-tooltip");
    expect(tooltip).toHaveTextContent("T+1m");
    expect(tooltip).toHaveTextContent("Total20%");
    expect(tooltip).toHaveTextContent("User—");
  });

  it("hides the tooltip when the pointer leaves", () => {
    renderChart();
    const plot = stubPlotRect(400);
    fireEvent.pointerMove(plot, { clientX: 400 });
    expect(screen.getByTestId("time-series-tooltip")).toHaveTextContent("T+4m");
    fireEvent.pointerLeave(plot);
    expect(screen.queryByTestId("time-series-tooltip")).not.toBeInTheDocument();
  });

  it("ignores pointer moves before the plot has been laid out", () => {
    renderChart();
    const plot = stubPlotRect(0);
    fireEvent.pointerMove(plot, { clientX: 50 });
    expect(screen.queryByTestId("time-series-tooltip")).not.toBeInTheDocument();
  });
});
