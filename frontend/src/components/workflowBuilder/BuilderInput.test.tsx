import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { BuilderInput, type BuilderInputProps } from "./BuilderInput";
import type { RunningTurnView, TurnView } from "./builderReducer";

const IDLE: TurnView = { kind: "idle" };

const RUNNING: RunningTurnView = {
  kind: "running",
  turnId: "t1",
  origin: "this_tab",
  stage: "thinking",
  label: "Thinking",
  startedAt: 0,
  lastSeq: 0,
  activity: [],
  steps: [],
  warnings: [],
  pendingDraft: null,
};

/** Controlled host, because the component does not hold its own text. */
function Host(props: Partial<BuilderInputProps> & { initial?: string }) {
  const { initial = "", onChange, ...rest } = props;
  const [value, setValue] = useState(initial);
  return (
    <BuilderInput
      value={value}
      onChange={(text) => {
        setValue(text);
        onChange?.(text);
      }}
      onSend={vi.fn()}
      onStop={vi.fn()}
      turn={IDLE}
      {...rest}
    />
  );
}

const box = () => screen.getByRole("textbox", { name: "Message to the builder" });

describe("BuilderInput", () => {
  it("sends on Enter when the text is sendable", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Host initial="Build a report" onSend={onSend} />);
    await user.type(box(), "{Enter}");
    expect(onSend).toHaveBeenCalledOnce();
  });

  it("inserts a newline on Shift+Enter and does not send", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Host onSend={onSend} />);
    await user.type(box(), "one{Shift>}{Enter}{/Shift}two");
    expect(box()).toHaveValue("one\ntwo");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("does not send on Enter during IME composition", () => {
    const onSend = vi.fn();
    render(<Host initial="にほん" onSend={onSend} />);
    fireEvent.keyDown(box(), { key: "Enter", isComposing: true });
    fireEvent.keyDown(box(), { key: "Enter", keyCode: 229 });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("does not send on Enter when the text is blank", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Host initial="   " onSend={onSend} />);
    await user.type(box(), "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("enables Send for text and calls onSend from the button", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Host initial="Hello" onSend={onSend} />);
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledOnce();
  });

  it("disables Send while sendDisabled is set", () => {
    render(<Host initial="Hello" sendDisabled />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("shows Stop and disables Send while a turn runs", async () => {
    const user = userEvent.setup();
    const onStop = vi.fn();
    render(<Host initial="Hello" turn={RUNNING} onStop={onStop} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("hides Stop when no turn runs", () => {
    render(<Host initial="Hello" />);
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  });

  it("shows no counter at 11,000 code points", () => {
    render(<Host initial={"a".repeat(11_000)} />);
    expect(screen.queryByText(/\/ 12,000/)).toBeNull();
  });

  it("shows the counter past 11,000 code points and keeps Send enabled", () => {
    render(<Host initial={"a".repeat(11_001)} />);
    expect(screen.getByText("11,001 / 12,000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(box()).toHaveAttribute("aria-invalid", "false");
  });

  it("counts code points, not UTF-16 units", () => {
    // 6,000 emoji are 12,000 UTF-16 units but only 6,000 code points.
    render(<Host initial={"😀".repeat(6_000)} />);
    expect(screen.queryByText(/\/ 12,000/)).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("blocks Send above 12,000 code points, keeps the text and says why", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const text = "a".repeat(12_001);
    render(<Host initial={text} onSend={onSend} />);
    expect(screen.getByText(/12,001 \/ 12,000\. Shorten the message/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(box()).toHaveAttribute("aria-invalid", "true");
    expect(box()).toHaveValue(text);
    await user.type(box(), "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("renders the toolbar in the message bar beside Send", () => {
    render(<Host toolbar={<button type="button">Model chip</button>} />);
    const chip = screen.getByRole("button", { name: "Model chip" });
    const send = screen.getByRole("button", { name: "Send" });
    expect(chip.compareDocumentPosition(send) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the keyboard hint until the counter takes its place", () => {
    const { unmount } = render(<Host initial="Hello" />);
    expect(screen.getByText("Enter to send · Shift+Enter for a new line")).toBeInTheDocument();
    unmount();
    render(<Host initial={"a".repeat(11_001)} />);
    expect(screen.queryByText("Enter to send · Shift+Enter for a new line")).toBeNull();
    expect(screen.getByText("11,001 / 12,000")).toBeInTheDocument();
  });

  it("lets the parent focus the box through textareaRef", () => {
    const ref = { current: null as HTMLTextAreaElement | null };
    render(<Host textareaRef={ref} />);
    ref.current?.focus();
    expect(box()).toHaveFocus();
  });
});
