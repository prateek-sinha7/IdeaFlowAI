"use client";

/**
 * ResultCard — the narrator result card the chat lane projects from a `chat_reply`
 * turn (Phase 31, CHATUI-01). It renders a narrator message BY ITS GENERIC
 * `cardKind` (`clarify | gate | pipeline | deliverable | spec_revision`) and
 * offers a "deep-link" affordance that opens the milestone's run tab through the
 * plan-03 nonce'd seam (`useTabDeepLink.requestOpenTab`, open-design borrow #6).
 *
 * SC-001 (the CONTEXT invariant): the card selects its label + target tab from a
 * SWITCH on the generic card kind — NEVER a workflow/agent name. An unknown or
 * absent kind falls back to an inert generic card (T-31-04-T2) rather than a
 * workflow-name branch. The narrator text is rendered by react-markdown with NO
 * `rehype-raw` / `dangerouslySetInnerHTML` (T-31-04-T XSS mitigation).
 *
 * LOCK-F: the `deliverable` card labels the run output "Deliverable" (never a
 * workflow-specific noun). LIVE-STATE-CONTRACT §2b terminology: the
 * `spec_revision` card is the KAN-101 spec loop-back — "Revising spec — cycle N"
 * — distinct from a family revision RUN; the two are never conflated.
 *
 * Skin (D-15 — reskin-look keep-behavior): Phase-32 brand token layer + lucide-react.
 */

import {
  ArrowUpRight,
  CheckCircle2,
  FileCheck2,
  HelpCircle,
  ListChecks,
  RefreshCw,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatMessage } from "@/types/index";

type CardKind = NonNullable<ChatMessage["cardKind"]>;

interface CardSpec {
  title: string;
  linkLabel: string;
  /** Generic run-tab id the deep-link targets when the frame carries none. */
  defaultTab: string;
  Icon: typeof ArrowUpRight;
  tone: string;
}

/**
 * The card-kind → presentation map. Keyed ENTIRELY on the generic milestone
 * card kind (SC-001) — a renamed workflow cannot change which card renders.
 */
const CARD_SPECS: Record<CardKind, CardSpec> = {
  clarify: {
    title: "Clarification needed",
    linkLabel: "Answer in Steps",
    defaultTab: "steps",
    Icon: HelpCircle,
    tone: "text-status-amber",
  },
  gate: {
    title: "Review required",
    linkLabel: "Open in Steps",
    defaultTab: "steps",
    Icon: CheckCircle2,
    tone: "text-brand",
  },
  pipeline: {
    title: "Pipeline update",
    linkLabel: "Open in Steps",
    defaultTab: "steps",
    Icon: ListChecks,
    tone: "text-status-running",
  },
  // LOCK-F: the run output is "Deliverable", never a workflow-specific noun.
  deliverable: {
    title: "Deliverable",
    linkLabel: "Open in Preview",
    defaultTab: "preview",
    Icon: FileCheck2,
    tone: "text-status-done",
  },
  spec_revision: {
    title: "Revising spec",
    linkLabel: "Open in Steps",
    defaultTab: "steps",
    Icon: RefreshCw,
    tone: "text-brand",
  },
};

interface ResultCardProps {
  /** The narrator `chat_reply` turn (carries `cardKind`, `content`, `deepLink`). */
  message: ChatMessage;
  /** The plan-03 nonce'd deep-link seam — opens a generic run tab (borrow #6). */
  onRequestOpenTab: (tab: string) => void;
  /**
   * KAN-101 spec loop-back cycle (spec_revision only) — the "cycle N" counter.
   * Generic data, never a workflow discriminator. Defaults to 1.
   */
  cycle?: number;
}

export function ResultCard({ message, onRequestOpenTab, cycle }: ResultCardProps) {
  const kind = message.cardKind;
  // Unknown/absent kind → inert generic card (no workflow-name branch; SC-001,
  // T-31-04-T2). A crafted narrator with an unrecognised kind cannot select a
  // privileged renderer — it degrades to the plain card below.
  const spec = kind ? CARD_SPECS[kind] : undefined;
  // The stored descriptor's tab wins; else the kind's generic default; else Steps.
  const tab = message.deepLink?.tab ?? spec?.defaultTab ?? "steps";
  const title =
    kind === "spec_revision"
      ? `Revising spec — cycle ${cycle ?? 1}`
      : (spec?.title ?? "Update");
  const Icon = spec?.Icon ?? ListChecks;
  const tone = spec?.tone ?? "text-ink-500";
  const linkLabel = spec?.linkLabel ?? "Open";

  return (
    <div
      data-testid="chat-result-card"
      data-card-kind={kind ?? "unknown"}
      className="my-2 rounded-2xl border border-line-border bg-surface-white px-4 py-3 shadow-sm"
    >
      <div className="mb-1.5 flex items-center gap-2">
        <Icon className={`h-4 w-4 flex-shrink-0 ${tone}`} aria-hidden="true" />
        <p className="text-[12px] font-semibold text-ink-900">{title}</p>
      </div>

      <div className="markdown-content text-[13px] leading-relaxed text-ink-700">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.content}
        </ReactMarkdown>
      </div>

      <button
        type="button"
        data-testid="chat-result-card-link"
        data-target-tab={tab}
        onClick={() => onRequestOpenTab(tab)}
        className="mt-2 inline-flex items-center gap-1 rounded-lg border border-brand/20 px-3 py-1.5 text-[11px] font-semibold text-brand transition-colors hover:bg-brand-fill"
      >
        {linkLabel}
        <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
