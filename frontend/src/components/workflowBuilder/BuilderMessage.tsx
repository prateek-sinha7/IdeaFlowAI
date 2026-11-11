"use client";

/**
 * BuilderMessage: one message of the AI Workflow Builder transcript (design 3.10.5).
 *
 * Presentational. It renders a stored or streaming `TranscriptMessage` and
 * calls back through optional props; it fetches nothing and keeps only local
 * UI state (the reading-view dialog). An action button appears only when the
 * parent passes its callback, so the parent decides where Retry, Continue and
 * Undo are offered (Property 35 lives in the selectors, not here).
 *
 * Safe Markdown (Req 4.8, 4.9): assistant text goes through `react-markdown`
 * with `remark-gfm` and no `rehype-raw`, the `components/chat/ResultCard.tsx`
 * pattern, so raw HTML in a reply renders as text. react-markdown's default
 * URL transform also drops `javascript:` links. Images are replaced by their
 * alt text so a reply cannot make the browser fetch a remote URL. There is no
 * `dangerouslySetInnerHTML`. User messages are plain text, not Markdown.
 */

import { Check, Maximize2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { USER_BUBBLE_CLASS, USER_BUBBLE_TEXT_CLASS } from "@/components/chat/chatStyles";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import type {
  ChangeSummary,
  DraftRevisionOut,
  LaunchNeed,
  StopReason,
  TranscriptMessage,
} from "@/types/workflowBuilder";

import { foldReport } from "./reportFold";

export interface BuilderMessageProps {
  message: TranscriptMessage;
  /**
   * The accepted draft of this message's turn. Its change summary and launch
   * needs show only when `message.revision` is set and this is passed.
   */
  draft?: Pick<DraftRevisionOut, "change_summary" | "launch_needs"> | null;
  /** Offered on a `failed` message (Req 13.1). */
  onRetry?: () => void;
  /** Offered on a `timed_out` or `interrupted` message (Req 13.8, 13.9). */
  onContinue?: () => void;
  /** Offered on the latest message whose accepted revision is the latest (Req 8.3). */
  onUndo?: () => void;
  /** Disables the three actions, for example while a turn runs. */
  actionsDisabled?: boolean;
}

// --- Markdown ------------------------------------------------------------------------

/** Tables scroll sideways inside the message instead of widening it (Req 15.2). */
const MARKDOWN_COMPONENTS: Components = {
  table: ({ children }) => (
    <div
      role="region"
      aria-label="Table, scrolls sideways"
      tabIndex={0}
      className="my-2 max-w-full overflow-x-auto rounded-[var(--radius-node)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      <table style={{ width: "max-content", minWidth: "100%" }}>{children}</table>
    </div>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  img: ({ alt }) => <span>{alt ?? ""}</span>,
};

/** Renders assistant Markdown with the safe component set. The transcript reuses it for streamed text. */
export function SafeMarkdown({ text }: { text: string }) {
  return (
    <div className="markdown-content min-w-0 break-words font-serif text-[13px] leading-relaxed text-ink-900">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

// --- Wording -------------------------------------------------------------------------

const KEPT = "The work so far is kept.";

/** Notice for a turn that ended `timed_out` or `interrupted`, worded by `stop_reason`. */
function stopNoticeText(status: "timed_out" | "interrupted", reason: StopReason | null): string {
  if (status === "interrupted") {
    return `A server restart stopped this turn. ${KEPT}`;
  }
  switch (reason) {
    case "time":
      return `This turn stopped at the time limit. ${KEPT}`;
    case "tool_calls":
      return `This turn stopped at the tool-call limit. ${KEPT}`;
    case "tokens":
      return `This turn stopped at the token limit. ${KEPT}`;
    case "recursion":
      return `This turn stopped at the step limit. ${KEPT}`;
    default:
      return `This turn stopped at a limit. ${KEPT}`;
  }
}

function describeChanges(summary: ChangeSummary): string[] {
  const lines: string[] = [];
  if (summary.added.length > 0) lines.push(`Added: ${summary.added.join(", ")}`);
  if (summary.removed.length > 0) lines.push(`Removed: ${summary.removed.join(", ")}`);
  if (summary.reordered) lines.push("Steps reordered");
  if (summary.gates_changed.length > 0) {
    lines.push(`Gates changed: ${summary.gates_changed.join(", ")}`);
  }
  if (summary.validators_changed.length > 0) {
    lines.push(`Validators changed: ${summary.validators_changed.join(", ")}`);
  }
  if (summary.models_changed.length > 0) {
    lines.push(`Models changed: ${summary.models_changed.join(", ")}`);
  }
  if (summary.prompts_changed > 0) {
    lines.push(
      summary.prompts_changed === 1 ? "1 prompt changed" : `${summary.prompts_changed} prompts changed`,
    );
  }
  return lines.length > 0 ? lines : ["No changes to the steps"];
}

function describeLaunchNeed(need: LaunchNeed): string {
  const detail = need.detail ? ` (${need.detail})` : "";
  switch (need.kind) {
    case "uploads":
      return `Files to upload${detail}`;
    case "design":
      return `A design or template${detail}`;
    case "connector":
      return `A connector${detail}`;
    case "source_run":
      return `A source run${detail}`;
  }
}

// --- Small pieces --------------------------------------------------------------------

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1";

/** A collapsed-by-default section built on native `<details>` (keyboard and screen-reader ready). */
function Fold({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="mt-2 rounded-[var(--radius-node)] border border-line-border bg-surface-card first:mt-0">
      <summary
        className={`cursor-pointer rounded-[var(--radius-node)] px-3 py-1.5 text-[12px] font-semibold text-ink-700 ${FOCUS_RING}`}
      >
        {label}
      </summary>
      <div className="border-t border-line-divider px-3 py-2">{children}</div>
    </details>
  );
}

function DraftDetails({
  draft,
}: {
  draft: Pick<DraftRevisionOut, "change_summary" | "launch_needs">;
}) {
  const changes = draft.change_summary ? describeChanges(draft.change_summary) : [];
  const needs = draft.launch_needs;
  if (changes.length === 0 && needs.length === 0) return null;
  return (
    <div className="mt-3 rounded-[var(--radius-menu)] border border-line-border bg-surface-card px-[13px] py-[11px] font-sans text-[12px] text-ink-700">
      {changes.length > 0 ? (
        <div>
          <p className="flex items-center gap-2 font-semibold text-ink-900">
            <span
              aria-hidden="true"
              className="grid h-4 w-4 flex-none place-items-center rounded-full border border-status-done-border bg-status-done-fill"
            >
              <Check className="h-2.5 w-2.5 text-status-done" strokeWidth={2.4} />
            </span>
            What changed
          </p>
          <ul className="mt-1.5 list-disc pl-[38px] leading-[1.5]">
            {changes.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {needs.length > 0 ? (
        <div className={changes.length > 0 ? "mt-2.5 border-t border-line-divider pt-2.5" : undefined}>
          <p className="font-semibold text-ink-900">Before you run it</p>
          <ul className="mt-1.5 list-disc pl-5 leading-[1.5]">
            {needs.map((need) => (
              <li key={`${need.kind}:${need.detail ?? ""}`}>{describeLaunchNeed(need)}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

// --- Component -----------------------------------------------------------------------

export function BuilderMessage({
  message,
  draft = null,
  onRetry,
  onContinue,
  onUndo,
  actionsDisabled = false,
}: BuilderMessageProps) {
  const [readingView, setReadingView] = useState(false);

  if (message.role === "user") {
    return (
      <article
        aria-label="Your message"
        className={`ml-auto max-w-[86%] break-words ${USER_BUBBLE_CLASS} ${USER_BUBBLE_TEXT_CLASS}`}
      >
        {message.content}
      </article>
    );
  }

  const folded = foldReport(message.content);
  const hasContent = message.content.trim().length > 0;
  const showDraft = message.revision !== null && draft !== null;
  const stopped = message.status === "timed_out" || message.status === "interrupted";

  return (
    <div className="min-w-0">
      {message.skill_updated ? (
        <p className="mb-1 text-center text-[11px] text-ink-500">
          The builder was updated before this reply.
        </p>
      ) : null}
      <article aria-label="Builder reply" className="min-w-0">
        {message.thinking ? (
          <Fold label="Thinking">
            <p className="whitespace-pre-wrap break-words font-sans text-[12px] leading-relaxed text-ink-600">
              {message.thinking}
            </p>
          </Fold>
        ) : null}

        {hasContent ? (
          <div className="mt-2 first:mt-0">
            {folded.folded ? (
              <>
                <SafeMarkdown text={folded.summary} />
                <Fold label="Full report">
                  <SafeMarkdown text={folded.report} />
                </Fold>
              </>
            ) : (
              <SafeMarkdown text={folded.text} />
            )}
          </div>
        ) : null}

        {showDraft ? <DraftDetails draft={draft} /> : null}

        {message.status === "failed" ? (
          <div className="mt-2 flex flex-wrap items-center gap-2 rounded-[var(--radius-node)] border border-status-failed-border bg-status-failed-fill px-3 py-2 font-sans text-[12px] text-status-failed-strong first:mt-0">
            <p className="min-w-0 flex-1 break-words">
              {message.error?.message ?? "Something went wrong while writing this reply."}
            </p>
            {onRetry ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={onRetry}
                disabled={actionsDisabled}
                className={FOCUS_RING}
              >
                Retry
              </Button>
            ) : null}
          </div>
        ) : null}

        {stopped ? (
          <div className="mt-2 flex flex-wrap items-center gap-2 rounded-[var(--radius-node)] border border-status-amber-border bg-status-amber-fill px-3 py-2 font-sans text-[12px] text-ink-800 first:mt-0">
            <p className="min-w-0 flex-1 break-words">
              {stopNoticeText(
                message.status === "interrupted" ? "interrupted" : "timed_out",
                message.stop_reason,
              )}
            </p>
            {onContinue ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={onContinue}
                disabled={actionsDisabled}
                className={FOCUS_RING}
              >
                Continue
              </Button>
            ) : null}
          </div>
        ) : null}

        {message.status === "cancelled" ? (
          <p className="mt-2 font-sans text-[12px] text-ink-500">Stopped</p>
        ) : null}

        {hasContent || onUndo ? (
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            {onUndo ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={onUndo}
                disabled={actionsDisabled}
                className={FOCUS_RING}
              >
                Undo
              </Button>
            ) : null}
            {hasContent ? (
              <button
                type="button"
                onClick={() => setReadingView(true)}
                className={`inline-flex items-center gap-1 rounded-[6px] px-1 py-0.5 font-sans text-[11px] font-medium text-ink-400 transition-colors hover:text-brand ${FOCUS_RING}`}
              >
                <Maximize2 className="h-3 w-3" aria-hidden="true" />
                Open in reading view
              </button>
            ) : null}
          </div>
        ) : null}
      </article>

      {readingView ? (
        <Modal
          title="Reading view"
          onClose={() => setReadingView(false)}
          className="max-h-[85vh] max-w-3xl! overflow-y-auto"
        >
          <SafeMarkdown text={message.content} />
        </Modal>
      ) : null}
    </div>
  );
}

export default BuilderMessage;
