/**
 * ADR-0056 — CapacityHistoryPanel controls. The panel is controlled, so the
 * tests assert on `onOptionsChange` and on what reaches the (mocked) API.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CapacityHistoryPanel, DEFAULT_HISTORY_VIEW } from "./CapacityHistoryPanel";
import type { HistoryViewOptions } from "./CapacityHistoryPanel";
import type { AdminCapacityHistory } from "@/lib/api";

const { adminGetCapacityHistory } = vi.hoisted(() => ({
  adminGetCapacityHistory: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ adminGetCapacityHistory }));

function buildHistory(overrides: Partial<AdminCapacityHistory> = {}): AdminCapacityHistory {
  return {
    instance_id: "i-a",
    range: "3h",
    period_seconds: 60,
    allowed_periods: [60, 300, 900, 3600],
    start: "2026-10-21T07:00:00Z",
    end: "2026-10-21T10:00:00Z",
    fetched_at: "2026-10-21T10:00:05Z",
    cached: false,
    cpu_threshold_percent: 75,
    mem_threshold_percent: 75,
    series: [],
    ...overrides,
  };
}

async function renderPanel(options: HistoryViewOptions = DEFAULT_HISTORY_VIEW) {
  const onOptionsChange = vi.fn();
  const utils = render(
    <CapacityHistoryPanel token="tok" instanceId="i-a" options={options} onOptionsChange={onOptionsChange} />,
  );
  await act(async () => {
    await Promise.resolve();
  });
  return { ...utils, onOptionsChange };
}

beforeEach(() => {
  adminGetCapacityHistory.mockReset();
  adminGetCapacityHistory.mockResolvedValue(buildHistory());
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
});

afterEach(() => {
  vi.clearAllTimers();
});

describe("CapacityHistoryPanel", () => {
  it("fetches the selected instance at the chosen range and period", async () => {
    await renderPanel({ range: "1d", periodSeconds: 300, timeZone: "local" });
    expect(adminGetCapacityHistory).toHaveBeenCalledWith("tok", "i-a", "1d", 300);
    expect(screen.getByText("i-a")).toBeInTheDocument();
  });

  it("marks the active range and resets the period to Auto when a range is picked", async () => {
    const user = userEvent.setup();
    const { onOptionsChange } = await renderPanel({ range: "3h", periodSeconds: 300, timeZone: "utc" });
    const group = screen.getByRole("group", { name: "Time range" });
    expect(screen.getByRole("button", { name: "3h" })).toHaveAttribute("aria-pressed", "true");
    expect(group).toContainElement(screen.getByRole("button", { name: "15d" }));

    await user.click(screen.getByRole("button", { name: "1w" }));
    expect(onOptionsChange).toHaveBeenCalledWith({ range: "1w", periodSeconds: null, timeZone: "utc" });
  });

  it("offers the backend's allowed periods for the range and reports a chosen one", async () => {
    const user = userEvent.setup();
    const { onOptionsChange } = await renderPanel();
    const select = screen.getByRole("combobox", { name: /resolution/i });
    expect(screen.getByRole("option", { name: "Auto (1 min)" })).toBeInTheDocument();
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Auto (1 min)",
      "1 min",
      "5 min",
      "15 min",
      "1 hour",
    ]);

    await user.selectOptions(select, "900");
    expect(onOptionsChange).toHaveBeenCalledWith({ ...DEFAULT_HISTORY_VIEW, periodSeconds: 900 });
  });

  it("returns to Auto when the Auto option is chosen", async () => {
    const user = userEvent.setup();
    const { onOptionsChange } = await renderPanel({ ...DEFAULT_HISTORY_VIEW, periodSeconds: 300 });
    await user.selectOptions(screen.getByRole("combobox", { name: /resolution/i }), "auto");
    expect(onOptionsChange).toHaveBeenCalledWith({ ...DEFAULT_HISTORY_VIEW, periodSeconds: null });
  });

  it("toggles between local time and UTC", async () => {
    const user = userEvent.setup();
    const { onOptionsChange } = await renderPanel();
    expect(screen.getByRole("button", { name: "Local" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "UTC" }));
    expect(onOptionsChange).toHaveBeenCalledWith({ ...DEFAULT_HISTORY_VIEW, timeZone: "utc" });
  });

  it("refetches on demand from the refresh button", async () => {
    const user = userEvent.setup();
    await renderPanel();
    expect(adminGetCapacityHistory).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Refresh charts" }));
    expect(adminGetCapacityHistory).toHaveBeenCalledTimes(2);
  });

  it("explains a failed refresh while keeping the charts", async () => {
    const user = userEvent.setup();
    await renderPanel();
    adminGetCapacityHistory.mockRejectedValueOnce(new Error("timeout"));
    await user.click(screen.getByRole("button", { name: "Refresh charts" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/refresh failed \(timeout\)/i);
    expect(screen.getByRole("heading", { name: "CPU utilization" })).toBeInTheDocument();
  });
});
