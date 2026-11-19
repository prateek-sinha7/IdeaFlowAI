"use client";

/**
 * BuilderInput: the message box of the Builder panel (Req 4.2 to 4.7, 5.5, 5.6).
 *
 * Styled like the run chat's composer: one white bar with the text area on top
 * and, below it, the `toolbar` slot (the Model and Thinking picker) and one
 * action button: Stop while a turn runs, otherwise Send. The text area grows with its content up to
 * `MAX_BOX_HEIGHT_PX`, then scrolls.
 *
 * Controlled: the parent owns the text. Enter sends and Shift+Enter inserts a
 * newline. Enter during IME composition is left to the input method. Send is
 * enabled only when `canSend` says the server would accept the text (Req 4.5,
 * 4.6), and Stop appears while a turn runs (Req 5.5).
 *
 * The counter appears past 11,000 code points. Above 12,000 the text stays in
 * the box, Send is disabled, and the counter says why.
 */

import { ArrowRight, Square } from "lucide-react";
import {
  useId,
  useLayoutEffect,
  useRef,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import type { TurnView } from "./builderReducer";
import {
  MAX_MESSAGE_CODE_POINTS,
  MESSAGE_COUNTER_THRESHOLD,
  canSend,
  codePointLength,
} from "./builderSelectors";

/** The text area grows to this height, about six lines, then scrolls (the run chat's cap). */
export const MAX_BOX_HEIGHT_PX = 132;

export interface BuilderInputProps {
  value: string;
  onChange: (text: string) => void;
  /** Called only when `canSend` is true. The parent clears `value` after it accepts the message. */
  onSend: () => void;
  onStop: () => void;
  turn: TurnView;
  placeholder?: string;
  /** Extra reason to block Send, for example while the model list has not loaded. */
  sendDisabled?: boolean;
  /** Controls shown in the bar under the text, left of Send (the model picker). */
  toolbar?: ReactNode;
  /** Lets the parent focus the text area, for example after filling it with an example. */
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
}

const COUNT_FORMAT = new Intl.NumberFormat("en-US");

const ICON_BUTTON_BASE =
  "grid h-8 w-8 flex-none place-items-center rounded-[9px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 disabled:cursor-not-allowed";

export function BuilderInput({
  value,
  onChange,
  onSend,
  onStop,
  turn,
  placeholder = "Describe the workflow, or answer the builder's questions",
  sendDisabled = false,
  toolbar,
  textareaRef,
}: BuilderInputProps) {
  const inputId = useId();
  const counterId = `${inputId}-counter`;
  const ownRef = useRef<HTMLTextAreaElement | null>(null);
  const boxRef = textareaRef ?? ownRef;

  const count = codePointLength(value);
  const sendable = canSend(value, turn) && !sendDisabled;
  const tooLong = count > MAX_MESSAGE_CODE_POINTS;
  const showCounter = count > MESSAGE_COUNTER_THRESHOLD;
  const running = turn.kind === "running";

  // Grow with the text, shrink when it is removed. "auto" first so scrollHeight is the
  // content's height, not the previous one. No layout (jsdom, hidden) reports 0: skip.
  useLayoutEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    box.style.height = "auto";
    if (box.scrollHeight === 0) return;
    box.style.height = `${Math.min(box.scrollHeight, MAX_BOX_HEIGHT_PX)}px`;
  }, [value, boxRef]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    // Enter that confirms an IME candidate must reach the input method.
    if (event.nativeEvent.isComposing || event.keyCode === 229) {
      return;
    }
    event.preventDefault();
    if (sendable) {
      onSend();
    }
  };

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={inputId} className="sr-only">
        Message to the builder
      </label>
      <div
        className={`flex min-w-0 flex-col gap-2 rounded-[var(--radius-menu)] border bg-surface-white pb-[7px] pl-[13px] pr-[7px] pt-[10px] transition-[border-color,box-shadow] has-[textarea:focus-visible]:ring-2 ${
          tooLong
            ? "border-status-failed-border has-[textarea:focus-visible]:ring-status-failed/20"
            : "border-line-control has-[textarea:focus-visible]:border-brand has-[textarea:focus-visible]:ring-brand/15"
        }`}
      >
        <textarea
          ref={boxRef}
          id={inputId}
          rows={2}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          aria-invalid={tooLong}
          aria-describedby={showCounter ? counterId : undefined}
          style={{ maxHeight: MAX_BOX_HEIGHT_PX }}
          className="min-w-0 resize-none overflow-y-auto border-none bg-transparent pr-1.5 font-serif text-[13px] leading-[1.5] text-ink-900 placeholder:text-ink-300 focus-visible:outline-none"
        />
        <div className="flex min-w-0 items-center gap-1.5">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">{toolbar}</div>
          {running ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop"
              title="Stop the reply"
              className={`${ICON_BUTTON_BASE} border border-line-control bg-surface-card text-ink-700 hover:border-line-faint hover:bg-surface-warm`}
            >
              <Square className="h-3 w-3 fill-current" strokeWidth={2} aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              onClick={onSend}
              disabled={!sendable}
              aria-label="Send"
              title="Send"
              className={`${ICON_BUTTON_BASE} bg-brand text-white hover:bg-brand-pressed disabled:opacity-40 disabled:hover:bg-brand`}
            >
              <ArrowRight className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      <div className="flex min-h-[15px] items-center px-1">
        {showCounter ? (
          <p
            id={counterId}
            className={`min-w-0 flex-1 font-sans text-[11px] ${tooLong ? "text-status-failed-strong" : "text-ink-500"}`}
          >
            {tooLong
              ? `${COUNT_FORMAT.format(count)} / ${COUNT_FORMAT.format(MAX_MESSAGE_CODE_POINTS)}. Shorten the message to send it.`
              : `${COUNT_FORMAT.format(count)} / ${COUNT_FORMAT.format(MAX_MESSAGE_CODE_POINTS)}`}
          </p>
        ) : (
          <p className="min-w-0 flex-1 font-sans text-[10px] text-ink-400">
            Enter to send · Shift+Enter for a new line
          </p>
        )}
      </div>
    </div>
  );
}

export default BuilderInput;
