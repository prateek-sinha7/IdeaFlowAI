/**
 * specs/014 §3.6/3.8 — CapacityMatrix render contract.
 *
 * Drives the REAL component with hand-built `CapacityMatrixState` values
 * (the discriminated union `useCapacityMatrix` produces) rather than mocking
 * the hook's internals — this is a pure presentational component, so the
 * only seam worth testing is "given this state, what renders".
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CapacityMatrix } from "./CapacityMatrix";
import type { CapacityMatrixState } from "@/hooks/useCapacityMatrix";
import type { AdminCapacityMatrix } from "@/lib/api";

// Same retired-palette guard every other primitive/consumer in this codebase
// is held to (SC-1, D-15) — no hardcoded hex anywhere in rendered output.
const RETIRED_HEX = /#1B2A4A|#2563eb/i;

function buildMatrix(overrides: Partial<AdminCapacityMatrix> = {}): AdminCapacityMatrix {
  return {
    collected_at: "2026-09-08T12:00:00Z",
    self_instance_id: "i-self0001",
    instance_source: "discovery",
    instances: [
      {
        instance_id: "i-self0001",
        instance_type: "t3.large",
        is_self: true,
        cpu_used_percent: 42.5,
        mem_used_percent: 55.0,
        cpu_user_percent: 30.0,
        cpu_system_percent: 12.5,
        cpu_iowait_percent: 0.0,
        reading_age_seconds: 12,
        stale: false,
      },
    ],
    gate: {
      enabled: true,
      state: "allowing",
      blind_reason: null,
      cpu_threshold_percent: 75,
      mem_threshold_percent: 75,
      signals: [],
      engaged_at: null,
      evaluated_at: "2026-09-08T12:00:00Z",
    },
    ...overrides,
  };
}

describe("CapacityMatrix — loading / error / empty triad", () => {
  it("renders a loading indicator", () => {
    render(<CapacityMatrix state={{ status: "loading" }} />);
    expect(screen.getByText(/loading capacity matrix/i)).toBeInTheDocument();
  });

  it("renders the error message", () => {
    const state: CapacityMatrixState = { status: "error", message: "network down" };
    render(<CapacityMatrix state={state} />);
    expect(screen.getByText("network down")).toBeInTheDocument();
  });

  it("renders an empty state when no instances have been collected yet", () => {
    const matrix = buildMatrix({ instances: [] });
    const state: CapacityMatrixState = { status: "empty", matrix };
    render(<CapacityMatrix state={state} />);
    expect(screen.getByText(/no instances collected yet/i)).toBeInTheDocument();
    // The gate summary strip still renders even with zero instances.
    expect(screen.getByText("Admission gate")).toBeInTheDocument();
  });
});

describe("CapacityMatrix — ready state, instance table", () => {
  function renderReady(overrides: Partial<AdminCapacityMatrix> = {}) {
    const matrix = buildMatrix(overrides);
    const state: CapacityMatrixState = { status: "ready", matrix };
    return render(<CapacityMatrix state={state} />);
  }

  it("renders the Instance / Type / State / CPU % / Memory % / Reading age / Gate columns", () => {
    renderReady();
    for (const name of ["Instance", "Type", "State", "CPU %", "Memory %", "Reading age", "Gate"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
  });

  it("renders the instance id, type, and CPU/memory readings", () => {
    renderReady();
    expect(screen.getByText("i-self0001")).toBeInTheDocument();
    expect(screen.getByText("t3.large")).toBeInTheDocument();
    expect(screen.getByText("42.5%")).toBeInTheDocument();
    expect(screen.getByText("55.0%")).toBeInTheDocument();
  });

  it("marks the self instance", () => {
    renderReady();
    expect(screen.getByText("This instance")).toBeInTheDocument();
  });

  it("shows the reading age", () => {
    renderReady();
    expect(screen.getByText(/12s ago/)).toBeInTheDocument();
  });

  it("shows the gate state badge (allowing)", () => {
    renderReady();
    expect(screen.getAllByText("Allowing").length).toBeGreaterThan(0);
  });

  it("shows a 'Blocking' gate with its hot signals", () => {
    renderReady({
      gate: {
        enabled: true,
        state: "blocking",
        blind_reason: null,
        cpu_threshold_percent: 75,
        mem_threshold_percent: 75,
        signals: [{ name: "cpu", value: 91.2, threshold: 75 }],
        engaged_at: "2026-09-08T11:59:00Z",
        evaluated_at: "2026-09-08T12:00:00Z",
      },
    });
    expect(screen.getAllByText("Blocking").length).toBeGreaterThan(0);
    expect(screen.getByText(/cpu 91.2% \(>= 75%\)/i)).toBeInTheDocument();
  });

  it("shows a 'Blind' gate with its reason and a 'Disabled' pill when the gate is off", () => {
    renderReady({
      gate: {
        enabled: false,
        state: "blind",
        blind_reason: "cpu and memory readings are both missing or stale",
        cpu_threshold_percent: 75,
        mem_threshold_percent: 75,
        signals: [],
        engaged_at: null,
        evaluated_at: "2026-09-08T12:00:00Z",
      },
    });
    expect(screen.getAllByText("Blind").length).toBeGreaterThan(0);
    expect(screen.getByText(/cpu and memory readings are both missing or stale/i)).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
  });

  it("marks an instance with no reading as 'Unknown'", () => {
    renderReady({
      instances: [
        {
          instance_id: "i-unknown1",
          instance_type: null,
          is_self: false,
          cpu_used_percent: null,
          mem_used_percent: null,
          cpu_user_percent: null,
          cpu_system_percent: null,
          cpu_iowait_percent: null,
          reading_age_seconds: null,
          stale: false,
        },
      ],
    });
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    // Missing readings render as an em dash, never a blank cell.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("marks a stale-but-previously-read instance as 'Stale', distinct from 'Unknown'", () => {
    renderReady({
      instances: [
        {
          instance_id: "i-stale0001",
          instance_type: "t3.medium",
          is_self: false,
          cpu_used_percent: 30,
          mem_used_percent: 40,
          cpu_user_percent: 20,
          cpu_system_percent: 10,
          cpu_iowait_percent: 0,
          reading_age_seconds: 900,
          stale: true,
        },
      ],
    });
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("shows the 'as of' collection timestamp unconditionally", () => {
    renderReady();
    expect(screen.getByText(/as of/i)).toBeInTheDocument();
  });

  it("renders instance ids as plain text when no selection handler is given", () => {
    renderReady();
    expect(screen.queryByRole("button", { name: /history for/i })).not.toBeInTheDocument();
  });

  it("renders a selection button per instance and reports clicks when selectable", () => {
    const onSelectInstance = vi.fn();
    const matrix = buildMatrix();
    render(
      <CapacityMatrix
        state={{ status: "ready", matrix }}
        selectedInstanceId="i-self0001"
        onSelectInstance={onSelectInstance}
      />,
    );
    const button = screen.getByRole("button", { name: "Show metrics history for i-self0001" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(button);
    expect(onSelectInstance).toHaveBeenCalledTimes(1);
    expect(onSelectInstance).toHaveBeenCalledWith("i-self0001");
  });

  it("contains no retired palette hex in rendered output", () => {
    const { container } = renderReady();
    expect(container.innerHTML).not.toMatch(RETIRED_HEX);
  });
});
