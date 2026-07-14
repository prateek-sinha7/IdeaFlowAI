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
  it("renders exactly two primary buttons — Approve & build + Request changes", () => {
    renderGate();
    expect(screen.getByTestId("chat-gate-actions")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-approve")).toHaveTextContent(
      "Approve & build",
    );
    expect(screen.getByTestId("chat-gate-request-changes")).toHaveTextContent(
      "Request changes",
    );
    // The change channels are collapsed until "Request changes" is opened.
    expect(screen.queryByTestId("chat-gate-update-specs")).toBeNull();
    expect(screen.queryByText("Reject & cancel")).toBeNull();
    expect(screen.queryByText("Redo with instructions")).toBeNull();
  });

  it("Request changes reveals the preserved redo/update-specs/reject channels", () => {
    renderGate();
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
    expect(screen.getByTestId("chat-gate-update-specs")).toBeInTheDocument();
    expect(screen.getByText("Reject & cancel")).toBeInTheDocument();
    expect(screen.getByText("Redo with instructions")).toBeInTheDocument();
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
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
    fireEvent.click(screen.getByText("Reject & cancel"));
    // Not fired yet — confirm dialog is shown.
    expect(onReject).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("chat-gate-reject"));
    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onReject).toHaveBeenCalledWith("gate-1");
  });

  it("redo carries the free-text instructions on the shared channel", () => {
    const { onRedo } = renderGate();
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
    fireEvent.click(screen.getByText("Redo with instructions"));
    fireEvent.change(screen.getByLabelText("Additional instructions for redo"), {
      target: { value: "tighten spacing" },
    });
    fireEvent.click(screen.getByTestId("chat-gate-redo"));
    expect(onRedo).toHaveBeenCalledTimes(1);
    expect(onRedo).toHaveBeenCalledWith("gate-1", "tighten spacing");
  });

  it("KAN-101: update_specs fires onUpdateSpecs with the raw analysis report", () => {
    const { onUpdateSpecs } = renderGate();
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
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
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
    expect(screen.queryByTestId("chat-gate-update-specs")).toBeNull();
    // Approve stays primary; the other two change channels remain.
    expect(screen.getByTestId("chat-gate-approve")).toBeInTheDocument();
    expect(screen.getByText("Reject & cancel")).toBeInTheDocument();
    expect(screen.getByText("Redo with instructions")).toBeInTheDocument();
  });

  it("hides redo when the server did not mark the gate redoable", () => {
    renderGate({ redoable: false });
    fireEvent.click(screen.getByTestId("chat-gate-request-changes"));
    expect(screen.queryByText("Redo with instructions")).toBeNull();
  });

  it("latches after one resolve action to prevent a double-send", () => {
    const { onApprove } = renderGate();
    const approve = screen.getByTestId("chat-gate-approve");
    fireEvent.click(approve);
    fireEvent.click(approve);
    expect(onApprove).toHaveBeenCalledTimes(1);
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
