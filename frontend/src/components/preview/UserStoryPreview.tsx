"use client";

import { useState } from "react";
import { FileText, BookOpen, CheckCircle2, Copy, Check, Users, Link2, Target, Layers, Zap } from "lucide-react";
import { parseUserStoryMarkdown } from "@/lib/parsers/userStoryParser";

interface UserStoryPreviewProps {
  content?: string;
}

const EPIC_COLORS = [
  { border: "border-l-blue-500", bg: "bg-blue-50", badge: "bg-blue-100 text-blue-700" },
  { border: "border-l-purple-500", bg: "bg-purple-50", badge: "bg-purple-100 text-purple-700" },
  { border: "border-l-emerald-500", bg: "bg-emerald-50", badge: "bg-emerald-100 text-emerald-700" },
  { border: "border-l-amber-500", bg: "bg-amber-50", badge: "bg-amber-100 text-amber-700" },
  { border: "border-l-rose-500", bg: "bg-rose-50", badge: "bg-rose-100 text-rose-700" },
  { border: "border-l-cyan-500", bg: "bg-cyan-50", badge: "bg-cyan-100 text-cyan-700" },
];

function getStoryPointColor(points?: number): string {
  if (!points) return "bg-[#f0eee6] text-[#5e5d59]";
  if (points <= 2) return "bg-emerald-100 text-emerald-700";
  if (points <= 5) return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

function getPriorityColor(priority?: string): string {
  if (!priority) return "bg-[#f0eee6] text-[#5e5d59]";
  if (priority.includes("P0")) return "bg-rose-100 text-rose-700";
  if (priority.includes("P1")) return "bg-amber-100 text-amber-700";
  return "bg-blue-100 text-blue-700";
}

export function UserStoryPreview({ content }: UserStoryPreviewProps) {
  const [copied, setCopied] = useState(false);
  const [expandedEpics, setExpandedEpics] = useState<Set<number>>(new Set([0, 1, 2, 3, 4, 5]));

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#f0eee6] to-[#e8e6dc] border border-[#e8e6dc] mb-4">
          <FileText className="h-7 w-7 text-[#87867f]" />
        </div>
        <p className="text-sm font-medium text-[#5e5d59] mb-1">No User Stories Yet</p>
        <p className="text-xs text-[#87867f] text-center max-w-[220px]">
          Run the pipeline to generate a structured product backlog.
        </p>
      </div>
    );
  }

  const doc = parseUserStoryMarkdown(content);

  const handleCopyMarkdown = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleEpic = (idx: number) => {
    setExpandedEpics((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  // Calculate summary stats
  const totalStories = doc.epics.reduce((sum, e) => sum + e.stories.length, 0);
  const totalPoints = doc.epics.reduce((sum, e) => sum + e.stories.reduce((s, st) => s + (st.storyPoints || 0), 0), 0);
  const p0Count = doc.epics.filter((e) => e.priority?.includes("P0")).length;
  const p1Count = doc.epics.filter((e) => e.priority?.includes("P1")).length;

  // If parser found no epics, render raw markdown nicely
  if (doc.epics.length === 0) {
    return (
      <div className="p-4 h-full overflow-y-auto">
        <div className="flex justify-end mb-3">
          <button onClick={handleCopyMarkdown} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-[#5e5d59] hover:text-[#141413] hover:bg-[#f0eee6] border border-[#e8e6dc] transition-all">
            {copied ? <><Check className="h-3 w-3 text-emerald-600" /><span className="text-emerald-600">Copied!</span></> : <><Copy className="h-3 w-3" /><span>Copy Markdown</span></>}
          </button>
        </div>
        <div className="rounded-xl border border-[#e8e6dc] bg-white p-5">
          <div className="prose prose-sm max-w-none text-[#141413] text-[12px] leading-relaxed whitespace-pre-wrap font-mono">
            {content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 h-full overflow-y-auto space-y-3">
      {/* Header with copy button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-[#c96442]" />
          <span className="text-[12px] font-semibold text-[#141413]">Product Backlog</span>
        </div>
        <button onClick={handleCopyMarkdown} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-medium text-[#5e5d59] hover:text-[#141413] hover:bg-[#f0eee6] border border-[#e8e6dc] transition-all">
          {copied ? <><Check className="h-3 w-3 text-emerald-600" /><span className="text-emerald-600">Copied!</span></> : <><Copy className="h-3 w-3" /><span>Copy MD</span></>}
        </button>
      </div>

      {/* Summary Stats Card */}
      <div className="rounded-xl border border-[#e8e6dc] bg-white p-3 grid grid-cols-4 gap-2">
        <div className="text-center">
          <p className="text-[16px] font-bold text-[#141413]">{doc.epics.length}</p>
          <p className="text-[9px] text-[#87867f] font-medium">Epics</p>
        </div>
        <div className="text-center">
          <p className="text-[16px] font-bold text-[#141413]">{totalStories}</p>
          <p className="text-[9px] text-[#87867f] font-medium">Stories</p>
        </div>
        <div className="text-center">
          <p className="text-[16px] font-bold text-[#c96442]">{totalPoints}</p>
          <p className="text-[9px] text-[#87867f] font-medium">Points</p>
        </div>
        <div className="text-center">
          <p className="text-[16px] font-bold text-[#141413]">{Math.ceil(totalPoints / 30) || 1}</p>
          <p className="text-[9px] text-[#87867f] font-medium">Sprints</p>
        </div>
      </div>

      {/* Priority breakdown */}
      {(p0Count > 0 || p1Count > 0) && (
        <div className="flex gap-2">
          {p0Count > 0 && <span className="text-[9px] font-semibold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">{p0Count} Must-have</span>}
          {p1Count > 0 && <span className="text-[9px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">{p1Count} Should-have</span>}
          {doc.epics.length - p0Count - p1Count > 0 && <span className="text-[9px] font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">{doc.epics.length - p0Count - p1Count} Nice-to-have</span>}
        </div>
      )}

      {/* Epics and Stories */}
      {doc.epics.map((epic, epicIdx) => {
        const colors = EPIC_COLORS[epicIdx % EPIC_COLORS.length];
        const isExpanded = expandedEpics.has(epicIdx);
        return (
          <div
            key={epicIdx}
            className={`rounded-xl border border-[#e8e6dc] bg-white overflow-hidden border-l-[3px] ${colors.border}`}
          >
            {/* Epic header */}
            <button
              onClick={() => toggleEpic(epicIdx)}
              className="w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-[#faf9f5] transition-colors"
            >
              <div className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-[11px] font-bold ${colors.badge}`}>
                {epicIdx + 1}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-[12px] font-bold text-[#141413] leading-tight">{epic.title}</h2>
                  {epic.priority && (
                    <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[8px] font-bold ${getPriorityColor(epic.priority)}`}>
                      {epic.priority}
                    </span>
                  )}
                  <span className="text-[9px] text-[#87867f]">{epic.stories.length} stories</span>
                </div>
                {epic.businessValue && (
                  <p className="mt-0.5 text-[10px] text-[#5e5d59] leading-relaxed line-clamp-1">{epic.businessValue}</p>
                )}
              </div>
              <span className="text-[#87867f] text-[10px] flex-shrink-0 mt-1">{isExpanded ? "▼" : "▶"}</span>
            </button>

            {/* Stories (collapsible) */}
            {isExpanded && (
              <div className="space-y-2 px-4 pb-3">
                {epic.stories.map((story, storyIdx) => (
                  <div
                    key={storyIdx}
                    className="rounded-lg border border-[#e8e6dc] bg-[#faf9f5] p-3"
                  >
                    <div className="flex items-start gap-2">
                      <BookOpen className="h-3.5 w-3.5 text-[#87867f] flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        {/* Story title + badges */}
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <h3 className="text-[11px] font-semibold text-[#141413] leading-tight">
                            <span className="text-[#87867f] mr-1">{epicIdx + 1}.{storyIdx + 1}</span>
                            {story.title}
                          </h3>
                          {story.storyPoints && (
                            <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[8px] font-bold ${getStoryPointColor(story.storyPoints)}`}>
                              {story.storyPoints} SP
                            </span>
                          )}
                        </div>

                        {/* As a / I want / So that */}
                        {story.description && (
                          <p className="text-[10px] text-[#5e5d59] leading-relaxed mb-1.5 italic">{story.description.replace(/\*\*/g, "")}</p>
                        )}

                        {/* Dependencies */}
                        {story.dependencies && story.dependencies !== "None" && (
                          <div className="flex items-center gap-1 mb-1.5">
                            <Link2 className="h-2.5 w-2.5 text-[#87867f]" />
                            <span className="text-[9px] text-[#87867f]">Depends on: </span>
                            <span className="text-[9px] text-amber-600 font-medium">{story.dependencies}</span>
                          </div>
                        )}

                        {/* Acceptance Criteria */}
                        {story.acceptanceCriteria.length > 0 && (
                          <div className="mt-1.5 space-y-1">
                            {story.acceptanceCriteria.map((criterion, critIdx) => (
                              <div key={critIdx} className="flex items-start gap-1.5 text-[10px] text-[#5e5d59]">
                                <CheckCircle2 className="h-3 w-3 flex-shrink-0 mt-0.5 text-emerald-500" />
                                <span
                                  dangerouslySetInnerHTML={{
                                    __html: criterion
                                      .replace(/\*\*Given\*\*/g, '<span class="text-blue-600 font-semibold">Given</span>')
                                      .replace(/\*\*When\*\*/g, '<span class="text-amber-600 font-semibold">When</span>')
                                      .replace(/\*\*Then\*\*/g, '<span class="text-emerald-600 font-semibold">Then</span>')
                                      .replace(/\bGiven\b/g, '<span class="text-blue-600 font-semibold">Given</span>')
                                      .replace(/\bWhen\b/g, '<span class="text-amber-600 font-semibold">When</span>')
                                      .replace(/\bThen\b/g, '<span class="text-emerald-600 font-semibold">Then</span>')
                                  }}
                                />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
