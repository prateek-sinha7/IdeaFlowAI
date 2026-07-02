"use client";

import { useState } from "react";
import { MessageCircleQuestion, ChevronDown, Loader2 } from "lucide-react";
import type { ClarifyRound } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D4) — ClarificationsCard: the clarify exchange, inserted
// AFTER PlannerCard and BEFORE the agent cards. Renders NOTHING for a PROCEED run
// (no rounds). Fully props-driven — renders on BOTH the live mount (retained
// pipelineState.clarifications, threaded by AgentThinkingTab) and the reopen
// mount (getRunArtifacts → parseClarificationArtifacts).
//
// Every visual node clones an existing analog (WORKSTREAM-C-UI-SPEC.md Surface 2):
//   card shell + timeline dot .......... PlannerCard AgentThinkingTab.tsx:108-177
//   round micro-label + count chip ..... ToolCallsSection :323-324
//   Q/A summary card ................... QuestionnairePanel.tsx:174-185
//   impact badge (high = amber) ........ QuestionnairePanel.tsx:285
//   impact badge (medium = gray tier) .. severity map AgentThinkingTab.tsx:262
// ─────────────────────────────────────────────────────────────────────────────

interface ClarificationsCardProps {
  clarifications?: ClarifyRound[];
  loading?: boolean;
}

function ImpactBadge({ level }: { level: string }) {
  if (level === "high") {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
        ★ High impact
      </span>
    );
  }
  if (level === "medium") {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] font-semibold text-gray-600 bg-gray-100 rounded-full px-2 py-0.5">
        Medium impact
      </span>
    );
  }
  return null; // low / unset → omit to avoid noise
}

export function ClarificationsCard({ clarifications, loading }: ClarificationsCardProps) {
  const [expanded, setExpanded] = useState(true);

  const rounds = clarifications ?? [];
  const hasRounds = rounds.length > 0;

  // PROCEED run (no rounds) and not loading → render NOTHING.
  if (!loading && !hasRounds) return null;

  const questionCount = rounds.reduce((n, r) => n + r.qa.length, 0);
  const subtitle = loading
    ? "Loading clarifications…"
    : `${questionCount} question${questionCount !== 1 ? "s" : ""} across ${rounds.length} round${rounds.length !== 1 ? "s" : ""}`;

  return (
    <div className="relative pl-8">
      {/* Timeline dot — sits on the rail between Planner and Agents */}
      <div className="absolute left-0 top-3 flex flex-col items-center">
        <div className="w-6 h-6 rounded-full flex items-center justify-center border-2 z-10 border-[#1B2A4A] bg-[#E8EDF5]">
          <MessageCircleQuestion aria-hidden className="h-3 w-3 text-[#1B2A4A]" />
        </div>
        <div className="w-px flex-1 bg-gray-200 mt-1" style={{ minHeight: 20 }} />
      </div>

      <div className="rounded-xl border overflow-hidden border-gray-100">
        <button
          onClick={() => setExpanded(v => !v)}
          aria-expanded={expanded}
          aria-label={`Clarifications, ${questionCount} question${questionCount !== 1 ? "s" : ""}`}
          className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-gray-50/50 transition-colors text-left"
        >
          <div className="w-7 h-7 rounded-lg bg-[#E8EDF5] flex items-center justify-center flex-shrink-0">
            <MessageCircleQuestion aria-hidden className="h-3.5 w-3.5 text-[#1B2A4A]" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[12px] font-semibold text-gray-900">Clarifications</p>
            <p className="text-[10px] text-gray-400 truncate">{subtitle}</p>
          </div>
          <ChevronDown aria-hidden className={`h-3.5 w-3.5 text-gray-400 flex-shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>

        {expanded && (
          <div className="border-t border-gray-100 px-4 py-3 bg-white" aria-busy={loading || undefined}>
            {loading ? (
              <div className="flex items-center gap-2">
                <Loader2 aria-hidden className="h-4 w-4 text-[#1B2A4A] animate-spin" />
                <span className="text-[10px] text-gray-400">Loading clarifications…</span>
              </div>
            ) : (
              <div className="space-y-4">
                {rounds.map((round) => (
                  <div key={round.round} className="space-y-2">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">Round</span>
                      <span className="text-[9px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full font-medium">{round.round}</span>
                    </div>
                    {round.qa.map((item, i) => (
                      <div
                        key={`${item.question_id}-${i}`}
                        className="rounded-xl border px-4 py-3 border-emerald-200 bg-emerald-50/30"
                      >
                        {item.impact_level && (
                          <div className="mb-1.5">
                            <ImpactBadge level={item.impact_level} />
                          </div>
                        )}
                        <p className="text-[12px] font-semibold text-gray-800 leading-snug">{item.question_text}</p>
                        {item.answer && (
                          <p className="text-[11px] text-emerald-600 font-medium mt-1">✓ {item.answer}</p>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
