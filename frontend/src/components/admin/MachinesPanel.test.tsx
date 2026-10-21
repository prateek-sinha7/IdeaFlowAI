/**
 * ADR-0056 — MachinesPanel: instance selection drives the history charts.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MachinesPanel, resolveSelectedInstance } from "./MachinesPanel";
import type { CapacityMatrixState } from "@/hooks/useCapacityMatrix";
import type { AdminCapacityInstance, AdminCapacityMatrix } from "@/lib/api";

const { adminGetCapacityHistory } = vi.hoisted(() => ({
  adminGetCapacityHistory: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ adminGetCapacityHistory }));

function instance(id: string, isSelf = false): AdminCapacityInstance {
  return {
    instance_id: id,
    instance_type: "m6i.xlarge",
    is_self: isSelf,
    cpu_used_percent: 10,
    mem_used_percent: 20,
    cpu_user_percent: 5,
    cpu_system_percent: 4,
    cpu_iowait_percent: 1,
    reading_age_seconds: 30,
    stale: false,
  };
}

function matrixState(instances: AdminCapacityInstance[]): CapacityMatrixState {
  const matrix: AdminCapacityMatrix = {
    collected_at: "2026-10-21T10:00:00Z",
    self_instance_id: instances.find((i) => i.is_self)?.instance_id ?? null,
    instance_source: "override",
    instances,
    gate: {
      enabled: true,
      state: "allowing",
      blind_reason: null,
      cpu_threshold_percent: 75,
      mem_threshold_percent: 75,
      signals: [],
      engaged_at: null,
      evaluated_at: "2026-10-21T10:00:00Z",
    },
  };
  return instances.length ? { status: "ready", matrix } : { status: "empty", matrix };
}

beforeEach(() => {
  adminGetCapacityHistory.mockReset();
  adminGetCapacityHistory.mockReturnValue(new Promise(() => {}));
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
});

describe("resolveSelectedInstance", () => {
  const instances = [instance("i-a"), instance("i-self", true), instance("i-c")];

  it("keeps a selection that is still listed", () => {
    expect(resolveSelectedInstance(instances, "i-c")).toBe("i-c");
  });

  it("falls back to this instance when nothing (or a vanished id) is selected", () => {
    expect(resolveSelectedInstance(instances, null)).toBe("i-self");
    expect(resolveSelectedInstance(instances, "i-gone")).toBe("i-self");
  });

  it("falls back to the first row when no row is this instance, and to null when empty", () => {
    expect(resolveSelectedInstance([instance("i-a"), instance("i-b")], null)).toBe("i-a");
    expect(resolveSelectedInstance([], null)).toBeNull();
  });
});

describe("MachinesPanel", () => {
  it("charts this instance by default and switches when another row is selected", async () => {
    const user = userEvent.setup();
    render(<MachinesPanel state={matrixState([instance("i-self", true), instance("i-other")])} token="tok" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(adminGetCapacityHistory).toHaveBeenLastCalledWith("tok", "i-self", "3h", null);
    expect(screen.getByRole("button", { name: /history for i-self/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /history for i-other/ }));
    expect(adminGetCapacityHistory).toHaveBeenLastCalledWith("tok", "i-other", "3h", null);
    expect(screen.getByRole("button", { name: /history for i-other/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /history for i-self/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("selects an instance when its row is clicked", async () => {
    const user = userEvent.setup();
    render(<MachinesPanel state={matrixState([instance("i-self", true), instance("i-other")])} token="tok" />);
    // Type cells in row order: [i-self, i-other]. Clicking a plain cell selects its row.
    const typeCells = screen.getAllByText("m6i.xlarge", { selector: "td" });
    await user.click(typeCells[1]);
    expect(adminGetCapacityHistory).toHaveBeenLastCalledWith("tok", "i-other", "3h", null);
  });

  it("keeps the chosen range when the selected instance changes", async () => {
    const user = userEvent.setup();
    render(<MachinesPanel state={matrixState([instance("i-self", true), instance("i-other")])} token="tok" />);
    await user.click(screen.getByRole("button", { name: "1w" }));
    await user.click(screen.getByRole("button", { name: /history for i-other/ }));
    expect(adminGetCapacityHistory).toHaveBeenLastCalledWith("tok", "i-other", "1w", null);
  });

  it("renders no history panel when no instances have been collected", () => {
    render(<MachinesPanel state={matrixState([])} token="tok" />);
    expect(screen.queryByRole("heading", { name: "Metrics history" })).not.toBeInTheDocument();
    expect(adminGetCapacityHistory).not.toHaveBeenCalled();
  });
});
