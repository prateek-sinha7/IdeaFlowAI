import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

import { ReviewGatePanel } from "./ReviewGatePanel";

// ─── Motion mock (same pattern as the other preview-area component tests) ──────
const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

const BASE = {
  agentId: "prototype-specify",
  agentName: "Spec Agent",
  output: "<spec>\n## Overview\nA thing.\n</spec>",
  gateKey: "run-1:prototype-specify",
};

function redoButton() {
  return screen.queryByRole("button", { name: /redo this step/i });
}

describe("ReviewGatePanel — Redo control (REDO-GATE T9/T13)", () => {
  it("does NOT render the Redo control when redoable is false (declared-gate fence)", () => {
    render(
      <ReviewGatePanel
        {...BASE}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRedo={vi.fn()}
        redoable={false}
      />,
    );
    expect(redoButton()).toBeNull();
    expect(screen.queryByLabelText(/additional instructions for redo/i)).toBeNull();
  });

  it("does NOT render the Redo control when redoable is true but no onRedo handler is wired", () => {
    render(
      <ReviewGatePanel
        {...BASE}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        redoable={true}
      />,
    );
    expect(redoButton()).toBeNull();
  });

  it("renders the Redo button + textarea only when onRedo AND redoable are set", () => {
    render(
      <ReviewGatePanel
        {...BASE}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRedo={vi.fn()}
        redoable={true}
      />,
    );
    expect(redoButton()).not.toBeNull();
    expect(screen.getByLabelText(/additional instructions for redo/i)).toBeTruthy();
  });

  it("calls onRedo(gateKey, instructions) with the typed text", () => {
    const onRedo = vi.fn();
    render(
      <ReviewGatePanel
        {...BASE}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRedo={onRedo}
        redoable={true}
      />,
    );
    fireEvent.change(screen.getByLabelText(/additional instructions for redo/i), {
      target: { value: "add dark mode" },
    });
    fireEvent.click(redoButton()!);
    expect(onRedo).toHaveBeenCalledTimes(1);
    expect(onRedo).toHaveBeenCalledWith(BASE.gateKey, "add dark mode");
  });

  it("calls onRedo(gateKey, \"\") when the instructions box is left empty", () => {
    const onRedo = vi.fn();
    render(
      <ReviewGatePanel
        {...BASE}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRedo={onRedo}
        redoable={true}
      />,
    );
    fireEvent.click(redoButton()!);
    expect(onRedo).toHaveBeenCalledWith(BASE.gateKey, "");
  });

  it("disables the controls after a Redo click — no double-send (T13/F8)", () => {
    const onRedo = vi.fn();
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <ReviewGatePanel
        {...BASE}
        onApprove={onApprove}
        onReject={onReject}
        onRedo={onRedo}
        redoable={true}
      />,
    );
    const redo = redoButton()!;
    fireEvent.click(redo);
    // Second click must be ignored (latched) ...
    fireEvent.click(redo);
    expect(onRedo).toHaveBeenCalledTimes(1);
    // ... and the other resolve actions are disabled too.
    expect((redo as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /approve & continue/i }));
    fireEvent.click(screen.getByRole("button", { name: /reject & cancel/i }));
    expect(onApprove).not.toHaveBeenCalled();
    expect(onReject).not.toHaveBeenCalled();
  });

  it("re-arms the controls when a fresh review_gate_ready re-opens the panel (new output)", () => {
    const onRedo = vi.fn();
    const { rerender } = render(
      <ReviewGatePanel
        {...BASE}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRedo={onRedo}
        redoable={true}
      />,
    );
    fireEvent.click(redoButton()!);
    expect((redoButton() as HTMLButtonElement).disabled).toBe(true);

    // The re-run re-emits review_gate_ready with NEW output → panel re-arms.
    rerender(
      <ReviewGatePanel
        {...BASE}
        output="<spec>\n## Overview\nA revised thing.\n</spec>"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRedo={onRedo}
        redoable={true}
      />,
    );
    expect((redoButton() as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(redoButton()!);
    expect(onRedo).toHaveBeenCalledTimes(2);
  });
});
