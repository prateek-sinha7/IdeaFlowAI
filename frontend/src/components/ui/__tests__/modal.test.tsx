/**
 * specs/014 — Modal primitive a11y + focus-management contract.
 *
 * The first real accessible dialog in this codebase; every prior modal was a
 * hand-rolled copy with no focus trap. Covers: role/aria wiring, Escape close,
 * backdrop-click close (+ opt-out), initial focus on mount, Tab/Shift+Tab
 * wrapping (the focus CYCLE — genuinely new behavior), focus RESTORE to the
 * trigger element on unmount, and the no-retired-hex token convention every
 * primitive in this directory is held to (see primitives.test.tsx).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "../Modal";

afterEach(() => {
  cleanup();
});

// Same retired-palette guard primitives.test.tsx already enforces on every
// other component in this directory (SC-1, D-15) — no hardcoded hex anywhere.
const RETIRED_HEX = /#1B2A4A|#2563eb/i;

describe("Modal — structure + aria wiring", () => {
  it("renders role=dialog, aria-modal=true, and aria-labelledby pointing at the rendered title", () => {
    render(
      <Modal onClose={vi.fn()} title="Service is busy">
        <p>Please try again shortly.</p>
      </Modal>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    const titleEl = document.getElementById(labelledBy!);
    expect(titleEl).toHaveTextContent("Service is busy");
  });

  it("renders the optional description under the title", () => {
    render(
      <Modal onClose={vi.fn()} title="T" description="extra context">
        <div />
      </Modal>,
    );
    expect(screen.getByText("extra context")).toBeInTheDocument();
  });

  it("contains no retired palette hex in rendered output", () => {
    const { container } = render(
      <Modal onClose={vi.fn()} title="T">
        <div />
      </Modal>,
    );
    expect(container.innerHTML).not.toMatch(RETIRED_HEX);
  });

  it("renders a close button labelled 'Close' by default", () => {
    render(
      <Modal onClose={vi.fn()} title="T">
        <div />
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("hides the close button when hideCloseButton is set", () => {
    render(
      <Modal onClose={vi.fn()} title="T" hideCloseButton>
        <div />
      </Modal>,
    );
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
  });
});

describe("Modal — closing", () => {
  it("Escape calls onClose", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} title="T">
        <div />
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clicking the × button calls onClose", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} title="T">
        <div />
      </Modal>,
    );
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clicking the backdrop (not the panel) calls onClose by default", () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal onClose={onClose} title="T">
        <div />
      </Modal>,
    );
    fireEvent.click(container.firstChild as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clicking INSIDE the panel does not call onClose", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} title="T">
        <button type="button">inner</button>
      </Modal>,
    );
    fireEvent.click(screen.getByRole("button", { name: "inner" }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closeOnBackdropClick=false disables the backdrop-click close", () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal onClose={onClose} title="T" closeOnBackdropClick={false}>
        <div />
      </Modal>,
    );
    fireEvent.click(container.firstChild as HTMLElement);
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("Modal — focus management", () => {
  it("moves focus to the first focusable element inside the panel on mount (the built-in Close button, which renders before children)", () => {
    render(
      <Modal onClose={vi.fn()} title="T">
        <button type="button">first</button>
        <button type="button">second</button>
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("with the close button hidden, focus moves to the first CHILD focusable element on mount", () => {
    render(
      <Modal onClose={vi.fn()} title="T" hideCloseButton>
        <button type="button">first</button>
        <button type="button">second</button>
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();
  });

  it("falls back to focusing the panel itself when there is no focusable content", () => {
    render(
      <Modal onClose={vi.fn()} title="T" hideCloseButton>
        <p>nothing focusable here</p>
      </Modal>,
    );
    expect(screen.getByRole("dialog")).toHaveFocus();
  });

  it("restores focus to the previously-focused element on unmount", () => {
    const trigger = document.createElement("button");
    trigger.textContent = "open modal";
    document.body.appendChild(trigger);
    trigger.focus();
    expect(trigger).toHaveFocus();

    const { unmount } = render(
      <Modal onClose={vi.fn()} title="T">
        <button type="button">inside</button>
      </Modal>,
    );
    expect(trigger).not.toHaveFocus();

    unmount();
    expect(trigger).toHaveFocus();

    document.body.removeChild(trigger);
  });
});

describe("Modal — focus cycle (Tab/Shift+Tab)", () => {
  it("Tab on the LAST focusable element wraps to the first (the close button)", async () => {
    const user = userEvent.setup();
    render(
      <Modal onClose={vi.fn()} title="T">
        <button type="button">only-inner</button>
      </Modal>,
    );
    // Close button is first (rendered before children), only-inner is last.
    screen.getByRole("button", { name: "only-inner" }).focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("Shift+Tab on the FIRST focusable element (Close) wraps to the last", async () => {
    const user = userEvent.setup();
    render(
      <Modal onClose={vi.fn()} title="T">
        <button type="button">only-inner</button>
      </Modal>,
    );
    screen.getByRole("button", { name: "Close" }).focus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "only-inner" })).toHaveFocus();
  });

  it("Tab cycles correctly across three focusable elements without escaping the panel", async () => {
    const user = userEvent.setup();
    render(
      <Modal onClose={vi.fn()} title="T">
        <button type="button">a</button>
        <button type="button">b</button>
      </Modal>,
    );
    // Order: Close, a, b.
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "a" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "b" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });
});

describe("Modal — body scroll lock", () => {
  it("locks body scroll while mounted and restores it on unmount", () => {
    const originalOverflow = document.body.style.overflow;
    const { unmount } = render(
      <Modal onClose={vi.fn()} title="T">
        <div />
      </Modal>,
    );
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe(originalOverflow);
  });
});
