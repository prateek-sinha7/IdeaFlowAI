/**
 * ThinkingBlock — collapsed-by-default reasoning with a "Thought for Xs" timer
 * (open-design borrow #7).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of upstream's `ThinkingBlock` (`AssistantMessage.tsx:2603`)
 * — a first-class `{kind:'thinking'}` render surface, collapsed by default, with
 * a client-measured "Thought for Xs" label sourced from the block's `durationMs`.
 *
 * CURRENT SKIN (D-15 — behavior over restyle): raw Tailwind + motion +
 * lucide-react, reusing the existing kit's collapsible/`<thinking>` idiom
 * (`MessageBubble.tsx`). Phase 32 owns the reskin. Rendered inert (no HTML/eval).
 */

"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Brain, ChevronDown, ChevronRight } from "lucide-react";

import type { ChatBlock } from "../runtime/blocks.types";

type ThinkingData = Extract<ChatBlock, { kind: "thinking" }>;

/** Round elapsed ms to a whole-second "Thought for Xs" label. */
function elapsedLabel(durationMs?: number): string {
  if (durationMs == null) return "Thought process";
  const seconds = Math.max(1, Math.round(durationMs / 1000));
  return `Thought for ${seconds}s`;
}

export function ThinkingBlock({ block }: { block: ThinkingData }) {
  const [expanded, setExpanded] = useState(false);
  const label = elapsedLabel(block.durationMs);
  const bodyId = "chat-thinking-body";

  return (
    <div data-testid="chat-thinking-block" className="mb-4">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls={bodyId}
        className="flex items-center gap-1.5 text-[12px] text-grey/60 hover:text-grey/90 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        <Brain className="h-3.5 w-3.5 text-purple-400/70" aria-hidden="true" />
        <span className="font-medium">{label}</span>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id={bodyId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="relative mt-2 pl-4 py-2 text-[13px] text-grey/60 leading-relaxed whitespace-pre-wrap">
              <div className="absolute left-0 top-0 bottom-0 w-[2px] rounded-full bg-gradient-to-b from-blue-400/60 via-purple-400/40 to-transparent" />
              {block.text}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
