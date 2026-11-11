"use client";

/**
 * BuilderEmptyState: what the Builder panel shows before a conversation exists
 * (Req 1.6, 1.11, 12.1). It took over from the popup that used to open first:
 * a short intro, example prompts and the most recent conversations. The message
 * box and the Model and Thinking picker sit below it in the panel's footer.
 *
 * An example fills the message box and does not send [pending G-25]. Picking a
 * recent conversation opens it as Requirement 12 describes. Presentational: the
 * host owns the text and the session list.
 */

import { useId } from "react";

import { AssistantMark } from "@/components/chat/AssistantMark";
import { formatRelativeAge } from "@/components/chat/LaneRunHeader";
import type { SessionSummary } from "@/types/workflowBuilder";

/** Example prompts offered on an empty panel (Req 1.6: three to four). */
export const EXAMPLE_PROMPTS: readonly string[] = [
  "Research a topic and write a summary report with sources",
  "Turn meeting notes into action items and a follow-up email",
  "Review a document and list risks, gaps and suggested fixes",
  "Plan a product launch with tasks, owners and a timeline",
];

/** Number of recent conversations the empty panel lists (design G-24). */
export const EMPTY_STATE_RECENT_SESSIONS = 5;

export interface BuilderEmptyStateProps {
  /** Puts the example's text in the message box. Must not send. */
  onPickExample: (text: string) => void;
  /** The user's sessions, newest first; the first few are listed. */
  recentSessions: readonly SessionSummary[];
  onSelectSession: (sessionId: string) => void;
}

const FOCUS_RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand";
const SECTION_LABEL_CLASS =
  "mb-2 font-sans text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-300";

export function BuilderEmptyState({
  onPickExample,
  recentSessions,
  onSelectSession,
}: BuilderEmptyStateProps) {
  const headingId = useId();
  const examplesId = useId();
  const recentId = useId();
  const recent = recentSessions.slice(0, EMPTY_STATE_RECENT_SESSIONS);

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
        <p id={examplesId} className={SECTION_LABEL_CLASS}>
          Try an example
        </p>
        <ul aria-labelledby={examplesId} className="flex flex-col gap-2">
          {EXAMPLE_PROMPTS.map((prompt) => (
            <li key={prompt}>
              <button
                type="button"
                onClick={() => onPickExample(prompt)}
                className={`w-full rounded-[var(--radius-list-row)] border border-line-border bg-surface-card px-[13px] py-[10px] text-left font-sans text-[12.5px] leading-[1.4] text-ink-700 transition-colors hover:border-line-faint hover:text-ink-900 ${FOCUS_RING}`}
              >
                {prompt}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {recent.length > 0 ? (
        <div>
          <p id={recentId} className={SECTION_LABEL_CLASS}>
            Recent conversations
          </p>
          <ul aria-labelledby={recentId} className="-mx-2 flex flex-col">
            {recent.map((session) => (
              <li key={session.id}>
                <button
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                  className={`flex w-full items-center gap-3 rounded-[var(--radius-node)] px-2 py-1.5 text-left transition-colors hover:bg-surface-paper ${FOCUS_RING}`}
                >
                  <span className="min-w-0 flex-1 truncate font-sans text-[12.5px] text-ink-900">
                    {session.title}
                  </span>
                  <span className="flex-none font-sans text-[11px] tabular-nums text-ink-400">
                    {formatRelativeAge(session.updated_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export default BuilderEmptyState;
