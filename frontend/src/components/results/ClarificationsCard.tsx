"use client";

import { useState } from "react";
import { ChevronDown, Check, Loader2 } from "lucide-react";
import type { ClarifyRound } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 39 plan 02 (RUNUI-06) — ClarificationsCard rebuilt pixel-as-is to the
// mock's Steps-overview clarifications card (Hexaware Run.dc.html :311-332):
// a COLLAPSED-by-default card ("Clarifications · N questions across R round(s) ·
// answered" + chevron); expanded, the rounds are FLATTENED into one Q&A list —
// each row is the question text (with a "★ High impact" amber badge on
// high-impact questions only) followed by the answer prefixed with a check icon.
// Fully props-driven — renders NOTHING for a PROCEED run (no rounds); the reopen
// mount passes fetched rounds, the live mount passes pipelineState.clarifications
// (threaded by AgentThinkingTab). Token-reskinned (no gray-* palette).
// ─────────────────────────────────────────────────────────────────────────────

interface ClarificationsCardProps {
  clarifications?: ClarifyRound[];
  loading?: boolean;
}

export function ClarificationsCard({ clarifications, loading }: ClarificationsCardProps) {
  // Collapsed by default — the mock's settled clarifications is a read-only record.
  const [expanded, setExpanded] = useState(false);

  const rounds = clarifications ?? [];
  const hasRounds = rounds.length > 0;

  // PROCEED run (no rounds) and not loading → render NOTHING.
  if (!loading && !hasRounds) return null;

  const questionCount = rounds.reduce((n, r) => n + r.qa.length, 0);
  const subtitle = loading
    ? "Loading clarifications…"
    : `${questionCount} question${questionCount !== 1 ? "s" : ""} across ${rounds.length} round${rounds.length !== 1 ? "s" : ""} · answered`;

  // Flatten every round into one Q&A list (the mock renders a single flat list).
  const items = rounds.flatMap((r) => r.qa);

  return (
    <div className="rounded-[12px] border border-line-border bg-surface-card overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-label={`Clarifications, ${questionCount} question${questionCount !== 1 ? "s" : ""}`}
        className="w-full flex items-center gap-2.5 px-3.5 py-3 text-left"
      >
        <div className="flex-1 min-w-0">
          <p className="m-0 text-[13px] font-semibold text-ink-900 font-[Manrope]">Clarifications</p>
          <p className="m-0 mt-0.5 text-[11.5px] text-ink-300">{subtitle}</p>
        </div>
        <ChevronDown aria-hidden className={`h-4 w-4 text-ink-300 flex-none transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {(expanded || loading) && (
        <div className="px-3.5 pb-2.5" aria-busy={loading || undefined}>
          {loading ? (
            <div className="flex items-center gap-2 pt-2">
              <Loader2 aria-hidden className="h-4 w-4 text-brand animate-spin" />
              <span className="text-[11px] text-ink-300">Loading clarifications…</span>
            </div>
          ) : (
            items.map((item, i) => (
              <div key={`${item.question_id}-${i}`} className="py-2.5 border-t border-surface-paper">
                <div className="flex items-center gap-2 mb-1.5">
                  {item.impact_level === "high" && (
                    <span className="flex-none text-[9px] font-semibold text-status-amber bg-status-amber-fill border border-status-amber-border px-1.5 py-1 rounded-[5px] font-[Manrope]">
                      ★ High impact
                    </span>
                  )}
                  <p className="m-0 text-[12.5px] font-medium text-ink-800 leading-[1.4]">{item.question_text}</p>
                </div>
                {item.answer && (
                  <p className="m-0 flex items-start gap-1.5 text-[12px] text-ink-700 leading-[1.45]">
                    <Check aria-hidden className="h-3 w-3 text-ink-900 flex-none mt-0.5" />
                    {item.answer}
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
