"use client";

/**
 * BuilderModelPicker: the labelled Model and Thinking selects of the AI Workflow
 * Builder panel (Req 6.1 to 6.5; design 3.10).
 *
 * Two compact chips, each a visible label and a native select, sized to sit in
 * the message bar's toolbar. Native selects keep the keyboard and screen-reader
 * behaviour of the platform.
 *
 * Presentational. The options come from the `GET /models` response carried in
 * `state` (no model list lives in the frontend, Req 6.2), and the Thinking
 * options from `thinkingOptions` in `modelPicker.ts`: the selected model's
 * `reasoning_levels` labelled with `effortLabel`, hidden for
 * `reasoning_mode: none` (Req 6.3, 6.4). Opus 4.6 lists `none` and `on`, which
 * `effortLabel` shows as Off and On (Req 6.5). Pair it with
 * `useBuilderModelPicker`, which loads the list and keeps the choice.
 *
 * A failed load shows an error with Retry instead of the selects; the parent
 * disables Send while `choice` is `null`.
 */

import { ChevronDown } from "lucide-react";
import { useId } from "react";

import type { BuilderModelsState } from "@/hooks/useBuilderModelPicker";

import {
  thinkingOptions,
  type PickerChoice,
  type PickerNote,
} from "./modelPicker";

export interface BuilderModelPickerProps {
  state: BuilderModelsState;
  choice: PickerChoice | null;
  note: PickerNote | null;
  onModelChange: (modelId: string) => void;
  onEffortChange: (effort: string) => void;
  onRetry: () => void;
  /** Disables both selects, for example while a turn runs. */
  disabled?: boolean;
}

const CHIP_CLASS =
  "relative inline-flex min-w-0 shrink items-center rounded-[var(--radius-pill)] border border-line-control bg-surface-warm transition-colors hover:border-line-faint has-[select:focus-visible]:border-brand has-[select:focus-visible]:ring-2 has-[select:focus-visible]:ring-brand/15";
const CHIP_LABEL_CLASS =
  "flex-none cursor-pointer pl-2 font-sans text-[11px] font-medium text-ink-500";
// The select stays transparent so the chip's rounded background shows through.
// Each option sets its own colours: the native dropdown otherwise falls back to
// the system white while the option text inherits the light dark-theme colour.
const CHIP_SELECT_CLASS =
  "min-w-0 cursor-pointer appearance-none truncate bg-transparent py-[5px] pr-5 font-sans text-[11px] font-semibold text-ink-900 focus-visible:outline-none disabled:cursor-not-allowed";
const OPTION_CLASS = "bg-surface-warm text-ink-900";
const STATUS_TEXT_CLASS = "font-sans text-[11px] text-ink-500";

export function BuilderModelPicker({
  state,
  choice,
  note,
  onModelChange,
  onEffortChange,
  onRetry,
  disabled = false,
}: BuilderModelPickerProps) {
  const baseId = useId();
  const modelId = `${baseId}-model`;
  const thinkingId = `${baseId}-thinking`;

  if (state.status === "loading") {
    return (
      <p role="status" className={STATUS_TEXT_CLASS}>
        Loading models…
      </p>
    );
  }

  if (state.status === "error") {
    return (
      <div
        role="alert"
        className="flex min-w-0 items-center gap-2 font-sans text-[11px] text-ink-700"
      >
        <span className="min-w-0">Could not load the model list.</span>
        <button
          type="button"
          onClick={onRetry}
          className="flex-none rounded-[6px] px-1 font-semibold text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          Retry
        </button>
      </div>
    );
  }

  const { models } = state.response;
  if (choice === null) {
    return (
      <p className={STATUS_TEXT_CLASS}>No models are available on your plan.</p>
    );
  }

  const options = thinkingOptions(choice.modelId, models);
  const chosenLabel =
    models.find((m) => m.id === choice.modelId)?.label ?? choice.modelId;
  const chip = `${CHIP_CLASS} ${disabled ? "opacity-50" : ""}`;

  return (
    <div className="flex w-full min-w-0 flex-col gap-1.5">
      {/* One row that never wraps: when the Stop button appears beside Send the chips
          shrink (their selects truncate) instead of Thinking dropping to a second row. */}
      <div className="flex min-w-0 flex-nowrap items-center gap-1.5">
        <div className={chip}>
          {/* The model's name says what this chip is, as in other chat composers; the
            label stays for screen readers. Thinking keeps a visible label because
            its values (Low, On, ...) do not. */}
          <label htmlFor={modelId} className="sr-only">
            Model
          </label>
          <select
            id={modelId}
            value={choice.modelId}
            disabled={disabled}
            onChange={(e) => onModelChange(e.target.value)}
            className={`${CHIP_SELECT_CLASS} max-w-[150px] pl-2.5`}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id} className={OPTION_CLASS}>
                {m.label}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-2 h-3 w-3 text-ink-400"
            aria-hidden="true"
          />
        </div>
        {options.length > 0 && (
          <div className={chip}>
            <label htmlFor={thinkingId} className={CHIP_LABEL_CLASS}>
              Thinking
            </label>
            <select
              id={thinkingId}
              value={choice.effort ?? ""}
              disabled={disabled}
              onChange={(e) => onEffortChange(e.target.value)}
              className={`${CHIP_SELECT_CLASS} max-w-[90px] pl-1`}
            >
              {options.map((o) => (
                <option key={o.value} value={o.value} className={OPTION_CLASS}>
                  {o.label}
                </option>
              ))}
            </select>
            <ChevronDown
              className="pointer-events-none absolute right-2 h-3 w-3 text-ink-400"
              aria-hidden="true"
            />
          </div>
        )}
      </div>
      {note !== null && (
        <p className={STATUS_TEXT_CLASS}>{noteText(note, chosenLabel)}</p>
      )}
    </div>
  );
}

function noteText(note: PickerNote, chosenLabel: string): string {
  return note.kind === "stored_model_unavailable"
    ? `The model used earlier in this conversation is no longer available. Using ${chosenLabel}.`
    : `The default model is not available on your plan. Using ${chosenLabel}.`;
}
