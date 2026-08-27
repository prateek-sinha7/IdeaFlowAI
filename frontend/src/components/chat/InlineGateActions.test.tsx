import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InlineGateActions } from "./InlineGateActions";

// ─── InlineGateActions — in-lane mirror of the Steps ReviewGatePanel ──────────
// Presentational + callback-driven. Every action fires the SAME approve_review
// channel the full panel uses (one backend command either way). Carries the
// four post-merge gate behaviors: KAN-101 update_specs, KAN-100 terminal fence,
// KAN-98 retained edit, KAN-95 reject-confirm — all SC-001-safe.

const OUTPUT = "<analysis>Readiness verdict: READY</analysis>";

function renderGate(overrides: Record<string, unknown> = {}) {
  const onApprove = vi.fn();
  const onReject = vi.fn();
  const onRedo = vi.fn();
  const onUpdateSpecs = vi.fn();
  const props = {
    agentId: "some-agent",
    agentName: "Analyzer",
    output: OUTPUT,
    gateKey: "gate-1",
    isPipelineRunning: true,
    redoable: true,
    updateSpecsEligible: true,
    onApprove,
    onReject,
    onRedo,
    onUpdateSpecs,
    ...overrides,
  };
  const utils = render(
    <InlineGateActions
      {...(props as React.ComponentProps<typeof InlineGateActions>)}
    />,
  );
  return { onApprove, onReject, onRedo, onUpdateSpecs, ...utils };
}

describe("InlineGateActions", () => {
  // ── "Ask first" IA ────────────────────────────────────────────────────────
  // The card opens with the ASK, then its actions, then the evidence. Two
  // primaries (approve + request changes) and two quiet channels (update-specs
  // + cancel) that are NO LONGER collapsed behind a disclosure: each of the four
  // is one channel, and hiding two of them behind a third that is itself a
  // channel made "Request changes" mean two different things. Every callback
  // and its arguments are unchanged — only what you click to reach them.
  it("leads with the ask, not a card label", () => {
    renderGate();
    expect(screen.getByTestId("chat-gate-actions")).toBeInTheDocument();
    expect(screen.getByText("Waiting on you")).toBeInTheDocument();
    // OUTPUT is an <analysis> artifact → the analysis ask (gateAsk, SC-001).
    expect(
      screen.getByRole("heading", { name: "Approve this analysis and continue?" }),
    ).toBeInTheDocument();
  });

  it("renders two primaries and two always-visible quiet channels", () => {
    renderGate();
    expect(screen.getByTestId("chat-gate-approve")).toHaveTextContent(
      "Approve the analysis",
    );
    expect(screen.getByTestId("chat-gate-request-changes")).toHaveTextContent(
      "Request changes",
    );
    // Reachable without opening anything first.
    expect(screen.getByTestId("chat-gate-update-specs")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-cancel")).toBeInTheDocument();
    // …but neither destructive/re-run action fires from that first click.
    expect(screen.queryByTestId("chat-gate-redo")).toBeNull();
    expect(screen.queryByTestId("chat-gate-reject")).toBeNull();
  });

  it("Request changes opens the composer for the redo channel", () => {
    renderGate();
    expect(screen.queryByLabelText("Additional instructions for redo")).toBeNull();
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
    expect(screen.getByLabelText("Additional instructions for redo")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-redo")).toHaveTextContent("Send it back");
  });

  it("renders the plan preview via the shared artifactPreview module", () => {
    // OUTPUT is an <analysis> artifact — the shared discriminator selects the
    // AnalysisPreview renderer (INV-12: one parser, reused here).
    renderGate();
    expect(screen.getByTestId("chat-gate-preview")).toBeInTheDocument();
  });

  it("approve fires onApprove once with undefined when there are no edits", () => {
    const { onApprove } = renderGate();
    fireEvent.click(screen.getByTestId("chat-gate-approve"));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onApprove).toHaveBeenCalledWith("gate-1", undefined);
  });

  it("approve carries the edited content when the user edits (retained edit)", () => {
    const { onApprove } = renderGate();
    fireEvent.click(screen.getByText("Edit"));
    const textarea = screen.getByLabelText("Edit gate content");
    fireEvent.change(textarea, { target: { value: "edited spec" } });
    fireEvent.click(screen.getByTestId("chat-gate-approve"));
    expect(onApprove).toHaveBeenCalledWith("gate-1", "edited spec");
  });

  it("KAN-98: retains the edit across a no-echo re-render (same output)", () => {
    const { rerender } = renderGate();
    fireEvent.click(screen.getByText("Edit"));
    fireEvent.change(screen.getByLabelText("Edit gate content"), {
      target: { value: "my edit" },
    });
    // A no-echo re-render with the SAME output must NOT wipe the edit.
    rerender(
      <InlineGateActions
        agentId="some-agent"
        agentName="Analyzer"
        output={OUTPUT}
        gateKey="gate-1"
        isPipelineRunning
        redoable
        updateSpecsEligible
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRedo={vi.fn()}
        onUpdateSpecs={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Edit gate content")).toHaveValue("my edit");
  });

  it("KAN-95: reject requires the confirm step before firing onReject", () => {
    const { onReject } = renderGate();
    fireEvent.click(screen.getByTestId("chat-gate-cancel"));
    // Not fired yet — confirm dialog is shown.
    expect(onReject).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("chat-gate-reject"));
    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onReject).toHaveBeenCalledWith("gate-1");
  });

  it("redo carries the free-text instructions on the shared channel", () => {
    const { onRedo } = renderGate();
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
    fireEvent.change(screen.getByLabelText("Additional instructions for redo"), {
      target: { value: "tighten spacing" },
    });
    fireEvent.click(screen.getByTestId("chat-gate-redo"));
    expect(onRedo).toHaveBeenCalledTimes(1);
    expect(onRedo).toHaveBeenCalledWith("gate-1", "tighten spacing");
  });

  it("KAN-101: update_specs fires onUpdateSpecs with the raw analysis report", () => {
    const { onUpdateSpecs } = renderGate();
    fireEvent.click(screen.getByTestId("chat-gate-update-specs"));
    expect(onUpdateSpecs).toHaveBeenCalledTimes(1);
    expect(onUpdateSpecs).toHaveBeenCalledWith("gate-1", OUTPUT);
  });

  it("KAN-100: renders nothing when the pipeline is not running (terminal fence)", () => {
    const { container } = renderGate({ isPipelineRunning: false });
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("chat-gate-actions")).toBeNull();
  });

  it("SC-001: hides only the update_specs channel when not eligible", () => {
    renderGate({ updateSpecsEligible: false });
    expect(screen.queryByTestId("chat-gate-update-specs")).toBeNull();
    // Approve stays primary; the other two change channels remain.
    expect(screen.getByTestId("chat-gate-approve")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-request-changes")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-cancel")).toBeInTheDocument();
  });

  it("hides Request changes entirely when the server did not mark the gate redoable", () => {
    // Redo is the ONLY channel behind that button now, so an un-redoable gate
    // must not offer it — a button that cannot send anything is worse than none.
    renderGate({ redoable: false });
    expect(screen.queryByTestId("chat-gate-request-changes")).toBeNull();
    // The remaining channels are untouched.
    expect(screen.getByTestId("chat-gate-approve")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-cancel")).toBeInTheDocument();
  });

  it("latches after one resolve action to prevent a double-send", () => {
    const { onApprove } = renderGate();
    const approve = screen.getByTestId("chat-gate-approve");
    fireEvent.click(approve);
    fireEvent.click(approve);
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  // ── ISS-052 — the doubled analyze gate ─────────────────────────────────────
  // One "Update the Specs" click opens the analyze gate twice more: once INSIDE the
  // revision pass and once after it returns. Both carry the SAME `gateKey` and the SAME
  // `output` bytes (live: 11,974 chars, sha1 0136795fc392, 5 ms apart), so the server's
  // `revisionCycle`/`revisionInFlight` pair is the only thing that tells them apart.

  it("ISS-052: re-arms the one-action latch when the same gate re-opens with a new stamp", () => {
    const onApprove = vi.fn();
    const props = {
      agentId: "some-agent",
      agentName: "Analyzer",
      output: OUTPUT,
      gateKey: "gate-1",
      isPipelineRunning: true,
      redoable: true,
      updateSpecsEligible: false,
      revisionCycle: 1,
      revisionInFlight: true,
      onApprove,
      onReject: vi.fn(),
      onRedo: vi.fn(),
      onUpdateSpecs: vi.fn(),
    };
    const { rerender } = render(<InlineGateActions {...props} />);

    fireEvent.click(screen.getByTestId("chat-gate-approve"));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("chat-gate-approve")).toBeDisabled();

    // The gate RE-OPENS: same output, same gateKey — only the stamp moved (the pass
    // returned). Without the stamp in the reset effect's deps the latch stays stuck and
    // the user is left staring at a live gate with every action disabled.
    rerender(
      <InlineGateActions
        {...props}
        revisionInFlight={false}
        updateSpecsEligible
      />,
    );
    expect(screen.getByTestId("chat-gate-approve")).not.toBeDisabled();
    fireEvent.click(screen.getByTestId("chat-gate-approve"));
    expect(onApprove).toHaveBeenCalledTimes(2);
  });

  it("ISS-052: names the revision cycle, and reads differently in-pass vs re-opened", () => {
    // A gate outside any revision cycle is UNCHANGED — no badge at all.
    const { unmount } = renderGate();
    expect(screen.queryByTestId("chat-gate-revision")).toBeNull();
    unmount();

    // Inside the pass.
    const inPass = renderGate({ revisionCycle: 1, revisionInFlight: true });
    const inPassText = screen.getByTestId("chat-gate-revision").textContent ?? "";
    expect(inPassText).toContain("1");
    inPass.unmount();

    // After the pass returned — same cycle, different reading.
    renderGate({ revisionCycle: 1, revisionInFlight: false });
    const reopenedText = screen.getByTestId("chat-gate-revision").textContent ?? "";
    expect(reopenedText).toContain("1");
    expect(reopenedText).not.toBe(inPassText);
  });

  it("SC-001: the source carries no workflow-name literal", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/InlineGateActions.tsx"),
      "utf8",
    );
    expect(
      /prototype-analyze|prototype-specify|"prototype"|od_ppt|app_builder/.test(
        src,
      ),
    ).toBe(false);
  });
});

// ─── Routed human gate — the human IS the router ─────────────────────────────
// The backend publishes a routed step's declared route.outcomes on the EXISTING
// generic carriers: artifact_kind="conditional_gate" + a JSON envelope on output.
// Free text was the defect — the answer must equal a declared outcome key exactly.
describe("InlineGateActions — conditional_gate choices", () => {
  const CHOICE_OUTPUT = JSON.stringify({
    prompt: "(awaiting language choice)",
    choices: ["english", "spanish", "dutch"],
  });

  it("renders one button per declared outcome, title-cased, and no Approve button", () => {
    renderGate({ artifactKind: "conditional_gate", output: CHOICE_OUTPUT });
    expect(screen.getByTestId("chat-gate-choice-english")).toHaveTextContent("English");
    expect(screen.getByTestId("chat-gate-choice-spanish")).toHaveTextContent("Spanish");
    expect(screen.getByTestId("chat-gate-choice-dutch")).toHaveTextContent("Dutch");
    expect(screen.queryByTestId("chat-gate-approve")).toBeNull();
  });

  it("sends the route decision as JSON on the SAME approve channel", () => {
    const { onApprove } = renderGate({
      artifactKind: "conditional_gate", output: CHOICE_OUTPUT,
    });
    fireEvent.click(screen.getByTestId("chat-gate-choice-dutch"));
    expect(onApprove).toHaveBeenCalledWith("gate-1", JSON.stringify({ decision: "dutch" }));
  });

  it("keeps Request changes (the reject channel) and drops the free-text Edit", () => {
    renderGate({ artifactKind: "conditional_gate", output: CHOICE_OUTPUT });
    expect(screen.getByTestId("chat-gate-request-changes")).toBeTruthy();
    expect(screen.queryByText("Edit")).toBeNull();
  });

  it("shows the human-readable prompt, never the JSON envelope", () => {
    renderGate({ artifactKind: "conditional_gate", output: CHOICE_OUTPUT });
    expect(screen.getByTestId("chat-gate-choice-prompt")).toHaveTextContent(
      "(awaiting language choice)",
    );
    expect(screen.queryByText(/"choices"/)).toBeNull();
  });

  it("latches after one click — a gate resolves once", () => {
    const { onApprove } = renderGate({
      artifactKind: "conditional_gate", output: CHOICE_OUTPUT,
    });
    fireEvent.click(screen.getByTestId("chat-gate-choice-dutch"));
    fireEvent.click(screen.getByTestId("chat-gate-choice-english"));
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it("DEGRADES to the normal card on a malformed envelope, never breaks", () => {
    renderGate({ artifactKind: "conditional_gate", output: "not json at all" });
    expect(screen.getByTestId("chat-gate-approve")).toBeTruthy();
    expect(screen.queryByTestId("chat-gate-choice-english")).toBeNull();
  });

  it("is DORMANT without the discriminator — an ordinary gate is untouched", () => {
    renderGate({ output: CHOICE_OUTPUT });   // no artifactKind
    expect(screen.getByTestId("chat-gate-approve")).toBeTruthy();
    expect(screen.queryByTestId("chat-gate-choice-english")).toBeNull();
  });
});

