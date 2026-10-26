/**
 * ADR-0056 — CapacityHistoryCharts render contract: each chart card owns its
 * loading / error / "No data available" state, and the summary tiles show the
 * server-computed current / avg / max.
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { CapacityHistoryCharts } from "./CapacityHistoryCharts";
import type { CapacityHistoryState } from "@/hooks/useCapacityHistory";
import type { AdminCapacityHistory, CapacityHistorySeries } from "@/lib/api";

const CHART_TITLES = [
  "CPU utilization",
  "Memory used",
  "Disk used",
  "Disk I/O (EBS)",
  "Network",
  "Swap used",
  "Status check failed",
];

function series(overrides: Partial<CapacityHistorySeries> & Pick<CapacityHistorySeries, "key" | "group">): CapacityHistorySeries {
  return {
    label: overrides.key,
    unit: "percent",
    values: [10, 20, 30],
    summary: { latest: 30, min: 10, avg: 20, max: 30 },
    error: null,
    ...overrides,
  };
}

function buildHistory(seriesList: CapacityHistorySeries[]): AdminCapacityHistory {
  return {
    instance_id: "i-a",
    range: "3h",
    period_seconds: 60,
    allowed_periods: [60, 300, 900, 3600],
    start: "2026-10-21T07:00:00Z",
    end: "2026-10-21T07:03:00Z",
    fetched_at: "2026-10-21T07:03:05Z",
    cached: false,
    cpu_threshold_percent: 75,
    mem_threshold_percent: 80,
    series: seriesList,
  };
}

function fullHistory(): AdminCapacityHistory {
  return buildHistory([
    series({ key: "cpu_used", label: "Total", group: "cpu" }),
    series({ key: "cpu_user", label: "User", group: "cpu" }),
    series({ key: "mem_used", label: "Used", group: "memory", summary: { latest: 41.5, min: 40, avg: 41, max: 42.25 } }),
    series({ key: "disk_root_used", label: "/", group: "disk_used" }),
    series({ key: "disk_data_used", label: "/var/lib/postgresql", group: "disk_used" }),
    series({ key: "disk_read", label: "Read", group: "disk_io", unit: "bytes_per_second", values: [1000, 2000, 3000], summary: { latest: 3000, min: 1000, avg: 2000, max: 3000 } }),
    series({ key: "net_in", label: "In", group: "network", unit: "bytes_per_second" }),
    series({ key: "swap_used", label: "Used", group: "swap" }),
    series({ key: "status_check_failed", label: "Failed", group: "status", unit: "count", values: [0, 0, 1] }),
  ]);
}

function ready(history: AdminCapacityHistory): CapacityHistoryState {
  return { status: "ready", history, refreshing: false, refreshError: null };
}

function card(title: string): HTMLElement {
  return screen.getByRole("heading", { name: title }).parentElement as HTMLElement;
}

describe("CapacityHistoryCharts — per-chart states", () => {
  it("shows a loading state in every chart card while loading", () => {
    render(<CapacityHistoryCharts state={{ status: "loading" }} timeZone="utc" />);
    for (const title of CHART_TITLES) {
      expect(within(card(title)).getByText("Loading…")).toBeInTheDocument();
    }
  });

  it("shows the fetch error in every chart card when the request failed", () => {
    render(<CapacityHistoryCharts state={{ status: "error", message: "Unknown instance." }} timeZone="utc" />);
    expect(screen.getAllByRole("alert")).toHaveLength(CHART_TITLES.length);
    expect(within(card("Network")).getByText("Unknown instance.")).toBeInTheDocument();
  });

  it("draws a chart for every group with data", () => {
    render(<CapacityHistoryCharts state={ready(fullHistory())} timeZone="utc" />);
    expect(screen.getAllByRole("img")).toHaveLength(CHART_TITLES.length);
  });

  it("shows 'No data available' for a group whose series are all empty", () => {
    const history = fullHistory();
    history.series = history.series.map((s) =>
      s.group === "disk_io" ? { ...s, values: [null, null, null], summary: { latest: null, min: null, avg: null, max: null } } : s,
    );
    render(<CapacityHistoryCharts state={ready(history)} timeZone="utc" />);
    expect(within(card("Disk I/O (EBS)")).getByText("No data available")).toBeInTheDocument();
    expect(within(card("CPU utilization")).getByRole("img")).toBeInTheDocument();
  });

  it("errors only the card whose series all failed", () => {
    const history = fullHistory();
    history.series = history.series.map((s) =>
      s.group === "disk_io" ? { ...s, values: [null, null, null], error: "Could not list the instance's EBS volumes." } : s,
    );
    render(<CapacityHistoryCharts state={ready(history)} timeZone="utc" />);
    expect(within(card("Disk I/O (EBS)")).getByRole("alert")).toHaveTextContent("Could not list the instance's EBS volumes.");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("still draws a chart when only some of its series failed, and says so", () => {
    const history = fullHistory();
    history.series = history.series.map((s) =>
      s.key === "cpu_user" ? { ...s, values: [null, null, null], error: "CloudWatch query failed." } : s,
    );
    render(<CapacityHistoryCharts state={ready(history)} timeZone="utc" />);
    const cpu = card("CPU utilization");
    expect(within(cpu).getByRole("img")).toBeInTheDocument();
    expect(within(cpu).getByText(/some series failed to load/i)).toBeInTheDocument();
  });
});

describe("CapacityHistoryCharts — thresholds and labels", () => {
  it("draws the CPU and memory gate thresholds from the response", () => {
    render(<CapacityHistoryCharts state={ready(fullHistory())} timeZone="utc" />);
    expect(within(card("CPU utilization")).getByText("Gate 75%")).toBeInTheDocument();
    expect(within(card("Memory used")).getByText("Gate 80%")).toBeInTheDocument();
    expect(within(card("Network")).queryByTestId("time-series-threshold")).not.toBeInTheDocument();
  });

  it("summarises each chart in its accessible name", () => {
    render(<CapacityHistoryCharts state={ready(fullHistory())} timeZone="utc" />);
    const memory = within(card("Memory used")).getByRole("img");
    expect(memory).toHaveAccessibleName(/Memory used over the last 3h at 1 min resolution/);
    expect(memory).toHaveAccessibleName(/current 41\.5%, average 41%, maximum 42\.3%/);
    expect(memory).toHaveAccessibleName(/Gate threshold 80%/);
  });
});

describe("CapacityHistoryCharts — summary tiles", () => {
  it("shows current, average and maximum for the tiled series", () => {
    render(<CapacityHistoryCharts state={ready(fullHistory())} timeZone="utc" />);
    const memoryTile = screen.getByText("Memory").parentElement as HTMLElement;
    expect(within(memoryTile).getByText("41.5%")).toBeInTheDocument();
    expect(within(memoryTile).getByText("avg 41% · max 42.3%")).toBeInTheDocument();
  });

  it("shows placeholders while loading and dashes when a tiled series is missing", () => {
    const { rerender } = render(<CapacityHistoryCharts state={{ status: "loading" }} timeZone="utc" />);
    expect(screen.getAllByText("…")).toHaveLength(4);

    rerender(<CapacityHistoryCharts state={ready(buildHistory([]))} timeZone="utc" />);
    expect(screen.getAllByText("avg — · max —")).toHaveLength(4);
  });
});
