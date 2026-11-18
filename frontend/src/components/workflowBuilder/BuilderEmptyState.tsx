"use client";

/**
 * BuilderEmptyState: what the Builder panel shows before a conversation exists
 * (Req 1.6, 1.11). It took over from the popup that used to open first: a short
 * intro and one example prompt. Earlier conversations are reached from the
 * panel header's menu, not from here. The message box and the Model and
 * Thinking picker sit below it in the panel's footer.
 *
 * The example fills the message box and does not send [pending G-25].
 * Presentational: the host owns the text.
 */

import { useId } from "react";

import { AssistantMark } from "@/components/chat/AssistantMark";

/** The one example prompt offered on an empty panel. */
export const EXAMPLE_PROMPT = "Research a topic and write a summary report with sources";

export interface BuilderEmptyStateProps {
  /** Puts the example's text in the message box. Must not send. */
  onPickExample: (text: string) => void;
}

const FOCUS_RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand";
const SECTION_LABEL_CLASS =
  "mb-2 font-sans text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-300";

export function BuilderEmptyState({ onPickExample }: BuilderEmptyStateProps) {
  const headingId = useId();
  const exampleId = useId();

  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col gap-6 pt-1">
      <div className="flex flex-col gap-2.5">
        <AssistantMark />
        <h3
          id={headingId}
          className="font-sans text-[18px] font-light leading-[1.3] tracking-[-0.01em] text-ink-900"
        >
          What should this workflow do?
        </h3>
        <p className="font-serif text-[12.5px] leading-[1.55] text-ink-500">
          Describe it in plain words. The builder drafts it on the canvas, and you can keep
          editing it there.
        </p>
      </div>

      <div>
        <p id={exampleId} className={SECTION_LABEL_CLASS}>
          Try an example
        </p>
        <button
          type="button"
          aria-describedby={exampleId}
          onClick={() => onPickExample(EXAMPLE_PROMPT)}
          className={`w-full rounded-[var(--radius-list-row)] border border-line-border bg-surface-card px-[13px] py-[10px] text-left font-sans text-[12.5px] leading-[1.4] text-ink-700 transition-colors hover:border-line-faint hover:text-ink-900 ${FOCUS_RING}`}
        >
          {EXAMPLE_PROMPT}
        </button>
      </div>
    </section>
  );
}

export default BuilderEmptyState;
