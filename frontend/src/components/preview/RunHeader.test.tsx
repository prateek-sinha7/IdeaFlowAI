import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { RunFamily } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// RunHeader (Phase 39, RUNUI-06/07) — the mock's right-column header bar across
// the settled / live / failed states. Isolated component specs: no PreviewPanel,
// no network. Asserts the state-driven composition + the client-only Share (ND-H)
// + the Version menu wiring.
// ─────────────────────────────────────────────────────────────────────────────

import { RunHeader } from "./RunHeader";

const t0 = new Date("2026-05-12T10:00:00Z").toISOString();
const t1 = new Date("2026-05-12T11:00:00Z").toISOString();

const family: RunFamily = {
  root_id: "root",
  members: [
    { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
    { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
  ],
};

beforeEach(() => {
  // A clipboard spy so the client-only Share path is observable.
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

describe("RunHeader — settled state", () => {
  it("renders the Version menu + Share + Download; hides the status badge", () => {
    render(
      <RunHeader
        runState="complete"
        family={family}
        activeRunId="r1"
        versionLabel="v2"
        onSelectVersion={() => {}}
        onShare={() => {}}
        onDownload={() => {}}
        canDownload
      />,
    );
    expect(screen.getByLabelText(/Version v2, choose version/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Share this run/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Download the deliverable/ })).toBeEnabled();
    // No live status badge in the settled state.
    expect(screen.queryByText(/streaming/i)).toBeNull();
    expect(screen.queryByText(/Run failed/i)).toBeNull();
  });

  it("Share button opens popover (no runId → legacy onShare path)", () => {
    const onShare = vi.fn();
    render(
      <RunHeader runState="complete" family={family} activeRunId="r1" versionLabel="v2" onShare={onShare} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Share this run/ }));
    // Popover opens — shows share panel heading.
    expect(screen.getByText(/Share deliverable/i)).toBeInTheDocument();
  });

  it("the Version menu lists the live family members; selecting one drives onSelectVersion", () => {
    const onSelectVersion = vi.fn();
    render(
      <RunHeader runState="complete" family={family} activeRunId="r1" versionLabel="v2" onSelectVersion={onSelectVersion} />,
    );
    fireEvent.click(screen.getByLabelText(/Version v2, choose version/));
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(2);
    // The active member (r1) is the selected option.
    expect(options[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.click(options[0]);
    expect(onSelectVersion).toHaveBeenCalledWith("root");
  });
});

describe("RunHeader — live (building) state", () => {
  it("renders a streaming status badge + a 'draft' version chip + a DISABLED Share; no Download", () => {
    render(
      <RunHeader
        runState="building"
        versionLabel="v1"
        currentAgentName="Build Agent"
        buildStepIndex={4}
        buildStepTotal={7}
        onShare={() => {}}
      />,
    );
    expect(screen.getByText(/streaming/i)).toBeInTheDocument();
    expect(screen.getByText(/building step 4 of 7/i)).toBeInTheDocument();
    expect(screen.getByText(/v1 draft/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Share this run/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Download the deliverable/ })).toBeNull();
    // No interactive Version menu while running.
    expect(screen.queryByLabelText(/choose version/)).toBeNull();
  });

  it("clarify state surfaces the 'Waiting on you' badge with the question count", () => {
    render(<RunHeader runState="clarify" versionLabel="v1" clarifyCount={6} />);
    expect(screen.getByText(/Waiting on you/)).toBeInTheDocument();
    expect(screen.getByText(/6 questions to answer before the build starts/)).toBeInTheDocument();
  });

  it("gate state surfaces the 'Paused · review gate' badge", () => {
    render(<RunHeader runState="gate" versionLabel="v1" />);
    expect(screen.getByText(/Paused · review gate/)).toBeInTheDocument();
  });
});

describe("RunHeader — failed state", () => {
  it("renders the red 'Run failed' badge + a 'partial' version chip; no Share / Download", () => {
    render(<RunHeader runState="terminal" failed versionLabel="v1" onShare={() => {}} onDownload={() => {}} />);
    expect(screen.getByText(/Run failed/)).toBeInTheDocument();
    expect(screen.getByText(/v1 · partial/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Share this run/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Download the deliverable/ })).toBeNull();
  });

  it("names the live failure location on the failed badge (ND-D reason)", () => {
    render(<RunHeader runState="terminal" failed versionLabel="v1" failureReason="Security reviewer" />);
    expect(screen.getByText(/Run failed · Security reviewer/)).toBeInTheDocument();
  });
});
